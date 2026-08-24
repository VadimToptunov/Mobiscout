package com.mobiletest.recorder.actions

import com.intellij.ide.actions.RevealFileAction
import com.intellij.notification.NotificationAction
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.notification.NotificationGroupManager
import com.mobiletest.recorder.rpc.JsonRpcNotification
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.settings.MTRSettings
import com.mobiletest.recorder.ui.GenerateKitDialog
import com.mobiletest.recorder.ui.Notifier
import java.io.File

/**
 * "Generate Test Kit" — opens a parameter form, then runs the engine's
 * parameterized `kit/generate` over the daemon: crawls the app you described and
 * writes the inventory, interaction graph, tests (in your language) and — for a
 * new project — a runnable scaffold. Not a magic button; you configure it.
 */
class GenerateKitAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        if (daemonService.getClient() != null) {
            openDialogAndRun(project, daemonService) // engine already up
            return
        }
        // First use: start the engine (which may download an ~85 MB binary) OFF the EDT
        // with a progress indicator, then open the dialog — instead of freezing the IDE.
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Starting the Mobiscout engine", false) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Preparing the engine (first run may download it)…"
                daemonService.start()
            }

            override fun onFinished() {
                ApplicationManager.getApplication().invokeLater {
                    if (daemonService.getClient() != null) {
                        openDialogAndRun(project, daemonService)
                    } else {
                        Notifier.error(project, "Couldn't start the engine", "Check your internet connection and try again.")
                    }
                }
            }
        })
    }

    private fun openDialogAndRun(project: Project, daemonService: MTRDaemonService) {
        val dialog = GenerateKitDialog(project)
        if (!dialog.showAndGet()) return
        val params = HashMap(dialog.params()) // mutable: auto-degradation may inject the booted device

        // One-click orchestration hints (install → crawl → cleanup), collected once
        // on the EDT before the background task — install a build first, then
        // optionally uninstall the app when the crawl finishes.
        val buildPath = dialog.buildPathToInstall()
        val uninstallAfter = dialog.uninstallAfter()
        val deviceId = dialog.deviceId()
        val appPackage = dialog.appPackage()
        val platform = dialog.platform()

        if (buildPath.isNotEmpty() && deviceId.isEmpty()) {
            Notifier.error(
                project,
                "Install build",
                "Set the Device UDID (Appium) to install the build on — install needs a target device.",
            )
            return
        }

        // Multi-app: "generate all detected apps" builds one config per app (each on its
        // own device) and generates them in parallel via kit/generateMany.
        val multiConfigs = dialog.multiAppConfigs()
        if (multiConfigs.isNotEmpty()) {
            generateMany(project, daemonService, multiConfigs)
            return
        }

        // Not cancellable: the crawl runs inside a single blocking `kit/generate` RPC and the
        // daemon reads its stdio serially, so a cancel request would sit unread until the crawl
        // finished — the button would do nothing. The crawl self-terminates on its wall-clock
        // budget instead. Better an honest bar with no Cancel than a Cancel that lies.
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Generating test kit", false) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                // Reflect the crawl's streamed progress in the indicator instead of a static
                // "Crawling…": the daemon emits a logs/message per screen it visits.
                val progress = liveProgressListener(indicator)
                daemonService.addNotificationListener(progress)
                try {
                    // 0. Auto-degrade: make sure a device is available before crawling. If
                    //    none is running for this platform, boot a candidate (an AVD, or a
                    //    shut-down simulator) instead of failing on an empty crawl.
                    val device = ensureDevice(daemonService, platform, deviceId, indicator)
                    params["udid"] = device

                    // 1. Install the build on the device, if one was given. Fail the
                    //    whole run on an install failure — there is nothing to crawl.
                    if (buildPath.isNotEmpty()) {
                        indicator.text = "Installing $buildPath on $device…"
                        val install = daemonService.installApp(platform, device, buildPath)
                        val ok = install?.get("ok")?.asBoolean ?: false
                        if (!ok) {
                            val detail = install?.get("detail")?.asString ?: "No response from the daemon."
                            throw IllegalStateException("Install failed: $detail")
                        }
                    }

                    // 2. Crawl and generate.
                    indicator.text = "Crawling ${params["package"]} and generating tests…"
                    val result = daemonService.getClient()?.call("kit/generate", params)?.getResultOrThrow()
                        ?: throw IllegalStateException("No response from daemon")

                    val screens = result.get("screens")?.asInt ?: 0
                    val cases = result.get("cases")?.asInt ?: 0
                    val output = result.get("output")?.asString ?: params["output"]
                    val scaffolded = result.get("scaffolded")?.let { if (it.isJsonNull) null else it.asString }
                    val extra = if (scaffolded != null) " · runnable $scaffolded project" else ""
                    // A crash the app dropped mid-crawl is captured into crashes/ —
                    // surface it, it's usually the most valuable thing a crawl finds.
                    val crashes = result.get("crashes")?.asInt ?: 0
                    val crashNote = if (crashes > 0) " · ⚠️ $crashes crash(es) → crashes/" else ""

                    // 3. Cleanup: uninstall the app if asked. Best-effort — a crawl
                    //    that succeeded should still be reported, so note but don't fail.
                    var cleanupNote = ""
                    if (uninstallAfter && appPackage.isNotEmpty() && device.isNotEmpty()) {
                        indicator.text = "Uninstalling $appPackage from $device…"
                        val uninstall = try {
                            daemonService.uninstallApp(platform, device, appPackage)
                        } catch (ex: Exception) {
                            null
                        }
                        val ok = uninstall?.get("ok")?.asBoolean ?: false
                        cleanupNote = if (ok) {
                            "\nUninstalled $appPackage."
                        } else {
                            val detail = uninstall?.get("detail")?.asString ?: "no response"
                            "\nUninstall failed: $detail"
                        }
                    }

                    // Show the active tier, and upsell when the free-tier quota
                    // actually clipped this kit. On the open-core engine the tier
                    // is unlimited, so this adds nothing.
                    val tierNote = tierNote(daemonService, screens, cases)

                    ApplicationManager.getApplication().invokeLater {
                        if (screens == 0) {
                            // 0 screens means the crawl never reached the app — a failure,
                            // not a success. Say so, with the usual causes.
                            Notifier.warn(
                                project,
                                "No screens crawled",
                                "The crawl reached 0 screens, so no tests were generated. Common causes: the " +
                                    "device/emulator isn't connected, Appium isn't running at the configured " +
                                    "server, or the app package / UDID is wrong. See the Logs tab for details.",
                            )
                        } else {
                            notifyGenerated(
                                project,
                                "$screens screen(s), $cases test case(s)$extra$crashNote" +
                                    "\nWritten to: $output$cleanupNote$tierNote",
                                (output as? String),
                            )
                        }
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        Notifier.error(project, "Generation failed", ex.message ?: "Unknown error")
                    }
                } finally {
                    daemonService.removeNotificationListener(progress)
                }
            }
        })
    }

    /** A daemon-notification listener that mirrors each streamed `logs/message` into the
     *  progress bar's text, so the crawl shows what it's doing (the screen it's on) rather
     *  than a frozen "Crawling…". One trimmed line; ignores everything but logs/message. */
    private fun liveProgressListener(
        indicator: ProgressIndicator,
    ): (JsonRpcNotification) -> Unit = { n ->
        if (n.method == "logs/message") {
            val msg = n.params.get("message")?.asString?.trim().orEmpty()
            if (msg.isNotEmpty()) indicator.text = msg.lineSequence().first().take(120)
        }
    }

    /** Return a device id to crawl on. Auto-degradation: use the given one, else a running
     *  device of this platform, else boot a candidate (an AVD / a shut-down simulator) and
     *  wait for it. Throws a friendly message only when there's nothing to boot. */
    private fun ensureDevice(
        daemonService: MTRDaemonService,
        platform: String,
        deviceId: String,
        indicator: ProgressIndicator,
    ): String {
        if (deviceId.isNotEmpty()) return deviceId
        runningDeviceFor(daemonService, platform)?.let { return it }

        val target = firstBootCandidate(daemonService, platform)
            ?: throw IllegalStateException(
                "No $platform device or emulator available. Connect a device or create an emulator, then try again.",
            )
        indicator.text = "No device running — booting $target…"
        daemonService.startDevice(platform, target)
        val deadline = System.currentTimeMillis() + 120_000
        while (System.currentTimeMillis() < deadline) {
            runningDeviceFor(daemonService, platform)?.let { return it }
            Thread.sleep(3_000)
        }
        throw IllegalStateException("Timed out waiting for $target to boot.")
    }

    /** A running/connected device of the platform, or null. */
    private fun runningDeviceFor(daemonService: MTRDaemonService, platform: String): String? {
        val devices = daemonService.listDevices(platform)?.getAsJsonArray("devices") ?: return null
        return devices.firstNotNullOfOrNull {
            val d = it.asJsonObject
            val running = (d.get("status")?.asString ?: "") in setOf("online", "booted")
            if (running && (d.get("platform")?.asString ?: "") == platform) d.get("id")?.asString else null
        }
    }

    /** A bootable target: the user's preferred emulator/simulator from settings when it's among
     *  the candidates, else the first AVD (Android) / shut-down simulator (iOS). Null if none. */
    private fun firstBootCandidate(daemonService: MTRDaemonService, platform: String): String? {
        val settings = MTRSettings.getInstance()
        if (platform == "android") {
            val avds = daemonService.listAvds()?.getAsJsonArray("avds")?.mapNotNull { it.asString } ?: return null
            val preferred = settings.defaultEmulatorName.trim()
            return avds.firstOrNull { it == preferred } ?: avds.firstOrNull()
        }
        val sims = (daemonService.listDevices("ios")?.getAsJsonArray("devices") ?: return null)
            .map { it.asJsonObject }
            .filter { (it.get("status")?.asString ?: "") == "shutdown" }
        val preferred = settings.defaultSimulatorName.trim()
        return (sims.firstOrNull { (it.get("name")?.asString ?: "") == preferred } ?: sims.firstOrNull())
            ?.get("id")?.asString
    }

    /** Generate a kit for several apps at once (a project's Android + iOS apps) via the
     *  engine's kit/generateMany — crawled in parallel, each on its own device — and report
     *  a per-app summary in one notification. */
    private fun generateMany(project: Project, daemonService: MTRDaemonService, configs: List<Map<String, Any>>) {
        // Not cancellable, same as the single-kit path: kit/generateMany is one blocking RPC.
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Generating ${configs.size} kits", false) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Crawling ${configs.size} apps in parallel…"
                val progress = liveProgressListener(indicator)
                daemonService.addNotificationListener(progress)
                try {
                    val result = daemonService.getClient()
                        ?.call("kit/generateMany", mapOf("configs" to configs, "parallel" to true))
                        ?.getResultOrThrow() ?: throw IllegalStateException("No response from daemon")
                    val results = result.getAsJsonArray("results")
                    val failed = results.count { r ->
                        r.asJsonObject.get("error")?.takeIf { !it.isJsonNull } != null
                    }
                    val lines = results.joinToString("\n") { el ->
                        val r = el.asJsonObject
                        val pkg = r.get("package")?.asString ?: "?"
                        val err = r.get("error")?.takeIf { !it.isJsonNull }?.asString
                        if (err != null) "• $pkg — failed: $err"
                        else "• $pkg — ${r.get("screens")?.asInt ?: 0} screen(s), ${r.get("cases")?.asInt ?: 0} case(s)"
                    }
                    ApplicationManager.getApplication().invokeLater {
                        val title = "Generated ${configs.size - failed}/${configs.size} kits"
                        // All failed → warn; otherwise a normal info summary.
                        if (failed == configs.size) Notifier.warn(project, title, lines)
                        else Notifier.info(project, title, lines)
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        Notifier.error(project, "Generation failed", ex.message ?: "Unknown error")
                    }
                } finally {
                    daemonService.removeNotificationListener(progress)
                }
            }
        })
    }

    /**
     * A one-line tier note for the result notification: empty on the unlimited
     * open-core engine; on a Mobiscout-PRO free tier it names the quota, and adds
     * an upgrade nudge when this kit actually hit the screen/test cap. Best-effort
     * — any lookup failure just omits the note.
     */
    private fun tierNote(daemonService: MTRDaemonService, screens: Int, cases: Int): String {
        return try {
            val lic = daemonService.licenseStatus()
            if (lic?.get("unlimited")?.asBoolean != false) return ""
            fun intOrNull(key: String): Int? = lic.get(key)?.let { if (it.isJsonNull) null else it.asInt }
            val maxScreens = intOrNull("max_screens")
            val maxTests = intOrNull("max_tests")
            val limits = listOfNotNull(maxScreens?.let { "$it screens" }, maxTests?.let { "$it tests" }).joinToString(" / ")
            val clipped = (maxScreens != null && screens >= maxScreens) || (maxTests != null && cases >= maxTests)
            if (clipped) {
                "\nFree tier — capped at $limits. Upgrade to Mobiscout PRO for unlimited."
            } else {
                "\nFree tier ($limits)."
            }
        } catch (ex: Exception) {
            ""
        }
    }

    /** Success notification with an "Open folder" action — the kit is on disk; the first thing
     *  a user wants is to see it, not copy a path out of notification text. */
    private fun notifyGenerated(project: Project, content: String, outputDir: String?) {
        val notification = NotificationGroupManager.getInstance()
            .getNotificationGroup("Mobiscout Framework")
            .createNotification("Test kit generated", content, NotificationType.INFORMATION)
        val dir = outputDir?.let { File(it) }
        if (dir != null && dir.isDirectory) {
            notification.addAction(NotificationAction.createSimpleExpiring("Open folder") {
                RevealFileAction.openDirectory(dir)
            })
        }
        notification.notify(project)
    }
}
