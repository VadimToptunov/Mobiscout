package com.mobiletest.recorder.ui

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.fileChooser.FileChooser
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.openapi.ui.ValidationInfo
import com.intellij.openapi.ui.popup.JBPopupFactory
import com.intellij.ui.dsl.builder.panel
import com.intellij.ui.SimpleListCellRenderer
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.settings.MTRSettings
import java.io.File
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.SwingWorker

/**
 * Parameter form for "Generate Test Kit" — you configure *what you want*
 * (app, platform, language/framework, where results go, new vs existing
 * framework, device) and get the result. Every field maps to one `kit/generate`
 * parameter; nothing is a magic default. Pre-filled from the plugin settings.
 *
 * The menus are dependent: the Framework list holds only the frameworks that
 * exist for the chosen Language (so Java never offers pytest), and platform-only
 * options are hidden/disabled where they don't apply (Espresso is Android-only;
 * the Android backend is irrelevant for iOS).
 */
class GenerateKitDialog(private val project: Project) : DialogWrapper(project) {

    private val settings = MTRSettings.getInstance()

    // Language -> the frameworks it actually has, each as (menu label -> codegen
    // target id). BDD is just a Gherkin framework here, not a separate toggle.
    private val frameworksByLanguage: Map<String, List<Pair<String, String>>> = mapOf(
        "python" to listOf("pytest" to "python_pytest", "pytest-bdd (Gherkin)" to "python_pytest_bdd"),
        "java" to listOf("TestNG" to "java_testng", "Cucumber (Gherkin)" to "java_cucumber"),
        "kotlin" to listOf("Appium" to "kotlin_appium", "Espresso (Android)" to "kotlin_espresso"),
        "javascript" to listOf("WebdriverIO" to "js_webdriverio", "Cucumber (Gherkin)" to "js_cucumber"),
        // Maestro isn't a programming language — it's declarative YAML flows — but the
        // dialog groups targets under this control, so it lives here as its own entry.
        "maestro" to listOf("YAML flows" to "maestro"),
    )

    // Point at a project folder and fill package/platform/build automatically — the
    // config becomes "confirm what was detected" rather than "type it all".
    private val detectButton = JButton("Detect from project…")
    private val packageField = JBTextField(30)
    private val platformCombo = comboBox("android", "ios")
    private val driverCombo = comboBox("adb", "appium")
    private val languageCombo = comboBox("python", "java", "javascript", "kotlin", "maestro")
    private val frameworkCombo = ComboBox<String>()
    private val outputField = TextFieldWithBrowseButton()
    private val newProjectCheck = JBCheckBox("Create a new runnable project (scaffold)", settings.createNewFramework)
    // Device is a dropdown of the currently running/connected devices (shown by name),
    // populated from the engine — so you pick "iPhone 17" instead of hunting for a UDID.
    // Still editable, so a device the engine can't see yet can be typed in.
    private val udidCombo = ComboBox<String>().apply { isEditable = true }
    private val deviceNames = HashMap<String, String>() // udid -> friendly name
    private val devicePlatforms = HashMap<String, String>() // udid -> platform

    // The apps the last "Detect from project…" found. When there's more than one, the
    // checkbox offers to generate a kit for each in parallel (each on its own device).
    private var detectedApps: List<JsonObject> = emptyList()
    private val generateAllCheck = JBCheckBox("Generate all detected apps in parallel", false)
        .apply { isVisible = false }
    private val serverField = JBTextField("http://localhost:4723", 24)
    private val maxStepsField = JBTextField("40", 5)
    private val maxDepthField = JBTextField("8", 5)
    private val launchArgsField = JBTextField(30)

    // Optional login the crawler applies on the first form it sees, so it can get
    // past the sign-in gate and map the app behind it. Sent as a `waypoints` fill
    // instruction the engine already understands; the password is never stored.
    private val loginUserField = JBTextField(20)
    private val loginPassField = JBPasswordField()
    private val loginSubmitField = JBTextField("Log in", 12)

    // Optional install → crawl → cleanup orchestration (not kit/generate params):
    // if a build is given it is installed on the device (UDID) before crawling.
    private val buildPathField = TextFieldWithBrowseButton()
    private val uninstallAfterCheck = JBCheckBox("Uninstall the app after crawling", false)
    private val fuzzCheck = JBCheckBox("Also generate fuzz tests (adversarial inputs per form)", false)

    init {
        title = "Generate Test Kit"
        platformCombo.selectedItem = if (settings.targetPlatform.name.equals("IOS", true)) "ios" else "android"
        languageCombo.selectedItem = dialogLanguage(settings.preferredLanguage)
        outputField.text = if (settings.createNewFramework) "mobile-tests" else settings.existingFrameworkPath

        // Keep the Framework list (and the Android-only backend) in sync with the
        // chosen Language/Platform — only ever showing what's actually available.
        reloadFrameworks()
        applyPlatform()
        languageCombo.addActionListener { reloadFrameworks() }
        platformCombo.addActionListener {
            reloadFrameworks()
            applyPlatform()
        }

        // .apk is a file, .app is a bundle directory — allow either. Title/description
        // ride on the descriptor (the non-deprecated 2-arg overload, 2024.3+).
        buildPathField.addBrowseFolderListener(
            project,
            FileChooserDescriptorFactory.createSingleFileOrFolderDescriptor()
                .withTitle("Select a Build (.apk / .app)")
                .withDescription("The build is installed on the device (UDID) before crawling")
        )
        // Let the output dir be browsed too — a relative path is resolved against the project.
        outputField.addBrowseFolderListener(
            project,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
                .withTitle("Select the output directory")
                .withDescription("Where the generated test kit is written")
        )
        loadDevices()
        detectButton.addActionListener { detectFromProject() }
        init()
    }

    /** The Language entry for a stored preference. Assigning a value the combo's model doesn't
     *  hold is a silent no-op that leaves whatever was showing, so the mapping must be total:
     *  a settings file from an older build can still carry SWIFT or GO, neither of which has a
     *  codegen target, and those land on the default rather than on nothing. */
    private fun dialogLanguage(language: MTRSettings.Language): String = when (language) {
        MTRSettings.Language.JAVA -> "java"
        MTRSettings.Language.KOTLIN -> "kotlin"
        MTRSettings.Language.JAVASCRIPT, MTRSettings.Language.TYPESCRIPT -> "javascript"
        else -> "python"
    }

    /** Pick a project folder, detect its app(s) via the engine, and fill the form. */
    private fun detectFromProject() {
        // Use the IDE's own file chooser (consistent look, remembers the last dir) instead of
        // a bare Swing JFileChooser.
        val descriptor = FileChooserDescriptorFactory.createSingleFolderDescriptor()
            .withTitle("Select the Project Folder")
            .withDescription("Detect the app(s) in this project and fill the form")
        val dir = FileChooser.chooseFile(descriptor, project, null) ?: return
        val path = dir.path
        detectButton.isEnabled = false
        setErrorText(null)
        (object : SwingWorker<JsonArray?, Void>() {
            // Distinguish "engine couldn't answer" (null) from "no app in that folder" (empty
            // list) — otherwise a dead engine tells the user their valid project has no app.
            private var failed = false

            override fun doInBackground(): JsonArray? = try {
                val client = ApplicationManager.getApplication()
                    .getService(MTRDaemonService::class.java).getClient()
                if (client == null) {
                    failed = true
                    null
                } else {
                    client.call("project/detect", mapOf("path" to path)).getResultOrThrow().getAsJsonArray("apps")
                }
            } catch (e: Exception) {
                failed = true
                null
            }

            override fun done() {
                detectButton.isEnabled = true
                if (failed) {
                    setErrorText("Couldn't detect apps — is the engine running? Try again in a moment.")
                    return
                }
                val apps = get()
                detectedApps = apps?.map { it.asJsonObject } ?: emptyList()
                generateAllCheck.isVisible = detectedApps.size > 1
                generateAllCheck.text = "Generate all ${detectedApps.size} detected apps in parallel"
                when {
                    apps == null || apps.size() == 0 -> setErrorText("No Android or iOS app found in that folder.")
                    apps.size() == 1 -> fillFromApp(apps[0].asJsonObject)
                    else -> chooseApp(apps)
                }
            }
        }).execute()
    }

    /** Several apps in the project — let the user pick which one to configure. */
    private fun chooseApp(apps: JsonArray) {
        val labels = apps.map {
            val a = it.asJsonObject
            "${a.get("package").asString} (${a.get("platform").asString})"
        }
        JBPopupFactory.getInstance()
            .createPopupChooserBuilder(labels)
            .setTitle("Which app?")
            .setItemChosenCallback { chosen ->
                val idx = labels.indexOf(chosen)
                if (idx >= 0) fillFromApp(apps[idx].asJsonObject)
            }
            .createPopup()
            .showInCenterOf(rootPane)
    }

    /** Fill package / platform / build from a detected app, and auto-pick a connected
     *  device of that platform so an Android app lands on an Android device, not an iOS one. */
    private fun fillFromApp(app: JsonObject) {
        packageField.text = app.get("package")?.asString ?: ""
        val platform = app.get("platform")?.asString
        if (platform != null) {
            platformCombo.selectedItem = platform
            devicePlatforms.entries.firstOrNull { it.value == platform }?.let { udidCombo.selectedItem = it.key }
        }
        val build = app.get("build_path")
        if (build != null && !build.isJsonNull) buildPathField.text = build.asString
    }

    /** Populate the Device dropdown from the engine's running/connected devices, shown
     *  by friendly name. Best-effort: if the engine isn't running the combo stays empty
     *  and editable, so a UDID can still be typed. Auto-selects the only device. */
    private fun loadDevices() {
        udidCombo.renderer = SimpleListCellRenderer.create("") { udid ->
            val name = deviceNames[udid]
            if (name.isNullOrBlank()) udid else "$name — $udid"
        }
        val app = ApplicationManager.getApplication()
        // The device enumeration (adb / simctl) can take seconds — do it off the EDT via the
        // shared DeviceList loader (no more hand-rolled device/list parsing here), then populate
        // the editable combo back on the EDT so opening the dialog never hangs.
        app.executeOnPooledThread {
            val found = try {
                DeviceList.load("all").filter { it.status != "shutdown" } // running only
            } catch (_: Exception) {
                emptyList() // engine down / no devices — leave the combo empty and editable
            }
            app.invokeLater({
                for (device in found) {
                    deviceNames[device.id] = device.name
                    devicePlatforms[device.id] = device.platform
                    udidCombo.addItem(device.id)
                }
                if (udidCombo.itemCount == 1) udidCombo.selectedIndex = 0 else udidCombo.selectedItem = ""
            }, ModalityState.any())
        }
    }

    /** The chosen device UDID — the selected dropdown item or a manually typed value. */
    private fun selectedUdid(): String =
        (udidCombo.editor.item ?: udidCombo.selectedItem)?.toString()?.trim().orEmpty()

    private fun comboBox(vararg items: String): ComboBox<String> = ComboBox(items.toList().toTypedArray())

    /** Repopulate the Framework list for the current language, dropping frameworks
     *  that don't apply to the current platform (Espresso is Android-only). Keeps
     *  the prior selection when it's still valid. */
    private fun reloadFrameworks() {
        val language = languageCombo.selectedItem as String
        val platform = platformCombo.selectedItem as String
        val previous = frameworkCombo.selectedItem as String?
        frameworkCombo.removeAllItems()
        for ((label, target) in frameworksByLanguage.getValue(language)) {
            if (platform == "ios" && target == "kotlin_espresso") continue // Android-only
            frameworkCombo.addItem(label)
        }
        if (previous != null && (0 until frameworkCombo.itemCount).any { frameworkCombo.getItemAt(it) == previous }) {
            frameworkCombo.selectedItem = previous
        }
    }

    /** iOS always drives via Appium/XCUITest, so the Android backend choice is
     *  irrelevant there — force Appium and disable it. */
    private fun applyPlatform() {
        val ios = platformCombo.selectedItem == "ios"
        if (ios) driverCombo.selectedItem = "appium"
        driverCombo.isEnabled = !ios
    }

    override fun createCenterPanel(): JComponent {
        // One Kotlin UI DSL panel for the whole form: the essentials up top, then Advanced as
        // a collapsibleGroup that starts collapsed. The group must be a top-level element of
        // this panel (not a nested panel{} dropped into a FormBuilder) or the dialog won't
        // re-pack when it toggles — which left a large empty area under a collapsed Advanced.
        return panel {
            row { cell(detectButton) }
            row { cell(generateAllCheck) }
            row("App package / bundle id:") { cell(packageField) }
            row("Platform:") { cell(platformCombo) }
            row("Device:") { cell(udidCombo) }
            row("Language / target:") { cell(languageCombo) }
            row("Framework:") { cell(frameworkCombo) }
            row("Output directory:") { cell(outputField) }
            row { cell(newProjectCheck) }
            collapsibleGroup("Advanced") {
                row("Android backend:") { cell(driverCombo) }
                row("Appium server:") { cell(serverField) }
                row("iOS launch args (space-separated):") { cell(launchArgsField) }
                separator()
                row("Login username (optional):") { cell(loginUserField) }
                row("Login password:") { cell(loginPassField) }
                row("Login submit button:") { cell(loginSubmitField) }
                separator()
                row("Install build first (.apk / .app):") { cell(buildPathField) }
                row { cell(uninstallAfterCheck) }
                row { cell(fuzzCheck) }
                separator()
                row("Max crawl steps:") { cell(maxStepsField) }
                row("Max crawl depth:") { cell(maxDepthField) }
            }.expanded = false
        }
    }

    override fun doValidate(): ValidationInfo? {
        if (packageField.text.isNullOrBlank()) {
            return ValidationInfo("App package / bundle id is required", packageField)
        }
        // A known device must match the chosen platform — an Android crawl can't drive an iOS
        // device. Only enforced for a device the engine listed; a hand-typed UDID has no platform.
        val platform = platformCombo.selectedItem as String
        val devicePlatform = devicePlatforms[selectedUdid()]
        if (devicePlatform != null && devicePlatform != platform) {
            return ValidationInfo("That device is $devicePlatform, but the platform is set to $platform", udidCombo)
        }
        // "Generate all" runs kit/generateMany, which has no install or cleanup step: the
        // action's install → crawl → uninstall orchestration belongs to the single-app path
        // only. Say so here rather than dropping the options silently — "Detect from project"
        // auto-fills the build path, so the combination is one click away, and the crawls
        // would then run against whatever build already happens to be on each device.
        if (generateAllCheck.isVisible && generateAllCheck.isSelected) {
            if (buildPathField.text.isNotBlank()) {
                return ValidationInfo(
                    "\"Install build first\" isn't supported with \"Generate all detected apps\" — " +
                        "install the builds yourself, or clear this field",
                    buildPathField,
                )
            }
            if (uninstallAfterCheck.isSelected) {
                return ValidationInfo(
                    "\"Uninstall the app after crawling\" isn't supported with \"Generate all detected apps\"",
                    uninstallAfterCheck,
                )
            }
        }
        // "Install build first" needs a target device — catch it here instead of after the
        // dialog closes (the action rejected it with a notification and made you reopen).
        if (buildPathField.text.isNotBlank() && selectedUdid().isBlank()) {
            return ValidationInfo("Choose a device (UDID) to install the build on", udidCombo)
        }
        // Reject garbage in the crawl limits instead of silently coercing it to the default.
        positiveIntError(maxStepsField, "Max crawl steps")?.let { return it }
        positiveIntError(maxDepthField, "Max crawl depth")?.let { return it }
        return null
    }

    /** [ValidationInfo] when [field] holds something other than a positive whole number, else
     *  null. Blank is allowed — an empty field falls back to the default in [params]. */
    private fun positiveIntError(field: JBTextField, label: String): ValidationInfo? {
        val text = field.text.trim()
        if (text.isEmpty()) return null
        val n = text.toIntOrNull()
        return if (n == null || n <= 0) ValidationInfo("$label must be a positive whole number", field) else null
    }

    /** The collected config, ready to send as `kit/generate` params. */
    private fun resolveOutput(out: String): String = resolveOutputPath(out, project.basePath)

    companion object {
        /** Resolve a relative output dir against the project root, so the kit lands where the
         *  user can find it — not in the IDE's working directory (which for a GUI launch is `/`
         *  or the install dir), where the engine would either fail mkdir or hide the result.
         *  An absolute path, or a relative one with no project root, is returned unchanged. */
        fun resolveOutputPath(out: String, basePath: String?): String {
            if (File(out).isAbsolute || basePath == null) return out
            return File(basePath, out).path
        }
    }

    fun params(): Map<String, Any> {
        val params = LinkedHashMap<String, Any>()
        params["package"] = packageField.text.trim()
        params["platform"] = platformCombo.selectedItem as String
        params["driver"] = driverCombo.selectedItem as String
        params["targets"] = listOf(selectedTarget())
        params["output"] = resolveOutput(outputField.text.trim().ifEmpty { "mobile-tests" })
        params["scaffold"] = newProjectCheck.isSelected
        params["fuzz"] = fuzzCheck.isSelected  // opt-in: adversarial-input tests per form
        params["server"] = serverField.text.trim()
        selectedUdid().takeIf { it.isNotBlank() }?.let { params["udid"] = it }
        params["max_steps"] = maxStepsField.text.trim().toIntOrNull() ?: 40
        params["max_depth"] = maxDepthField.text.trim().toIntOrNull() ?: 8
        // iOS launch arguments (e.g. -MyAppStartUnlocked 1) — passed to the app on
        // start so the crawl begins past a gate. The engine reads them as
        // `process_args` (see pipeline._make_driver).
        val launchArgs = launchArgsField.text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (launchArgs.isNotEmpty()) params["process_args"] = launchArgs
        // Login waypoint: when the crawl first hits a screen with inputs, fill the
        // username/password and tap the submit — so it can pass the sign-in gate and
        // map the app behind it. The engine reads `waypoints` (framework.crawler.
        // waypoints); the password is only read here to build the param, never stored.
        val loginUser = loginUserField.text.trim()
        if (loginUser.isNotEmpty()) {
            val loginPass = String(loginPassField.password)
            val submit = loginSubmitField.text.trim().ifEmpty { "log in" }
            params["waypoints"] = listOf(
                mapOf(
                    "when" to mapOf("has_input" to true),
                    "action" to "fill",
                    "data" to mapOf(
                        "fields" to mapOf("user" to loginUser, "password" to loginPass),
                        "submit" to submit,
                    ),
                ),
            )
        }
        return params
    }

    /** The codegen target for the selected language + framework — always a valid
     *  pairing because the Framework list only offers that language's frameworks. */
    private fun selectedTarget(): String {
        val language = languageCombo.selectedItem as String
        val frameworks = frameworksByLanguage.getValue(language)
        val label = frameworkCombo.selectedItem as String?
        return frameworks.firstOrNull { it.first == label }?.second ?: frameworks.first().second
    }

    /** A build (.apk / .app) to install on the device before crawling, or "" for none. */
    fun buildPathToInstall(): String = buildPathField.text.trim()

    /** Whether to uninstall the app once the crawl finishes (install → crawl → cleanup). */
    fun uninstallAfter(): Boolean = uninstallAfterCheck.isSelected

    /** The device the build installs on / the app uninstalls from — the Appium UDID, or "" if unset. */
    fun deviceId(): String = selectedUdid()

    /** When "generate all detected apps" is on, a kit/generate config per detected app —
     *  each with its own package/platform, a device of that platform, and its own output
     *  subdir — sharing the stack/output/budget/login from the form. Empty otherwise (the
     *  caller then does the normal single-app generate). */
    fun multiAppConfigs(): List<Map<String, Any>> {
        if (!generateAllCheck.isVisible || !generateAllCheck.isSelected || detectedApps.size < 2) return emptyList()
        val base = params()
        val baseOutput = (base["output"] as? String) ?: "mobile-tests"
        // Hand each app a DISTINCT device of its platform — two Android apps crawled in
        // parallel on the same emulator would fight over one Appium session. Devices are
        // consumed as assigned; an app with none left is emitted without a udid, and the
        // engine's auto-boot/degrade handles it (better serialized than colliding).
        val freeByPlatform: MutableMap<String, ArrayDeque<String>> = HashMap()
        for ((udid, platform) in devicePlatforms) {
            freeByPlatform.getOrPut(platform) { ArrayDeque() }.add(udid)
        }
        return detectedApps.map { app ->
            val pkg = app.get("package")?.asString ?: ""
            val platform = app.get("platform")?.asString ?: "android"
            val cfg = LinkedHashMap(base)
            cfg["package"] = pkg
            cfg["platform"] = platform
            cfg["output"] = "$baseOutput/$pkg"
            val device = freeByPlatform[platform]?.removeFirstOrNull()
            if (device != null) cfg["udid"] = device else cfg.remove("udid")
            cfg
        }
    }

    /** The app package / bundle id — the uninstall target. */
    fun appPackage(): String = packageField.text.trim()

    /** The target platform (android / ios) for install / uninstall RPCs. */
    fun platform(): String = platformCombo.selectedItem as String
}
