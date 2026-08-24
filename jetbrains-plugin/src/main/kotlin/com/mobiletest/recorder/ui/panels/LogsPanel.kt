package com.mobiletest.recorder.ui.panels

import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextField
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.ui.DeviceItem
import com.mobiletest.recorder.ui.DeviceList
import java.awt.BorderLayout
import java.awt.Font
import javax.swing.*
import javax.swing.text.BadLocationException
import com.mobiletest.recorder.ui.Notifier

class LogsPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService
) {
    private val panel = JPanel(BorderLayout())
    private val logsTextArea = JTextArea()
    private val logsScroll = JBScrollPane(logsTextArea)

    // App-log stream controls: pick a device, name the app, stream its device logs.
    private val deviceCombo = JComboBox<DeviceItem>()
    private val appField = JBTextField(16)

    // Whether a device-log stream is live — drives the Start/Stop action enablement.
    private var streaming = false

    init {
        logsTextArea.isEditable = false
        logsTextArea.font = Font("Monospaced", Font.PLAIN, 11)

        // Native ActionToolbar for the actions; the device combo + app field sit alongside it
        // (they can't live inside an ActionToolbar). Start/Stop enable off `streaming`.
        val actions = DefaultActionGroup().apply {
            add(LoadDevicesAction())
            add(StartLogsAction())
            add(StopLogsAction())
            add(ClearAction())
        }
        val actionToolbar = ActionManager.getInstance()
            .createActionToolbar(ActionPlaces.TOOLWINDOW_CONTENT, actions, true)
        actionToolbar.targetComponent = panel

        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)
        toolbar.add(JLabel("Device:"))
        toolbar.add(Box.createHorizontalStrut(4))
        toolbar.add(deviceCombo)
        toolbar.add(Box.createHorizontalStrut(8))
        toolbar.add(JLabel("App:"))
        toolbar.add(appField)
        toolbar.add(Box.createHorizontalStrut(6))
        toolbar.add(actionToolbar.component)
        toolbar.add(Box.createHorizontalGlue())

        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(logsScroll, BorderLayout.CENTER)

        // Render both daemon logs and streamed app logs (both arrive as logs/message).
        daemonService.addNotificationListener { notification ->
            if (notification.method == "logs/message") {
                val params = notification.params
                val message = params.get("message")?.asString ?: ""
                val timestamp = params.get("timestamp")?.asString ?: ""
                val level = params.get("level")?.asString ?: "INFO"
                val prefix = if (timestamp.isBlank()) "$level: " else "[$timestamp] $level: "

                SwingUtilities.invokeLater {
                    val bar = logsScroll.verticalScrollBar
                    // Autoscroll only when the view is already at the tail — don't yank it
                    // back down while the user has scrolled up to read earlier lines.
                    val atBottom = bar.value + bar.visibleAmount >= bar.maximum - 4
                    val doc = logsTextArea.document
                    logsTextArea.append("$prefix$message\n")
                    // Bound the buffer: a long-running stream would otherwise grow without
                    // limit. Drop the oldest characters once it exceeds MAX_LOG_CHARS.
                    if (doc.length > MAX_LOG_CHARS) {
                        try {
                            doc.remove(0, doc.length - MAX_LOG_CHARS)
                        } catch (_: BadLocationException) {
                            // concurrent edit narrowed the doc — skip this trim
                        }
                    }
                    if (atBottom) logsTextArea.caretPosition = doc.length
                }
            }
        }
    }

    private fun loadDevices() {
        (object : SwingWorker<List<DeviceItem>, Void>() {
            override fun doInBackground(): List<DeviceItem> = DeviceList.load("all")

            override fun done() {
                deviceCombo.removeAllItems()
                get().forEach { deviceCombo.addItem(it) }
            }
        }).execute()
    }

    private fun startAppLogs() {
        val selected = deviceCombo.selectedItem as? DeviceItem
        val udid = selected?.id.orEmpty()
        val bundle = appField.text.trim()
        val platform = selected?.platform ?: "ios"
        if (udid.isEmpty() || bundle.isEmpty()) {
            Notifier.warn(project, "App Logs", "Pick a device and enter the app bundle id / package first.")
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
                    streaming = true // the toolbar's Start/Stop reflect this via update()
                    logsTextArea.append("— streaming device logs for $bundle —\n")
                } else {
                    Notifier.error(project, "App Logs", "Couldn't start the log stream. Is the engine running?")
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
                streaming = false // flips the toolbar's Start/Stop back via update()
            }
        }).execute()
    }

    private inner class LoadDevicesAction :
        AnAction("Load Devices", "Reload the running devices", AllIcons.Actions.Refresh) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun actionPerformed(e: AnActionEvent) = loadDevices()
    }

    private inner class StartLogsAction :
        AnAction("Start App Logs", "Stream the app's device logs", AllIcons.Actions.Execute) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            // Needs a device and an app id, and only one live stream at a time.
            e.presentation.isEnabled =
                !streaming && deviceCombo.selectedItem is DeviceItem && appField.text.isNotBlank()
        }

        override fun actionPerformed(e: AnActionEvent) = startAppLogs()
    }

    private inner class StopLogsAction :
        AnAction("Stop", "Stop the log stream", AllIcons.Actions.Suspend) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = streaming
        }

        override fun actionPerformed(e: AnActionEvent) = stopAppLogs()
    }

    private inner class ClearAction :
        AnAction("Clear", "Clear the log view", AllIcons.Actions.GC) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun actionPerformed(e: AnActionEvent) {
            logsTextArea.text = ""
        }
    }

    fun getPanel(): JComponent = panel

    companion object {
        /** Keep at most this many characters of log tail in the view (~a few MB of RAM cap). */
        private const val MAX_LOG_CHARS = 200_000
    }
}
