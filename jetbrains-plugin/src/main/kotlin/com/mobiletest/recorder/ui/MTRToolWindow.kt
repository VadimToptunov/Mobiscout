package com.mobiletest.recorder.ui

import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.actionSystem.Separator
import com.intellij.openapi.actionSystem.ex.ActionUtil
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBTabbedPane
import com.intellij.util.ui.JBUI
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService
import com.mobiletest.recorder.ui.panels.DevicesPanel
import com.mobiletest.recorder.ui.panels.InspectorPanel
import com.mobiletest.recorder.ui.panels.LogsPanel
import com.mobiletest.recorder.ui.panels.ProPanel
import com.mobiletest.recorder.ui.panels.ScreenPanel
import java.awt.BorderLayout
import javax.swing.*

class MTRToolWindow(private val project: Project) {
    private val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
    private val tabbedPane = JBTabbedPane()
    
    // Panels
    private val devicesPanel = DevicesPanel(project, daemonService)
    private val screenPanel = ScreenPanel(project, daemonService)
    private val inspectorPanel = InspectorPanel(project, daemonService)
    private val logsPanel = LogsPanel(project, daemonService)
    private val proPanel = ProPanel(project, daemonService)
    
    private val mainPanel = JPanel(BorderLayout())

    // Theme-aware status colours (a hardcoded Color.GREEN/RED washes out in the
    // Darcula/dark themes); JBColor picks the right shade per theme.
    private val runningColor = JBColor(0x2E7D32, 0x6A8759)
    private val stoppedColor = JBColor(0x9E9E9E, 0x808080)
    private val statusLabel = JLabel("● Stopped").apply { foreground = stoppedColor }

    // Single source of truth for the daemon state so the toolbar actions can
    // enable/disable themselves in update() and the status label stays in sync.
    private var daemonRunning = false
    private var daemonStarting = false

    init {
        // Publish the panels so toolbar/menu actions (which the platform creates
        // without a panel reference) can drive them — e.g. RefreshDevicesAction.
        project.getService(MTRToolWindowService::class.java).let {
            it.devicesPanel = devicesPanel
            it.screenPanel = screenPanel
        }
        createToolbar()
        createTabs()
    }
    
    private fun createToolbar() {
        // A native ActionToolbar (icons, tooltips, theme, keyboard) instead of a
        // hand-rolled row of JButtons: it renders like the rest of the IDE and the
        // actions enable/disable themselves via update() off `daemonRunning`.
        val group = DefaultActionGroup().apply {
            add(GenerateKitAction())
            add(Separator.getInstance())
            add(StartDaemonAction())
            add(StopDaemonAction())
        }
        val actionToolbar = ActionManager.getInstance()
            .createActionToolbar(ActionPlaces.TOOLWINDOW_CONTENT, group, true)
        actionToolbar.targetComponent = mainPanel

        // The live daemon status dot sits at the trailing edge, outside the action
        // group (ActionToolbar hosts actions, not stateful labels).
        val bar = JPanel(BorderLayout()).apply {
            border = JBUI.Borders.empty(2, 4)
            add(actionToolbar.component, BorderLayout.WEST)
            add(statusLabel, BorderLayout.EAST)
        }
        mainPanel.add(bar, BorderLayout.NORTH)
    }

    /** The primary action — also registered under Tools ▸ Mobiscout Framework. */
    private inner class GenerateKitAction : AnAction(
        "Generate Test Kit…",
        "Generate a runnable test project from a crawl or app",
        AllIcons.Actions.Execute,
    ) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun actionPerformed(e: AnActionEvent) {
            // ActionUtil.invokeAction is the sanctioned way to fire a registered
            // action programmatically — don't call actionPerformed() directly.
            ActionManager.getInstance().getAction("MTR.GenerateKit")?.let { action ->
                val ctx = SimpleDataContext.getProjectContext(project)
                ActionUtil.invokeAction(action, ctx, ActionPlaces.TOOLWINDOW_CONTENT, null, null)
            }
        }
    }

    private inner class StartDaemonAction : AnAction(
        "Start Engine",
        "Start the Mobiscout engine (downloaded automatically on first use)",
        AllIcons.Actions.Execute,
    ) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = !daemonRunning && !daemonStarting
        }

        override fun actionPerformed(e: AnActionEvent) {
            daemonStarting = true
            statusLabel.text = "● Starting…"
            statusLabel.foreground = stoppedColor
            (object : SwingWorker<Boolean, Void>() {
                override fun doInBackground(): Boolean = daemonService.start()

                override fun done() {
                    daemonStarting = false
                    if (get()) {
                        daemonRunning = true
                        statusLabel.text = "● Running"
                        statusLabel.foreground = runningColor
                        devicesPanel.refreshDevices()
                        proPanel.refreshTier()
                    } else {
                        statusLabel.text = "● Stopped"
                        statusLabel.foreground = stoppedColor
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
    }

    private inner class StopDaemonAction : AnAction(
        "Stop Engine",
        "Stop the Mobiscout engine",
        AllIcons.Actions.Suspend,
    ) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = daemonRunning
        }

        override fun actionPerformed(e: AnActionEvent) {
            daemonService.stop()
            daemonRunning = false
            statusLabel.text = "● Stopped"
            statusLabel.foreground = stoppedColor
        }
    }

    private fun createTabs() {
        // Per-tab icons give the tool window a scannable information architecture
        // instead of a row of bare words.
        tabbedPane.addTab("Devices", AllIcons.Nodes.PpLib, devicesPanel.getPanel())
        tabbedPane.addTab("Screen", AllIcons.Actions.PreviewDetails, screenPanel.getPanel())
        tabbedPane.addTab("Inspector", AllIcons.Toolwindows.ToolWindowStructure, inspectorPanel.getPanel())
        tabbedPane.addTab("Logs", AllIcons.Debugger.Console, logsPanel.getPanel())
        tabbedPane.addTab("PRO", AllIcons.Nodes.Favorite, proPanel.getPanel())

        mainPanel.add(tabbedPane, BorderLayout.CENTER)
    }
    
    fun getContent(): JComponent {
        return mainPanel
    }
}
