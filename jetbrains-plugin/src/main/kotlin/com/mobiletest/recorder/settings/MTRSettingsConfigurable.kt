package com.mobiletest.recorder.settings

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.TitledSeparator
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import java.awt.BorderLayout
import java.awt.FlowLayout
import javax.swing.*

/**
 * Settings UI for Mobile Test Recorder plugin.
 *
 * Provides comprehensive configuration options organized into sections:
 * - Project Configuration
 * - Analysis Options
 * - Test Framework
 * - Device Configuration
 * - Code Generation
 * - Advanced Settings
 */
class MTRSettingsConfigurable : Configurable {

    private val settings = MTRSettings.getInstance()

    // === Project Configuration ===
    private val hasSourceCodeCheckbox = JBCheckBox("I have access to source code")
    private val sourceCodePathField = TextFieldWithBrowseButton()
    private val buildPathField = TextFieldWithBrowseButton()
    private val platformCombo = ComboBox(MTRSettings.Platform.values())

    // === Analysis Options ===
    private val analyzeApiLogsCheckbox = JBCheckBox("Analyze API logs for endpoint discovery")
    private val securityScanCheckbox = JBCheckBox("Enable security vulnerability scanning")
    private val performanceAnalysisCheckbox = JBCheckBox("Enable performance analysis")

    // === Test Framework ===
    private val createNewFrameworkRadio = JRadioButton("Create new test framework")
    private val useExistingFrameworkRadio = JRadioButton("Integrate with existing framework")
    private val existingFrameworkPathField = TextFieldWithBrowseButton()
    private val languageCombo = ComboBox(MTRSettings.Language.values())
    private val testFrameworkCombo = ComboBox(MTRSettings.TestFramework.values())
    private val backendCombo = ComboBox(MTRSettings.AutomationBackend.values())

    // === Device Configuration ===
    private val adbPathField = TextFieldWithBrowseButton()
    private val androidSdkPathField = TextFieldWithBrowseButton()
    private val defaultEmulatorField = JBTextField()
    private val defaultSimulatorField = JBTextField()

    // === Code Generation ===
    private val pageObjectPatternCombo = ComboBox(MTRSettings.PageObjectPattern.values())
    private val generateCommentsCheckbox = JBCheckBox("Generate code comments")
    private val generateDocstringsCheckbox = JBCheckBox("Generate docstrings")
    private val useTypeHintsCheckbox = JBCheckBox("Use type hints (Python/TypeScript)")

    // === Daemon Configuration ===
    private val daemonAutoStartCheckbox = JBCheckBox("Auto-start daemon when IDE opens")
    private val daemonPortField = JBTextField()
    private val daemonLogLevelCombo = ComboBox(MTRSettings.LogLevel.values())

    // === UI Preferences ===
    private val screenshotIntervalField = JBTextField()
    private val showOverlayCheckbox = JBCheckBox("Show element overlay on screenshot")
    private val highlightTappedCheckbox = JBCheckBox("Highlight tapped elements")

    // === License ===
    private val licenseKeyField = JBTextField()
    private val licenseEmailField = JBTextField()

    private var mainPanel: JPanel? = null

    override fun getDisplayName(): String = "Mobile Test Recorder"

    override fun createComponent(): JComponent {
        setupBrowseButtons()
        setupRadioButtons()
        setupConditionalVisibility()

        mainPanel = FormBuilder.createFormBuilder()
            // Project Configuration
            .addComponent(TitledSeparator("Project Configuration"))
            .addComponent(hasSourceCodeCheckbox)
            .addLabeledComponent(JBLabel("Source code path:"), sourceCodePathField)
            .addLabeledComponent(JBLabel("Build path (.apk/.ipa):"), buildPathField)
            .addLabeledComponent(JBLabel("Target platform:"), platformCombo)
            .addComponentFillVertically(JPanel(), 5)

            // Analysis Options
            .addComponent(TitledSeparator("Analysis Options"))
            .addComponent(analyzeApiLogsCheckbox)
            .addComponent(securityScanCheckbox)
            .addComponent(performanceAnalysisCheckbox)
            .addComponentFillVertically(JPanel(), 5)

            // Test Framework
            .addComponent(TitledSeparator("Test Framework"))
            .addComponent(createFrameworkPanel())
            .addLabeledComponent(JBLabel("Existing framework path:"), existingFrameworkPathField)
            .addLabeledComponent(JBLabel("Programming language:"), languageCombo)
            .addLabeledComponent(JBLabel("Test framework:"), testFrameworkCombo)
            .addLabeledComponent(JBLabel("Automation backend:"), backendCombo)
            .addComponentFillVertically(JPanel(), 5)

            // Device Configuration
            .addComponent(TitledSeparator("Device Configuration"))
            .addLabeledComponent(JBLabel("ADB path:"), adbPathField)
            .addLabeledComponent(JBLabel("Android SDK path:"), androidSdkPathField)
            .addLabeledComponent(JBLabel("Default Android emulator:"), defaultEmulatorField)
            .addLabeledComponent(JBLabel("Default iOS simulator:"), defaultSimulatorField)
            .addComponentFillVertically(JPanel(), 5)

            // Code Generation
            .addComponent(TitledSeparator("Code Generation"))
            .addLabeledComponent(JBLabel("Page Object pattern:"), pageObjectPatternCombo)
            .addComponent(generateCommentsCheckbox)
            .addComponent(generateDocstringsCheckbox)
            .addComponent(useTypeHintsCheckbox)
            .addComponentFillVertically(JPanel(), 5)

            // Daemon Configuration
            .addComponent(TitledSeparator("Daemon Configuration"))
            .addComponent(daemonAutoStartCheckbox)
            .addLabeledComponent(JBLabel("Daemon port:"), daemonPortField)
            .addLabeledComponent(JBLabel("Log level:"), daemonLogLevelCombo)
            .addComponentFillVertically(JPanel(), 5)

            // UI Preferences
            .addComponent(TitledSeparator("UI Preferences"))
            .addLabeledComponent(JBLabel("Screenshot refresh interval (ms):"), screenshotIntervalField)
            .addComponent(showOverlayCheckbox)
            .addComponent(highlightTappedCheckbox)
            .addComponentFillVertically(JPanel(), 5)

            // License
            .addComponent(TitledSeparator("License"))
            .addLabeledComponent(JBLabel("License key:"), licenseKeyField)
            .addLabeledComponent(JBLabel("Email:"), licenseEmailField)
            .addComponentFillVertically(JPanel(), 20)

            .panel

        val scrollPane = JScrollPane(mainPanel)
        scrollPane.border = null

        val container = JPanel(BorderLayout())
        container.add(scrollPane, BorderLayout.CENTER)

        reset() // Load current settings
        return container
    }

    private fun createFrameworkPanel(): JPanel {
        val group = ButtonGroup()
        group.add(createNewFrameworkRadio)
        group.add(useExistingFrameworkRadio)

        val panel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        panel.add(createNewFrameworkRadio)
        panel.add(Box.createHorizontalStrut(20))
        panel.add(useExistingFrameworkRadio)
        return panel
    }

    private fun setupBrowseButtons() {
        sourceCodePathField.addBrowseFolderListener(
            "Select Source Code Directory",
            "Choose the root directory of your mobile app source code",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )

        buildPathField.addBrowseFolderListener(
            "Select Build Directory",
            "Choose the directory containing .apk or .ipa files",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )

        existingFrameworkPathField.addBrowseFolderListener(
            "Select Existing Framework",
            "Choose the root directory of your existing test framework",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )

        adbPathField.addBrowseFolderListener(
            "Select ADB Executable",
            "Choose the path to adb executable",
            null,
            FileChooserDescriptorFactory.createSingleFileDescriptor()
        )

        androidSdkPathField.addBrowseFolderListener(
            "Select Android SDK",
            "Choose the Android SDK root directory",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
        )
    }

    private fun setupRadioButtons() {
        createNewFrameworkRadio.addActionListener { updateFrameworkVisibility() }
        useExistingFrameworkRadio.addActionListener { updateFrameworkVisibility() }
    }

    private fun setupConditionalVisibility() {
        hasSourceCodeCheckbox.addActionListener { updateSourceCodeVisibility() }
    }

    private fun updateSourceCodeVisibility() {
        val hasSource = hasSourceCodeCheckbox.isSelected
        sourceCodePathField.isEnabled = hasSource
        // Build path is always enabled (for decompilation when no source)
    }

    private fun updateFrameworkVisibility() {
        existingFrameworkPathField.isEnabled = useExistingFrameworkRadio.isSelected
    }

    override fun isModified(): Boolean {
        val state = settings.state
        return hasSourceCodeCheckbox.isSelected != state.hasSourceCode ||
                sourceCodePathField.text != state.sourceCodePath ||
                buildPathField.text != state.buildPath ||
                platformCombo.selectedItem != state.targetPlatform ||
                analyzeApiLogsCheckbox.isSelected != state.analyzeApiLogs ||
                securityScanCheckbox.isSelected != state.enableSecurityScan ||
                performanceAnalysisCheckbox.isSelected != state.enablePerformanceAnalysis ||
                createNewFrameworkRadio.isSelected != state.createNewFramework ||
                existingFrameworkPathField.text != state.existingFrameworkPath ||
                languageCombo.selectedItem != state.preferredLanguage ||
                testFrameworkCombo.selectedItem != state.testFramework ||
                backendCombo.selectedItem != state.automationBackend ||
                adbPathField.text != state.adbPath ||
                androidSdkPathField.text != state.androidSdkPath ||
                defaultEmulatorField.text != state.defaultEmulatorName ||
                defaultSimulatorField.text != state.defaultSimulatorName ||
                pageObjectPatternCombo.selectedItem != state.pageObjectPattern ||
                generateCommentsCheckbox.isSelected != state.generateComments ||
                generateDocstringsCheckbox.isSelected != state.generateDocstrings ||
                useTypeHintsCheckbox.isSelected != state.useTypeHints ||
                daemonAutoStartCheckbox.isSelected != state.daemonAutoStart ||
                daemonPortField.text != state.daemonPort.toString() ||
                daemonLogLevelCombo.selectedItem != state.daemonLogLevel ||
                screenshotIntervalField.text != state.screenshotRefreshInterval.toString() ||
                showOverlayCheckbox.isSelected != state.showElementOverlay ||
                highlightTappedCheckbox.isSelected != state.highlightTappedElements ||
                licenseKeyField.text != state.licenseKey ||
                licenseEmailField.text != state.licenseEmail
    }

    override fun apply() {
        val state = settings.state

        state.hasSourceCode = hasSourceCodeCheckbox.isSelected
        state.sourceCodePath = sourceCodePathField.text
        state.buildPath = buildPathField.text
        state.targetPlatform = platformCombo.selectedItem as MTRSettings.Platform

        state.analyzeApiLogs = analyzeApiLogsCheckbox.isSelected
        state.enableSecurityScan = securityScanCheckbox.isSelected
        state.enablePerformanceAnalysis = performanceAnalysisCheckbox.isSelected

        state.createNewFramework = createNewFrameworkRadio.isSelected
        state.existingFrameworkPath = existingFrameworkPathField.text
        state.preferredLanguage = languageCombo.selectedItem as MTRSettings.Language
        state.testFramework = testFrameworkCombo.selectedItem as MTRSettings.TestFramework
        state.automationBackend = backendCombo.selectedItem as MTRSettings.AutomationBackend

        state.adbPath = adbPathField.text
        state.androidSdkPath = androidSdkPathField.text
        state.defaultEmulatorName = defaultEmulatorField.text
        state.defaultSimulatorName = defaultSimulatorField.text

        state.pageObjectPattern = pageObjectPatternCombo.selectedItem as MTRSettings.PageObjectPattern
        state.generateComments = generateCommentsCheckbox.isSelected
        state.generateDocstrings = generateDocstringsCheckbox.isSelected
        state.useTypeHints = useTypeHintsCheckbox.isSelected

        state.daemonAutoStart = daemonAutoStartCheckbox.isSelected
        state.daemonPort = daemonPortField.text.toIntOrNull() ?: 9876
        state.daemonLogLevel = daemonLogLevelCombo.selectedItem as MTRSettings.LogLevel

        state.screenshotRefreshInterval = screenshotIntervalField.text.toIntOrNull() ?: 1000
        state.showElementOverlay = showOverlayCheckbox.isSelected
        state.highlightTappedElements = highlightTappedCheckbox.isSelected

        state.licenseKey = licenseKeyField.text
        state.licenseEmail = licenseEmailField.text
    }

    override fun reset() {
        val state = settings.state

        hasSourceCodeCheckbox.isSelected = state.hasSourceCode
        sourceCodePathField.text = state.sourceCodePath
        buildPathField.text = state.buildPath
        platformCombo.selectedItem = state.targetPlatform

        analyzeApiLogsCheckbox.isSelected = state.analyzeApiLogs
        securityScanCheckbox.isSelected = state.enableSecurityScan
        performanceAnalysisCheckbox.isSelected = state.enablePerformanceAnalysis

        createNewFrameworkRadio.isSelected = state.createNewFramework
        useExistingFrameworkRadio.isSelected = !state.createNewFramework
        existingFrameworkPathField.text = state.existingFrameworkPath
        languageCombo.selectedItem = state.preferredLanguage
        testFrameworkCombo.selectedItem = state.testFramework
        backendCombo.selectedItem = state.automationBackend

        adbPathField.text = state.adbPath
        androidSdkPathField.text = state.androidSdkPath
        defaultEmulatorField.text = state.defaultEmulatorName
        defaultSimulatorField.text = state.defaultSimulatorName

        pageObjectPatternCombo.selectedItem = state.pageObjectPattern
        generateCommentsCheckbox.isSelected = state.generateComments
        generateDocstringsCheckbox.isSelected = state.generateDocstrings
        useTypeHintsCheckbox.isSelected = state.useTypeHints

        daemonAutoStartCheckbox.isSelected = state.daemonAutoStart
        daemonPortField.text = state.daemonPort.toString()
        daemonLogLevelCombo.selectedItem = state.daemonLogLevel

        screenshotIntervalField.text = state.screenshotRefreshInterval.toString()
        showOverlayCheckbox.isSelected = state.showElementOverlay
        highlightTappedCheckbox.isSelected = state.highlightTappedElements

        licenseKeyField.text = state.licenseKey
        licenseEmailField.text = state.licenseEmail

        // Update conditional visibility
        updateSourceCodeVisibility()
        updateFrameworkVisibility()
    }
}
