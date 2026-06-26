package com.mobiletest.recorder.wizard

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBRadioButton
import com.intellij.util.ui.JBUI
import com.mobiletest.recorder.settings.MTRSettings
import java.awt.*
import javax.swing.*

/**
 * Step 1: Source Code Configuration
 */
class SourceCodeStep(model: SetupWizardModel) : SetupWizardStep(model) {

    override val stepTitle = "Source Code"
    override val stepDescription = "Do you have access to the mobile app source code?"

    private val yesRadio = JBRadioButton("Yes, I have access to source code")
    private val noRadio = JBRadioButton("No, I only have the build (.apk/.ipa)")
    private val sourcePathField = TextFieldWithBrowseButton()
    private val platformCombo = ComboBox(MTRSettings.Platform.values())

    override fun createStepComponent(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints().apply {
            gridx = 0
            gridy = 0
            anchor = GridBagConstraints.WEST
            fill = GridBagConstraints.HORIZONTAL
            insets = JBUI.insets(5, 10)
        }

        // Header
        panel.add(createHeaderLabel("Source Code Access"), gbc)
        gbc.gridy++

        panel.add(JBLabel(
            "<html>Having source code access enables advanced features like static analysis,<br>" +
            "intelligent Page Object generation, and API endpoint extraction.</html>"
        ), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(15, 10, 5, 10)

        // Radio buttons
        val buttonGroup = ButtonGroup()
        buttonGroup.add(yesRadio)
        buttonGroup.add(noRadio)

        panel.add(yesRadio, gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(5, 10)

        // Source path field (enabled when yes is selected)
        val sourcePanel = JPanel(BorderLayout(5, 0))
        sourcePanel.add(JBLabel("Source directory:"), BorderLayout.WEST)
        sourcePathField.addBrowseFolderListener(
            "Select Source Code Directory",
            "Choose the root directory of your mobile app source code",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )
        sourcePanel.add(sourcePathField, BorderLayout.CENTER)
        gbc.insets = JBUI.insets(5, 30, 5, 10)
        panel.add(sourcePanel, gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(15, 10, 5, 10)

        panel.add(noRadio, gbc)
        gbc.gridy++

        // Platform selection
        gbc.insets = JBUI.insets(20, 10, 5, 10)
        panel.add(createHeaderLabel("Target Platform"), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(5, 10)

        val platformPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        platformPanel.add(JBLabel("Platform: "))
        platformPanel.add(platformCombo)
        panel.add(platformPanel, gbc)
        gbc.gridy++

        // Filler
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH
        panel.add(JPanel(), gbc)

        // Setup listeners
        yesRadio.addActionListener { sourcePathField.isEnabled = true }
        noRadio.addActionListener { sourcePathField.isEnabled = false }

        // Set initial state
        if (model.hasSourceCode) {
            yesRadio.isSelected = true
            sourcePathField.isEnabled = true
        } else {
            noRadio.isSelected = true
            sourcePathField.isEnabled = false
        }
        sourcePathField.text = model.sourceCodePath
        platformCombo.selectedItem = model.targetPlatform

        return panel
    }

    override fun applyToModel() {
        model.hasSourceCode = yesRadio.isSelected
        model.sourceCodePath = sourcePathField.text
        model.targetPlatform = platformCombo.selectedItem as MTRSettings.Platform
    }

    private fun createHeaderLabel(text: String): JBLabel {
        val label = JBLabel(text)
        label.font = label.font.deriveFont(Font.BOLD, 14f)
        return label
    }
}

/**
 * Step 2: Build Configuration
 */
class BuildConfigStep(model: SetupWizardModel) : SetupWizardStep(model) {

    override val stepTitle = "Build Configuration"
    override val stepDescription = "Where are your application builds located?"

    private val buildPathField = TextFieldWithBrowseButton()

    override fun createStepComponent(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints().apply {
            gridx = 0
            gridy = 0
            anchor = GridBagConstraints.WEST
            fill = GridBagConstraints.HORIZONTAL
            insets = JBUI.insets(5, 10)
            weightx = 1.0
        }

        // Header
        panel.add(createHeaderLabel("Application Builds"), gbc)
        gbc.gridy++

        panel.add(JBLabel(
            "<html>Specify the directory containing your .apk (Android) or .ipa (iOS) files.<br>" +
            "These builds will be used for testing and analysis.</html>"
        ), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(15, 10, 5, 10)

        // Build path
        val buildPanel = JPanel(BorderLayout(5, 0))
        buildPanel.add(JBLabel("Build directory:"), BorderLayout.WEST)
        buildPathField.addBrowseFolderListener(
            "Select Build Directory",
            "Choose the directory containing .apk or .ipa files",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )
        buildPanel.add(buildPathField, BorderLayout.CENTER)
        panel.add(buildPanel, gbc)
        gbc.gridy++

        // Tips
        gbc.insets = JBUI.insets(20, 10, 5, 10)
        panel.add(createHeaderLabel("Tips"), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(5, 10)

        panel.add(JBLabel(
            "<html>" +
            "• For Android: Usually in <code>app/build/outputs/apk/</code><br>" +
            "• For iOS: Usually in <code>DerivedData/Build/Products/</code><br>" +
            "• You can also point to a CI artifacts directory</html>"
        ), gbc)
        gbc.gridy++

        // Filler
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH
        panel.add(JPanel(), gbc)

        // Set initial state
        buildPathField.text = model.buildPath

        return panel
    }

    override fun applyToModel() {
        model.buildPath = buildPathField.text
    }

    private fun createHeaderLabel(text: String): JBLabel {
        val label = JBLabel(text)
        label.font = label.font.deriveFont(Font.BOLD, 14f)
        return label
    }
}

/**
 * Step 3: Analysis Options
 */
class AnalysisOptionsStep(model: SetupWizardModel) : SetupWizardStep(model) {

    override val stepTitle = "Analysis Options"
    override val stepDescription = "What should we analyze?"

    private val apiLogsCheckbox = JBCheckBox("Analyze API logs for endpoint discovery")
    private val securityCheckbox = JBCheckBox("Enable security vulnerability scanning")
    private val performanceCheckbox = JBCheckBox("Enable performance analysis")

    override fun createStepComponent(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints().apply {
            gridx = 0
            gridy = 0
            anchor = GridBagConstraints.WEST
            fill = GridBagConstraints.HORIZONTAL
            insets = JBUI.insets(5, 10)
            weightx = 1.0
        }

        // Header
        panel.add(createHeaderLabel("Analysis Features"), gbc)
        gbc.gridy++

        panel.add(JBLabel(
            "<html>Select the analysis features you want to enable.<br>" +
            "You can change these settings later in Preferences.</html>"
        ), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(15, 10, 5, 10)

        // API Logs
        panel.add(apiLogsCheckbox, gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(2, 30, 5, 10)
        panel.add(JBLabel(
            "<html><font color='gray'>Intercept network traffic to discover API endpoints<br>" +
            "and automatically generate API test stubs.</font></html>"
        ), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(10, 10, 5, 10)

        // Security
        panel.add(securityCheckbox, gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(2, 30, 5, 10)
        panel.add(JBLabel(
            "<html><font color='gray'>Scan for OWASP Mobile Top 10 vulnerabilities,<br>" +
            "insecure storage, hardcoded secrets, and more.</font></html>"
        ), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(10, 10, 5, 10)

        // Performance
        panel.add(performanceCheckbox, gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(2, 30, 5, 10)
        panel.add(JBLabel(
            "<html><font color='gray'>Monitor CPU, memory, and battery usage during<br>" +
            "test execution and identify performance bottlenecks.</font></html>"
        ), gbc)
        gbc.gridy++

        // Filler
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH
        panel.add(JPanel(), gbc)

        // Set initial state
        apiLogsCheckbox.isSelected = model.analyzeApiLogs
        securityCheckbox.isSelected = model.enableSecurityScan
        performanceCheckbox.isSelected = model.enablePerformanceAnalysis

        return panel
    }

    override fun applyToModel() {
        model.analyzeApiLogs = apiLogsCheckbox.isSelected
        model.enableSecurityScan = securityCheckbox.isSelected
        model.enablePerformanceAnalysis = performanceCheckbox.isSelected
    }

    private fun createHeaderLabel(text: String): JBLabel {
        val label = JBLabel(text)
        label.font = label.font.deriveFont(Font.BOLD, 14f)
        return label
    }
}

/**
 * Step 4: Framework Selection
 */
class FrameworkSelectionStep(model: SetupWizardModel) : SetupWizardStep(model) {

    override val stepTitle = "Test Framework"
    override val stepDescription = "Configure your test framework preferences"

    private val createNewRadio = JBRadioButton("Create new test framework structure")
    private val useExistingRadio = JBRadioButton("Integrate with existing framework")
    private val existingPathField = TextFieldWithBrowseButton()
    private val languageCombo = ComboBox(MTRSettings.Language.values())
    private val testFrameworkCombo = ComboBox(MTRSettings.TestFramework.values())
    private val backendCombo = ComboBox(MTRSettings.AutomationBackend.values())

    override fun createStepComponent(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints().apply {
            gridx = 0
            gridy = 0
            anchor = GridBagConstraints.WEST
            fill = GridBagConstraints.HORIZONTAL
            insets = JBUI.insets(5, 10)
            weightx = 1.0
        }

        // Framework creation
        panel.add(createHeaderLabel("Framework Setup"), gbc)
        gbc.gridy++

        val buttonGroup = ButtonGroup()
        buttonGroup.add(createNewRadio)
        buttonGroup.add(useExistingRadio)

        gbc.insets = JBUI.insets(10, 10, 5, 10)
        panel.add(createNewRadio, gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(5, 10)
        panel.add(useExistingRadio, gbc)
        gbc.gridy++

        // Existing framework path
        val existingPanel = JPanel(BorderLayout(5, 0))
        existingPanel.add(JBLabel("Framework path:"), BorderLayout.WEST)
        existingPathField.addBrowseFolderListener(
            "Select Existing Framework",
            "Choose the root directory of your existing test framework",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )
        existingPanel.add(existingPathField, BorderLayout.CENTER)
        gbc.insets = JBUI.insets(5, 30, 10, 10)
        panel.add(existingPanel, gbc)
        gbc.gridy++

        // Language
        gbc.insets = JBUI.insets(15, 10, 5, 10)
        panel.add(createHeaderLabel("Code Generation Preferences"), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(5, 10)

        val langPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        langPanel.add(JBLabel("Programming language: "))
        langPanel.add(languageCombo)
        panel.add(langPanel, gbc)
        gbc.gridy++

        // Test framework
        val frameworkPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        frameworkPanel.add(JBLabel("Test framework: "))
        frameworkPanel.add(testFrameworkCombo)
        panel.add(frameworkPanel, gbc)
        gbc.gridy++

        // Automation backend
        val backendPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        backendPanel.add(JBLabel("Automation backend: "))
        backendPanel.add(backendCombo)
        panel.add(backendPanel, gbc)
        gbc.gridy++

        // Filler
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH
        panel.add(JPanel(), gbc)

        // Setup listeners
        createNewRadio.addActionListener { existingPathField.isEnabled = false }
        useExistingRadio.addActionListener { existingPathField.isEnabled = true }

        // Update test framework combo based on language
        languageCombo.addActionListener { updateTestFrameworkOptions() }

        // Set initial state
        if (model.createNewFramework) {
            createNewRadio.isSelected = true
            existingPathField.isEnabled = false
        } else {
            useExistingRadio.isSelected = true
            existingPathField.isEnabled = true
        }
        existingPathField.text = model.existingFrameworkPath
        languageCombo.selectedItem = model.preferredLanguage
        testFrameworkCombo.selectedItem = model.testFramework
        backendCombo.selectedItem = model.automationBackend

        return panel
    }

    private fun updateTestFrameworkOptions() {
        val language = languageCombo.selectedItem as MTRSettings.Language
        val recommended = when (language) {
            MTRSettings.Language.PYTHON -> MTRSettings.TestFramework.PYTEST
            MTRSettings.Language.JAVA -> MTRSettings.TestFramework.JUNIT
            MTRSettings.Language.KOTLIN -> MTRSettings.TestFramework.JUNIT
            MTRSettings.Language.SWIFT -> MTRSettings.TestFramework.XCTEST
            MTRSettings.Language.JAVASCRIPT, MTRSettings.Language.TYPESCRIPT -> MTRSettings.TestFramework.JEST
            MTRSettings.Language.GO -> MTRSettings.TestFramework.GO_TEST
        }
        testFrameworkCombo.selectedItem = recommended
    }

    override fun applyToModel() {
        model.createNewFramework = createNewRadio.isSelected
        model.existingFrameworkPath = existingPathField.text
        model.preferredLanguage = languageCombo.selectedItem as MTRSettings.Language
        model.testFramework = testFrameworkCombo.selectedItem as MTRSettings.TestFramework
        model.automationBackend = backendCombo.selectedItem as MTRSettings.AutomationBackend
    }

    private fun createHeaderLabel(text: String): JBLabel {
        val label = JBLabel(text)
        label.font = label.font.deriveFont(Font.BOLD, 14f)
        return label
    }
}

/**
 * Step 5: Summary
 */
class SummaryStep(model: SetupWizardModel) : SetupWizardStep(model) {

    override val stepTitle = "Summary"
    override val stepDescription = "Review your configuration"

    private lateinit var summaryLabel: JBLabel

    override fun createStepComponent(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints().apply {
            gridx = 0
            gridy = 0
            anchor = GridBagConstraints.WEST
            fill = GridBagConstraints.HORIZONTAL
            insets = JBUI.insets(5, 10)
            weightx = 1.0
        }

        // Header
        panel.add(createHeaderLabel("Configuration Summary"), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(10, 10)

        summaryLabel = JBLabel()
        updateSummary()
        panel.add(summaryLabel, gbc)
        gbc.gridy++

        // Ready message
        gbc.insets = JBUI.insets(20, 10, 5, 10)
        panel.add(createHeaderLabel("Ready to Start!"), gbc)
        gbc.gridy++
        gbc.insets = JBUI.insets(5, 10)

        panel.add(JBLabel(
            "<html>Click <b>Finish</b> to save your configuration and start using<br>" +
            "Mobile Test Recorder. You can modify these settings anytime<br>" +
            "in <b>Preferences → Mobile Test Recorder</b>.</html>"
        ), gbc)
        gbc.gridy++

        // Filler
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH
        panel.add(JPanel(), gbc)

        return panel
    }

    private fun updateSummary() {
        val sourceInfo = if (model.hasSourceCode) {
            "Source code: ${model.sourceCodePath.ifEmpty { "(not set)" }}"
        } else {
            "Source code: No access (will use decompilation)"
        }

        val analysisFeatures = mutableListOf<String>()
        if (model.analyzeApiLogs) analysisFeatures.add("API Log Analysis")
        if (model.enableSecurityScan) analysisFeatures.add("Security Scanning")
        if (model.enablePerformanceAnalysis) analysisFeatures.add("Performance Analysis")
        val analysisInfo = if (analysisFeatures.isEmpty()) "None" else analysisFeatures.joinToString(", ")

        val frameworkInfo = if (model.createNewFramework) {
            "Create new framework"
        } else {
            "Use existing: ${model.existingFrameworkPath.ifEmpty { "(not set)" }}"
        }

        summaryLabel.text = """
            <html>
            <table style='font-size: 12px;'>
                <tr><td><b>Platform:</b></td><td>${model.targetPlatform}</td></tr>
                <tr><td><b>Source:</b></td><td>$sourceInfo</td></tr>
                <tr><td><b>Build path:</b></td><td>${model.buildPath.ifEmpty { "(not set)" }}</td></tr>
                <tr><td><b>Analysis:</b></td><td>$analysisInfo</td></tr>
                <tr><td><b>Framework:</b></td><td>$frameworkInfo</td></tr>
                <tr><td><b>Language:</b></td><td>${model.preferredLanguage}</td></tr>
                <tr><td><b>Test Framework:</b></td><td>${model.testFramework}</td></tr>
                <tr><td><b>Backend:</b></td><td>${model.automationBackend}</td></tr>
            </table>
            </html>
        """.trimIndent()
    }

    override fun applyToModel() {
        // Nothing to apply in summary step
    }

    override fun _commit(finishChosen: Boolean) {
        // Update summary before showing
        updateSummary()
    }

    private fun createHeaderLabel(text: String): JBLabel {
        val label = JBLabel(text)
        label.font = label.font.deriveFont(Font.BOLD, 14f)
        return label
    }
}
