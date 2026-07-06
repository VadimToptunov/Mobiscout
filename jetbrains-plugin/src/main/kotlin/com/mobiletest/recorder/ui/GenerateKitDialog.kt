package com.mobiletest.recorder.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
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
 */
class GenerateKitDialog(project: Project) : DialogWrapper(project) {

    private val settings = MTRSettings.getInstance()

    private val packageField = JBTextField(30)
    private val platformCombo = comboBox("android", "ios")
    private val driverCombo = comboBox("adb", "appium")
    private val languageCombo = comboBox("python", "java", "javascript", "kotlin")
    private val frameworkField = JBTextField(20)
    private val bddCheck = JBCheckBox("BDD (Gherkin) style", false)
    private val outputField = JBTextField(30)
    private val newProjectCheck = JBCheckBox("Create a new runnable project (scaffold)", settings.createNewFramework)
    private val udidField = JBTextField(20)
    private val serverField = JBTextField("http://localhost:4723", 24)
    private val maxStepsField = JBTextField("40", 5)

    init {
        title = "Generate Test Kit"
        platformCombo.selectedItem = if (settings.targetPlatform.name.equals("IOS", true)) "ios" else "android"
        languageCombo.selectedItem = settings.preferredLanguage.name.lowercase().let {
            if (it == "typescript") "javascript" else it
        }
        frameworkField.text = settings.testFramework.name.lowercase()
        outputField.text = if (settings.createNewFramework) "mobile-tests" else settings.existingFrameworkPath
        init()
    }

    private fun comboBox(vararg items: String): ComboBox<String> = ComboBox(items.toList().toTypedArray())

    override fun createCenterPanel(): JComponent {
        val panel: JPanel = FormBuilder.createFormBuilder()
            .addLabeledComponent("App package / bundle id:", packageField)
            .addLabeledComponent("Platform:", platformCombo)
            .addLabeledComponent("Android backend:", driverCombo)
            .addLabeledComponent("Language:", languageCombo)
            .addLabeledComponent("Framework:", frameworkField)
            .addComponent(bddCheck)
            .addSeparator()
            .addLabeledComponent("Output directory:", outputField)
            .addComponent(newProjectCheck)
            .addSeparator()
            .addLabeledComponent("Device UDID (Appium):", udidField)
            .addLabeledComponent("Appium server:", serverField)
            .addLabeledComponent("Max crawl steps:", maxStepsField)
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
        val target = codegenTarget(languageCombo.selectedItem as String, frameworkField.text.trim(), bddCheck.isSelected)
        val params = LinkedHashMap<String, Any>()
        params["package"] = packageField.text.trim()
        params["platform"] = platformCombo.selectedItem as String
        params["driver"] = driverCombo.selectedItem as String
        params["targets"] = listOf(target)
        params["output"] = outputField.text.trim().ifEmpty { "mobile-tests" }
        params["scaffold"] = newProjectCheck.isSelected
        params["server"] = serverField.text.trim()
        if (udidField.text.isNotBlank()) params["udid"] = udidField.text.trim()
        params["max_steps"] = maxStepsField.text.trim().toIntOrNull() ?: 40
        return params
    }

    /** Map a language + framework choice onto one of the engine's codegen targets. */
    private fun codegenTarget(language: String, framework: String, bdd: Boolean): String {
        val fw = framework.lowercase()
        return when (language) {
            "python" -> if (bdd) "python_pytest_bdd" else "python_pytest"
            "java" -> if (bdd || fw.contains("cucumber")) "java_cucumber" else "java_testng"
            "kotlin" -> if (fw.contains("espresso")) "kotlin_espresso" else "kotlin_appium"
            else -> if (bdd || fw.contains("cucumber")) "js_cucumber" else "js_webdriverio"
        }
    }
}
