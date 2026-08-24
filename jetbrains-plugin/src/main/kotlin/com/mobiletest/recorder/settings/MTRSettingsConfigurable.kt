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
import javax.swing.ButtonGroup
import javax.swing.Box
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JRadioButton
import javax.swing.JScrollPane

/**
 * Settings UI for the Mobiscout plugin.
 *
 * Only settings the plugin actually consumes are shown — the page used to render ~20 more
 * (adb/SDK paths, license, code-gen toggles, screenshot interval, daemon port, …) that
 * nothing read, so a user turned them and nothing happened. See [MTRSettings].
 */
class MTRSettingsConfigurable : Configurable {

    private val settings = MTRSettings.getInstance()

    // Defaults for the Generate dialog.
    private val platformCombo = ComboBox(MTRSettings.Platform.values())
    private val languageCombo = ComboBox(MTRSettings.Language.values())
    private val createNewFrameworkRadio = JRadioButton("Create a new test framework")
    private val useExistingFrameworkRadio = JRadioButton("Integrate with an existing framework")
    private val existingFrameworkPathField = TextFieldWithBrowseButton()

    // Preferred device to auto-boot when nothing is running.
    private val defaultEmulatorField = JBTextField()
    private val defaultSimulatorField = JBTextField()

    // Engine.
    private val daemonAutoStartCheckbox = JBCheckBox("Start the engine when the IDE opens")

    override fun getDisplayName(): String = "Mobiscout"

    override fun createComponent(): JComponent {
        existingFrameworkPathField.addBrowseFolderListener(
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor()
                .withTitle("Select Existing Framework")
                .withDescription("Choose the root directory of your existing test framework"),
        )
        val group = ButtonGroup().apply { add(createNewFrameworkRadio); add(useExistingFrameworkRadio) }
        createNewFrameworkRadio.addActionListener { updateFrameworkVisibility() }
        useExistingFrameworkRadio.addActionListener { updateFrameworkVisibility() }

        val frameworkRadios = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0)).apply {
            add(createNewFrameworkRadio)
            add(Box.createHorizontalStrut(20))
            add(useExistingFrameworkRadio)
        }

        val panel = FormBuilder.createFormBuilder()
            .addComponent(TitledSeparator("Generate — defaults"))
            .addLabeledComponent(JBLabel("Target platform:"), platformCombo)
            .addLabeledComponent(JBLabel("Programming language:"), languageCombo)
            .addComponent(frameworkRadios)
            .addLabeledComponent(JBLabel("Existing framework path:"), existingFrameworkPathField)
            .addComponentFillVertically(JPanel(), 5)

            .addComponent(TitledSeparator("Device auto-boot"))
            .addComponent(JBLabel("When no device is running, Generate boots one — prefer these by name (blank = first available):"))
            .addLabeledComponent(JBLabel("Android emulator (AVD):"), defaultEmulatorField)
            .addLabeledComponent(JBLabel("iOS simulator:"), defaultSimulatorField)
            .addComponentFillVertically(JPanel(), 5)

            .addComponent(TitledSeparator("Engine"))
            .addComponent(daemonAutoStartCheckbox)
            .addComponentFillVertically(JPanel(), 20)
            .panel

        val container = JPanel(BorderLayout())
        container.add(JScrollPane(panel).apply { border = null }, BorderLayout.CENTER)
        reset()
        return container
    }

    private fun updateFrameworkVisibility() {
        existingFrameworkPathField.isEnabled = useExistingFrameworkRadio.isSelected
    }

    override fun isModified(): Boolean {
        val s = settings.state
        return platformCombo.selectedItem != s.targetPlatform ||
            languageCombo.selectedItem != s.preferredLanguage ||
            createNewFrameworkRadio.isSelected != s.createNewFramework ||
            existingFrameworkPathField.text != s.existingFrameworkPath ||
            defaultEmulatorField.text != s.defaultEmulatorName ||
            defaultSimulatorField.text != s.defaultSimulatorName ||
            daemonAutoStartCheckbox.isSelected != s.daemonAutoStart
    }

    override fun apply() {
        val s = settings.state
        s.targetPlatform = platformCombo.selectedItem as MTRSettings.Platform
        s.preferredLanguage = languageCombo.selectedItem as MTRSettings.Language
        s.createNewFramework = createNewFrameworkRadio.isSelected
        s.existingFrameworkPath = existingFrameworkPathField.text
        s.defaultEmulatorName = defaultEmulatorField.text.trim()
        s.defaultSimulatorName = defaultSimulatorField.text.trim()
        s.daemonAutoStart = daemonAutoStartCheckbox.isSelected
    }

    override fun reset() {
        val s = settings.state
        platformCombo.selectedItem = s.targetPlatform
        languageCombo.selectedItem = s.preferredLanguage
        createNewFrameworkRadio.isSelected = s.createNewFramework
        useExistingFrameworkRadio.isSelected = !s.createNewFramework
        existingFrameworkPathField.text = s.existingFrameworkPath
        defaultEmulatorField.text = s.defaultEmulatorName
        defaultSimulatorField.text = s.defaultSimulatorName
        daemonAutoStartCheckbox.isSelected = s.daemonAutoStart
        updateFrameworkVisibility()
    }
}
