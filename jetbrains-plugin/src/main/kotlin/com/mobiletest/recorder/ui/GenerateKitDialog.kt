package com.mobiletest.recorder.ui

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.openapi.ui.ValidationInfo
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.mobiletest.recorder.settings.MTRSettings
import javax.swing.JComponent
import javax.swing.JPanel

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
class GenerateKitDialog(project: Project) : DialogWrapper(project) {

    private val settings = MTRSettings.getInstance()

    // Language -> the frameworks it actually has, each as (menu label -> codegen
    // target id). BDD is just a Gherkin framework here, not a separate toggle.
    private val frameworksByLanguage: Map<String, List<Pair<String, String>>> = mapOf(
        "python" to listOf("pytest" to "python_pytest", "pytest-bdd (Gherkin)" to "python_pytest_bdd"),
        "java" to listOf("TestNG" to "java_testng", "Cucumber (Gherkin)" to "java_cucumber"),
        "kotlin" to listOf("Appium" to "kotlin_appium", "Espresso (Android)" to "kotlin_espresso"),
        "javascript" to listOf("WebdriverIO" to "js_webdriverio", "Cucumber (Gherkin)" to "js_cucumber"),
    )

    private val packageField = JBTextField(30)
    private val platformCombo = comboBox("android", "ios")
    private val driverCombo = comboBox("adb", "appium")
    private val languageCombo = comboBox("python", "java", "javascript", "kotlin")
    private val frameworkCombo = ComboBox<String>()
    private val outputField = JBTextField(30)
    private val newProjectCheck = JBCheckBox("Create a new runnable project (scaffold)", settings.createNewFramework)
    private val udidField = JBTextField(20)
    private val serverField = JBTextField("http://localhost:4723", 24)
    private val maxStepsField = JBTextField("40", 5)
    private val maxDepthField = JBTextField("8", 5)
    private val launchArgsField = JBTextField(30)

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

        // .apk is a file, .app is a bundle directory — allow either. (Same
        // addBrowseFolderListener overload the setup-wizard steps use; the 2-arg
        // (project, descriptor) form isn't in this platform build.)
        buildPathField.addBrowseFolderListener(
            "Select a Build (.apk / .app)",
            "The build is installed on the device (UDID) before crawling",
            project,
            FileChooserDescriptorFactory.createSingleFileOrFolderDescriptor()
        )
        init()
    }

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
        val panel: JPanel = FormBuilder.createFormBuilder()
            .addLabeledComponent("App package / bundle id:", packageField)
            .addLabeledComponent("Platform:", platformCombo)
            .addLabeledComponent("Android backend:", driverCombo)
            .addLabeledComponent("Language:", languageCombo)
            .addLabeledComponent("Framework:", frameworkCombo)
            .addSeparator()
            .addLabeledComponent("Output directory:", outputField)
            .addComponent(newProjectCheck)
            .addSeparator()
            .addLabeledComponent("Device UDID (Appium):", udidField)
            .addLabeledComponent("Appium server:", serverField)
            .addLabeledComponent("iOS launch args (space-separated):", launchArgsField)
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
        if (udidField.text.isNotBlank()) params["udid"] = udidField.text.trim()
        params["max_steps"] = maxStepsField.text.trim().toIntOrNull() ?: 40
        params["max_depth"] = maxDepthField.text.trim().toIntOrNull() ?: 8
        // iOS launch arguments (e.g. -MyAppStartUnlocked 1) — passed to the app on
        // start so the crawl begins past a gate. The engine reads them as
        // `process_args` (see pipeline._make_driver).
        val launchArgs = launchArgsField.text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (launchArgs.isNotEmpty()) params["process_args"] = launchArgs
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
    fun deviceId(): String = udidField.text.trim()

    /** The app package / bundle id — the uninstall target. */
    fun appPackage(): String = packageField.text.trim()

    /** The target platform (android / ios) for install / uninstall RPCs. */
    fun platform(): String = platformCombo.selectedItem as String
}
