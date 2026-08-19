package com.mobiletest.recorder.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.ui.Messages
import com.intellij.notification.NotificationGroupManager
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.ui.GenerateKitDialog

/**
 * "Generate Test Kit" — opens a parameter form, then runs the engine's
 * parameterized `kit/generate` over the daemon: crawls the app you described and
 * writes the inventory, interaction graph, tests (in your language) and — for a
 * new project — a runnable scaffold. Not a magic button; you configure it.
 */
class GenerateKitAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val dialog = GenerateKitDialog(project)
        if (!dialog.showAndGet()) return
        val params = dialog.params()

        // One-click orchestration hints (install → crawl → cleanup), collected once
        // on the EDT before the background task — install a build first, then
        // optionally uninstall the app when the crawl finishes.
        val buildPath = dialog.buildPathToInstall()
        val uninstallAfter = dialog.uninstallAfter()
        val deviceId = dialog.deviceId()
        val appPackage = dialog.appPackage()
        val platform = dialog.platform()

        if (buildPath.isNotEmpty() && deviceId.isEmpty()) {
            Messages.showErrorDialog(
                project,
                "Set the Device UDID (Appium) to install the build on — install needs a target device.",
                "Install build",
            )
            return
        }

        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        if (daemonService.getClient() == null && !daemonService.start()) {
            Messages.showErrorDialog(project, "Could not start the mobiscout daemon. Is the CLI installed?", "Error")
            return
        }

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Generating test kit", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                try {
                    // 1. Install the build on the device, if one was given. Fail the
                    //    whole run on an install failure — there is nothing to crawl.
                    if (buildPath.isNotEmpty()) {
                        indicator.text = "Installing $buildPath on $deviceId…"
                        val install = daemonService.installApp(platform, deviceId, buildPath)
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
                    if (uninstallAfter && appPackage.isNotEmpty() && deviceId.isNotEmpty()) {
                        indicator.text = "Uninstalling $appPackage from $deviceId…"
                        val uninstall = try {
                            daemonService.uninstallApp(platform, deviceId, appPackage)
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
                        notify(
                            project,
                            "Test kit generated",
                            "$screens screen(s), $cases test case(s)$extra$crashNote\nWritten to: $output$cleanupNote$tierNote",
                            NotificationType.INFORMATION,
                        )
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        notify(project, "Generation failed", ex.message ?: "Unknown error", NotificationType.ERROR)
                    }
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

    private fun notify(project: com.intellij.openapi.project.Project, title: String, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("Mobiscout Framework")
            .createNotification(title, content, type)
            .notify(project)
    }
}
