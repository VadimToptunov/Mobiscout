package com.mobiletest.recorder.wizard

import com.intellij.ide.wizard.AbstractWizard
import com.intellij.ide.wizard.StepAdapter
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.mobiletest.recorder.settings.MTRSettings
import javax.swing.JComponent

/**
 * Setup Wizard for Mobile Test Recorder initial configuration.
 *
 * Guides users through the essential setup steps:
 * 1. Source Code Configuration - Do you have source code?
 * 2. Build Configuration - Where are your builds?
 * 3. Analysis Options - What should we analyze?
 * 4. Framework Selection - Test framework and language
 * 5. Summary - Review and finish
 */
class SetupWizard(project: Project?) : AbstractWizard<SetupWizardStep>("Mobile Test Recorder Setup", project) {

    private val settings = MTRSettings.getInstance()
    private val wizardModel = SetupWizardModel()

    init {
        addStep(SourceCodeStep(wizardModel))
        addStep(BuildConfigStep(wizardModel))
        addStep(AnalysisOptionsStep(wizardModel))
        addStep(FrameworkSelectionStep(wizardModel))
        addStep(SummaryStep(wizardModel))

        init()
    }

    override fun getHelpID(): String = "mtr.setup.wizard"

    override fun doOKAction() {
        // Apply wizard settings to persistent storage
        applySettings()
        super.doOKAction()
    }

    private fun applySettings() {
        settings.hasSourceCode = wizardModel.hasSourceCode
        settings.sourceCodePath = wizardModel.sourceCodePath
        settings.state.buildPath = wizardModel.buildPath
        settings.targetPlatform = wizardModel.targetPlatform
        settings.analyzeApiLogs = wizardModel.analyzeApiLogs
        settings.enableSecurityScan = wizardModel.enableSecurityScan
        settings.enablePerformanceAnalysis = wizardModel.enablePerformanceAnalysis
        settings.state.createNewFramework = wizardModel.createNewFramework
        settings.state.existingFrameworkPath = wizardModel.existingFrameworkPath
        settings.preferredLanguage = wizardModel.preferredLanguage
        settings.testFramework = wizardModel.testFramework
        settings.automationBackend = wizardModel.automationBackend
    }

    companion object {
        /**
         * Show the setup wizard and return true if completed successfully.
         */
        fun showWizard(project: Project?): Boolean {
            val wizard = SetupWizard(project)
            return wizard.showAndGet()
        }

        /**
         * Check if setup wizard should be shown (first run or incomplete setup).
         */
        fun shouldShowWizard(): Boolean {
            val settings = MTRSettings.getInstance()
            // Show wizard if no build path is configured (essential setting)
            return settings.state.buildPath.isEmpty()
        }
    }
}

/**
 * Model to hold wizard state across all steps.
 */
data class SetupWizardModel(
    var hasSourceCode: Boolean = false,
    var sourceCodePath: String = "",
    var buildPath: String = "",
    var targetPlatform: MTRSettings.Platform = MTRSettings.Platform.ANDROID,

    var analyzeApiLogs: Boolean = true,
    var enableSecurityScan: Boolean = false,
    var enablePerformanceAnalysis: Boolean = false,

    var createNewFramework: Boolean = true,
    var existingFrameworkPath: String = "",
    var preferredLanguage: MTRSettings.Language = MTRSettings.Language.PYTHON,
    var testFramework: MTRSettings.TestFramework = MTRSettings.TestFramework.PYTEST,
    var automationBackend: MTRSettings.AutomationBackend = MTRSettings.AutomationBackend.APPIUM
)

/**
 * Base class for wizard steps.
 */
abstract class SetupWizardStep(protected val model: SetupWizardModel) : StepAdapter() {

    protected abstract val stepTitle: String
    protected abstract val stepDescription: String

    abstract fun createStepComponent(): JComponent

    abstract fun applyToModel()

    override fun getComponent(): JComponent = createStepComponent()

    override fun _commit(finishChosen: Boolean) {
        applyToModel()
    }
}
