package com.mobiletest.recorder.ui.panels

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBScrollPane
import com.mobiletest.recorder.services.MTRDaemonService
import java.awt.BorderLayout
import javax.swing.*

class LogsPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService
) {
    private val panel = JPanel(BorderLayout())
    private val logsTextArea = JTextArea()

    // App-log stream controls: pick a device, name the app, stream its device logs.
    private val deviceCombo = JComboBox<String>()
    private val appField = com.intellij.ui.components.JBTextField(16)
    private val startButton = JButton("Start App Logs")
    private val stopButton = JButton("Stop")
    // "name (id)" combo string -> platform, so logs stream on the right backend.
    private val devicePlatform = mutableMapOf<String, String>()

    init {
        logsTextArea.isEditable = false
        logsTextArea.font = java.awt.Font("Monospaced", java.awt.Font.PLAIN, 11)

        val scrollPane = JBScrollPane(logsTextArea)

        // Toolbar: device + app + stream controls, then Clear.
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)

        val loadButton = JButton("Load Devices")
        loadButton.addActionListener { loadDevices() }
        stopButton.isEnabled = false
        startButton.addActionListener { startAppLogs() }
        stopButton.addActionListener { stopAppLogs() }

        val clearButton = JButton("Clear")
        clearButton.addActionListener { logsTextArea.text = "" }

        toolbar.add(JLabel("Device:"))
        toolbar.add(Box.createHorizontalStrut(4))
        toolbar.add(deviceCombo)
        toolbar.add(Box.createHorizontalStrut(4))
        toolbar.add(loadButton)
        toolbar.add(Box.createHorizontalStrut(8))
        toolbar.add(JLabel("App:"))
        toolbar.add(appField)
        toolbar.add(Box.createHorizontalStrut(6))
        toolbar.add(startButton)
        toolbar.add(Box.createHorizontalStrut(4))
        toolbar.add(stopButton)
        toolbar.add(Box.createHorizontalGlue())
        toolbar.add(clearButton)

        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(scrollPane, BorderLayout.CENTER)

        // Render both daemon logs and streamed app logs (both arrive as logs/message).
        daemonService.addNotificationListener { notification ->
            if (notification.method == "logs/message") {
                val params = notification.params
                val message = params.get("message")?.asString ?: ""
                val timestamp = params.get("timestamp")?.asString ?: ""
                val level = params.get("level")?.asString ?: "INFO"
                val prefix = if (timestamp.isBlank()) "$level: " else "[$timestamp] $level: "

                SwingUtilities.invokeLater {
                    logsTextArea.append("$prefix$message\n")
                    logsTextArea.caretPosition = logsTextArea.document.length
                }
            }
        }
    }

    private fun loadDevices() {
        (object : SwingWorker<List<String>, Void>() {
            override fun doInBackground(): List<String> {
                return try {
                    val result = daemonService.listDevices("all")
                    val devices = result?.getAsJsonArray("devices") ?: return emptyList()
                    devices.map {
                        val dev = it.asJsonObject
                        val label = "${dev.get("name")?.asString} (${dev.get("id")?.asString})"
                        devicePlatform[label] = dev.get("platform")?.asString ?: "ios"
                        label
                    }
                } catch (e: Exception) {
                    emptyList()
                }
            }

            override fun done() {
                deviceCombo.removeAllItems()
                get().forEach { deviceCombo.addItem(it) }
            }
        }).execute()
    }

    private fun startAppLogs() {
        val selected = deviceCombo.selectedItem as? String
        val udid = selected?.substringAfterLast("(", "")?.substringBefore(")")?.trim().orEmpty()
        val bundle = appField.text.trim()
        val platform = selected?.let { devicePlatform[it] } ?: "ios"
        if (udid.isEmpty() || bundle.isEmpty()) {
            Messages.showWarningDialog(project, "Pick a device and enter the app bundle id / package first.", "App Logs")
            return
        }
        (object : SwingWorker<Boolean, Void>() {
            override fun doInBackground(): Boolean = try {
                daemonService.startAppLogs(udid, bundle, platform) != null
            } catch (e: Exception) {
                false
            }

            override fun done() {
                if (get()) {
                    startButton.isEnabled = false
                    stopButton.isEnabled = true
                    logsTextArea.append("— streaming device logs for $bundle —\n")
                } else {
                    Messages.showErrorDialog(project, "Couldn't start the log stream. Is the engine running?", "App Logs")
                }
            }
        }).execute()
    }

    private fun stopAppLogs() {
        (object : SwingWorker<Void?, Void>() {
            override fun doInBackground(): Void? {
                try {
                    daemonService.stopAppLogs()
                } catch (e: Exception) {
                    // best-effort
                }
                return null
            }

            override fun done() {
                startButton.isEnabled = true
                stopButton.isEnabled = false
            }
        }).execute()
    }

    fun getPanel(): JComponent = panel
}
