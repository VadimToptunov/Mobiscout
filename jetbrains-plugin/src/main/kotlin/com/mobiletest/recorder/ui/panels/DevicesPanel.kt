package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.table.JBTable
import com.mobiletest.recorder.services.MTRDaemonService
import java.awt.BorderLayout
import javax.swing.*
import javax.swing.table.DefaultTableModel

class DevicesPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService
) {
    private val panel = JPanel(BorderLayout())
    private val tableModel = DefaultTableModel(
        arrayOf("ID", "Name", "Platform", "Status"),
        0
    )
    private val table = JBTable(tableModel)
    
    init {
        // Toolbar
        val toolbar = JPanel()
        val refreshButton = JButton("Refresh")
        refreshButton.addActionListener {
            refreshDevices()
        }
        toolbar.add(refreshButton)

        val installButton = JButton("Install build…")
        installButton.addActionListener { installBuild() }
        toolbar.add(installButton)

        // Table
        table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        val scrollPane = JBScrollPane(table)
        
        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(scrollPane, BorderLayout.CENTER)
    }
    
    fun refreshDevices() {
        (object : SwingWorker<JsonObject?, Void>() {
            override fun doInBackground(): JsonObject? {
                return try {
                    daemonService.listDevices("all")
                } catch (e: Exception) {
                    null
                }
            }
            
            override fun done() {
                val result = get()
                if (result != null) {
                    updateTable(result)
                } else {
                    Messages.showErrorDialog(project, "Failed to list devices. Is the engine running?", "Devices")
                }
            }
        }).execute()
    }
    
    private fun updateTable(result: JsonObject) {
        tableModel.rowCount = 0
        
        val devices = result.getAsJsonArray("devices") ?: JsonArray()
        for (element in devices) {
            val device = element.asJsonObject
            tableModel.addRow(arrayOf(
                device.get("id")?.asString ?: "",
                device.get("name")?.asString ?: "",
                device.get("platform")?.asString ?: "",
                device.get("status")?.asString ?: ""
            ))
        }
    }
    
    /**
     * Install a build (.apk / .app) onto the selected device via the daemon's
     * app/install RPC — the IDE side of the install → crawl → cleanup flow.
     */
    private fun installBuild() {
        val row = table.selectedRow
        if (row < 0) {
            Messages.showWarningDialog(project, "Select a device first.", "Install Build")
            return
        }
        val deviceId = tableModel.getValueAt(row, 0)?.toString().orEmpty()
        val platform = tableModel.getValueAt(row, 2)?.toString().orEmpty().ifEmpty { "android" }

        val chooser = JFileChooser()
        chooser.dialogTitle = "Select a build (.apk / .app)"
        if (chooser.showOpenDialog(panel) != JFileChooser.APPROVE_OPTION) return
        val appPath = chooser.selectedFile?.absolutePath ?: return

        (object : SwingWorker<JsonObject?, Void>() {
            override fun doInBackground(): JsonObject? {
                return try {
                    daemonService.installApp(platform, deviceId, appPath)
                } catch (e: Exception) {
                    JsonObject().apply {
                        addProperty("ok", false)
                        addProperty("detail", e.message ?: e.toString())
                    }
                }
            }

            override fun done() {
                val result = get()
                val ok = result?.get("ok")?.asBoolean ?: false
                val detail = result?.get("detail")?.asString ?: "No response from the engine."
                if (ok) {
                    Messages.showInfoMessage(project, "Installed on $deviceId.", "Install Build")
                } else {
                    Messages.showErrorDialog(project, "Install failed: $detail", "Install Build")
                }
            }
        }).execute()
    }

    fun getPanel(): JComponent = panel
}
