package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ex.ActionUtil
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.SimpleTextAttributes
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

        // Actionable empty state instead of a blank grid: tell the user what to do
        // and give one-click ways to do it (the #1 friction on first run is "I see
        // nothing"). The links appear only while the table is empty.
        table.emptyText.text = "No devices yet"
        table.emptyText.appendSecondaryText(
            "Start the engine, then boot a simulator or connect a device.",
            SimpleTextAttributes.GRAYED_ATTRIBUTES,
            null,
        )
        table.emptyText.appendLine("Start engine and refresh", SimpleTextAttributes.LINK_ATTRIBUTES) {
            startEngineAndRefresh()
        }
        table.emptyText.appendLine("Open Setup Wizard", SimpleTextAttributes.LINK_ATTRIBUTES) {
            runAction("MTR.SetupWizard")
        }

        val scrollPane = JBScrollPane(table)

        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(scrollPane, BorderLayout.CENTER)
    }

    /** Start the engine (if needed) then list devices — the empty-state action. */
    private fun startEngineAndRefresh() {
        (object : SwingWorker<Boolean, Void>() {
            override fun doInBackground(): Boolean = daemonService.start()

            override fun done() {
                if (get()) {
                    refreshDevices()
                } else {
                    Messages.showErrorDialog(
                        project,
                        "The engine is downloaded automatically on first use. Check your internet " +
                            "connection, or install the 'mobiscout' CLI on PATH.",
                        "Couldn't Start the Mobiscout Engine",
                    )
                }
            }
        }).execute()
    }

    /** Fire a registered plugin action by id (e.g. the Setup Wizard). */
    private fun runAction(id: String) {
        ActionManager.getInstance().getAction(id)?.let { action ->
            val ctx = SimpleDataContext.getProjectContext(project)
            ActionUtil.invokeAction(action, ctx, ActionPlaces.TOOLWINDOW_CONTENT, null, null)
        }
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
