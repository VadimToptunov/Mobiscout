package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.intellij.ide.DataManager
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ActionUiKind
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.ex.ActionUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.popup.JBPopupFactory
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

        val bootButton = JButton("Boot device…")
        bootButton.addActionListener { bootDevice() }
        toolbar.add(bootButton)

        val shutdownButton = JButton("Shutdown")
        shutdownButton.addActionListener { shutdownDevice() }
        toolbar.add(shutdownButton)

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
            // Build an event from the panel's data context and fire it via the current
            // non-deprecated invokeAction(action, event, onDone) form.
            val dataContext = DataManager.getInstance().getDataContext(panel)
            val event = AnActionEvent.createEvent(
                dataContext,
                action.templatePresentation.clone(),
                ActionPlaces.TOOLWINDOW_CONTENT,
                ActionUiKind.NONE,
                null,
            )
            ActionUtil.invokeAction(action, event, null)
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

    /**
     * Boot an emulator/simulator without leaving the IDE: offer the installed
     * Android AVDs (device/listAvds) and the shut-down iOS simulators (device/list),
     * then device/start the chosen one. Booting is async — the device shows up on a
     * later Refresh, which we kick off optimistically.
     */
    private fun bootDevice() {
        (object : SwingWorker<Pair<List<String>, List<Pair<String, String>>>, Void>() {
            // labels shown to the user, and the parallel (platform, target) to boot.
            override fun doInBackground(): Pair<List<String>, List<Pair<String, String>>> {
                val labels = mutableListOf<String>()
                val targets = mutableListOf<Pair<String, String>>()
                try {
                    daemonService.listAvds()?.getAsJsonArray("avds")?.forEach {
                        val avd = it.asString
                        labels.add("Android AVD — $avd")
                        targets.add("android" to avd)
                    }
                } catch (_: Exception) {}
                try {
                    daemonService.listDevices("ios")?.getAsJsonArray("devices")?.forEach {
                        val d = it.asJsonObject
                        if ((d.get("status")?.asString ?: "") == "shutdown") {
                            val name = d.get("name")?.asString ?: ""
                            val udid = d.get("id")?.asString ?: ""
                            labels.add("iOS Simulator — $name")
                            targets.add("ios" to udid)
                        }
                    }
                } catch (_: Exception) {}
                return labels to targets
            }

            override fun done() {
                val (labels, targets) = get()
                if (labels.isEmpty()) {
                    Messages.showInfoMessage(
                        project,
                        "No bootable AVDs or shut-down simulators found. Is the engine running?",
                        "Boot Device",
                    )
                    return
                }
                // A lightweight list popup (the non-deprecated replacement for the old
                // Messages.showChooseDialog combo). Async: boot the chosen device in the
                // item-chosen callback; dismissing it (Esc / click away) boots nothing.
                JBPopupFactory.getInstance()
                    .createPopupChooserBuilder(labels)
                    .setTitle("Pick a device to boot")
                    .setItemChosenCallback { chosen ->
                        val idx = labels.indexOf(chosen)
                        if (idx >= 0) {
                            val (platform, target) = targets[idx]
                            startBoot(platform, target, labels[idx])
                        }
                    }
                    .createPopup()
                    .showCenteredInCurrentWindow(project)
            }
        }).execute()
    }

    private fun startBoot(platform: String, target: String, label: String) {
        (object : SwingWorker<JsonObject?, Void>() {
            override fun doInBackground(): JsonObject? =
                try { daemonService.startDevice(platform, target) } catch (e: Exception) { null }

            override fun done() {
                val started = get()?.get("started")?.asBoolean ?: false
                if (started) {
                    Messages.showInfoMessage(
                        project, "Booting $label — it'll appear here once ready (hit Refresh).", "Boot Device"
                    )
                    refreshDevices()
                } else {
                    val err = get()?.get("error")?.asString ?: "no response from the engine"
                    Messages.showErrorDialog(project, "Couldn't boot $label: $err", "Boot Device")
                }
            }
        }).execute()
    }

    /** Shut down the selected running device (device/stop). */
    private fun shutdownDevice() {
        val row = table.selectedRow
        if (row < 0) {
            Messages.showWarningDialog(project, "Select a running device first.", "Shutdown")
            return
        }
        val deviceId = tableModel.getValueAt(row, 0)?.toString().orEmpty()
        val platform = tableModel.getValueAt(row, 2)?.toString().orEmpty().ifEmpty { "android" }
        (object : SwingWorker<JsonObject?, Void>() {
            override fun doInBackground(): JsonObject? =
                try { daemonService.stopDevice(platform, deviceId) } catch (e: Exception) { null }

            override fun done() {
                val stopped = get()?.get("stopped")?.asBoolean ?: false
                if (stopped) refreshDevices()
                else Messages.showErrorDialog(
                    project, "Couldn't shut down $deviceId: ${get()?.get("error")?.asString ?: "no response"}", "Shutdown"
                )
            }
        }).execute()
    }

    fun getPanel(): JComponent = panel
}
