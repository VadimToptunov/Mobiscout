package com.mobiletest.recorder.ui

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.openapi.ui.ValidationInfo
import com.intellij.openapi.ui.popup.JBPopupFactory
import com.intellij.ui.TitledSeparator
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.mobiletest.recorder.settings.MTRSettings
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JFileChooser
import javax.swing.JPanel
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
    )

    // Point at a project folder and fill package/platform/build automatically — the
    // config becomes "confirm what was detected" rather than "type it all".
    private val detectButton = JButton("Detect from project…")
    private val packageField = JBTextField(30)
    private val platformCombo = comboBox("android", "ios")
    private val driverCombo = comboBox("adb", "appium")
    private val languageCombo = comboBox("python", "java", "javascript", "kotlin")
    private val frameworkCombo = ComboBox<String>()
    private val outputField = JBTextField(30)
    private val newProjectCheck = JBCheckBox("Create a new runnable project (scaffold)", settings.createNewFramework)
    // Device is a dropdown of the currently running/connected devices (shown by name),
    // populated from the engine — so you pick "iPhone 17" instead of hunting for a UDID.
    // Still editable, so a device the engine can't see yet can be typed in.
    private val udidCombo = ComboBox<String>().apply { isEditable = true }
    private val deviceNames = HashMap<String, String>() // udid -> friendly name
    private val devicePlatforms = HashMap<String, String>() // udid -> platform
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

    init {
        title = "Generate Test Kit"
        platformCombo.selectedItem = if (settings.targetPlatform.name.equals("IOS", true)) "ios" else "android"
        languageCombo.selectedItem = settings.preferredLanguage.name.lowercase().let {
            if (it == "typescript") "javascript" else it
        }
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
        loadDevices()
        detectButton.addActionListener { detectFromProject() }
        init()
    }

    /** Pick a project folder, detect its app(s) via the engine, and fill the form. */
    private fun detectFromProject() {
        val chooser = JFileChooser().apply {
            dialogTitle = "Select the project folder"
            fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
        }
        if (chooser.showOpenDialog(rootPane) != JFileChooser.APPROVE_OPTION) return
        val path = chooser.selectedFile?.absolutePath ?: return
        detectButton.isEnabled = false
        setErrorText(null)
        (object : SwingWorker<JsonArray?, Void>() {
            override fun doInBackground(): JsonArray? = try {
                com.intellij.openapi.application.ApplicationManager.getApplication()
                    .getService(com.mobiletest.recorder.services.MTRDaemonService::class.java)
                    .getClient()?.call("project/detect", mapOf("path" to path))
                    ?.getResultOrThrow()?.getAsJsonArray("apps")
            } catch (e: Exception) {
                null
            }

            override fun done() {
                detectButton.isEnabled = true
                val apps = get()
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
        udidCombo.renderer = com.intellij.ui.SimpleListCellRenderer.create("") { udid ->
            val name = deviceNames[udid]
            if (name.isNullOrBlank()) udid else "$name — $udid"
        }
        try {
            val daemon = com.intellij.openapi.application.ApplicationManager.getApplication()
                .getService(com.mobiletest.recorder.services.MTRDaemonService::class.java)
            val client = daemon.getClient() ?: return
            val result = client.call("device/list", mapOf("platform" to "all")).getResultOrThrow() ?: return
            val devices = result.getAsJsonArray("devices") ?: return
            for (el in devices) {
                val d = el.asJsonObject
                if ((d.get("status")?.asString ?: "") == "shutdown") continue // running/connected only
                val udid = d.get("id")?.asString ?: continue
                deviceNames[udid] = d.get("name")?.asString ?: ""
                devicePlatforms[udid] = d.get("platform")?.asString ?: ""
                udidCombo.addItem(udid)
            }
            if (udidCombo.itemCount == 1) udidCombo.selectedIndex = 0 else udidCombo.selectedItem = ""
        } catch (_: Exception) {
            // engine down / no devices — leave the combo empty and editable
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
        // Essentials up top (what you set every run), then everything else under an
        // "Advanced" heading whose defaults are fine for the common case — so the form
        // reads as "app, device, language → Generate" without hiding any knob.
        val panel: JPanel = FormBuilder.createFormBuilder()
            .addComponent(detectButton)
            .addLabeledComponent("App package / bundle id:", packageField)
            .addLabeledComponent("Platform:", platformCombo)
            .addLabeledComponent("Device:", udidCombo)
            .addLabeledComponent("Language:", languageCombo)
            .addLabeledComponent("Framework:", frameworkCombo)
            .addLabeledComponent("Output directory:", outputField)
            .addComponent(newProjectCheck)
            .addComponent(TitledSeparator("Advanced"))
            .addLabeledComponent("Android backend:", driverCombo)
            .addLabeledComponent("Appium server:", serverField)
            .addLabeledComponent("iOS launch args (space-separated):", launchArgsField)
            .addSeparator()
            .addLabeledComponent("Login username (optional):", loginUserField)
            .addLabeledComponent("Login password:", loginPassField)
            .addLabeledComponent("Login submit button:", loginSubmitField)
            .addSeparator()
            .addLabeledComponent("Install build first (.apk / .app):", buildPathField)
            .addComponent(uninstallAfterCheck)
            .addSeparator()
            .addLabeledComponent("Max crawl steps:", maxStepsField)
            .addLabeledComponent("Max crawl depth:", maxDepthField)
            .panel
        return panel
    }

    override fun doValidate(): ValidationInfo? {
        if (packageField.text.isNullOrBlank()) {
            return ValidationInfo("App package / bundle id is required", packageField)
        }
        return null
    }

    /** The collected config, ready to send as `kit/generate` params. */
    fun params(): Map<String, Any> {
        val params = LinkedHashMap<String, Any>()
        params["package"] = packageField.text.trim()
        params["platform"] = platformCombo.selectedItem as String
        params["driver"] = driverCombo.selectedItem as String
        params["targets"] = listOf(selectedTarget())
        params["output"] = outputField.text.trim().ifEmpty { "mobile-tests" }
        params["scaffold"] = newProjectCheck.isSelected
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

    /** The app package / bundle id — the uninstall target. */
    fun appPackage(): String = packageField.text.trim()

    /** The target platform (android / ios) for install / uninstall RPCs. */
    fun platform(): String = platformCombo.selectedItem as String
}
