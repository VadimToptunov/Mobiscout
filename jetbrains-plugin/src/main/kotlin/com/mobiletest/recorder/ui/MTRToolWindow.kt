package com.mobiletest.recorder.ui

import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ex.ActionUtil
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBTabbedPane
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService
import com.mobiletest.recorder.ui.panels.DevicesPanel
import com.mobiletest.recorder.ui.panels.InspectorPanel
import com.mobiletest.recorder.ui.panels.LogsPanel
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
    
    private val mainPanel = JPanel(BorderLayout())
    
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
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)
        
        // Theme-aware status colours (a hardcoded Color.GREEN/RED washes out in the
        // Darcula/dark themes); JBColor picks the right shade per theme.
        val runningColor = JBColor(0x2E7D32, 0x6A8759)
        val stoppedColor = JBColor(0x9E9E9E, 0x808080)

        val startButton = JButton("Start Daemon")
        val stopButton = JButton("Stop Daemon")
        val statusLabel = JLabel("● Stopped").apply { foreground = stoppedColor }
        // The primary action — surfaced right in the tool window instead of only
        // living under Tools ▸ Mobiscout Framework.
        val generateButton = JButton("Generate Test Kit…")

        startButton.addActionListener {
            startButton.isEnabled = false
            statusLabel.text = "● Starting…"
            statusLabel.foreground = stoppedColor
            (object : SwingWorker<Boolean, Void>() {
                override fun doInBackground(): Boolean = daemonService.start()

                override fun done() {
                    val started = get()
                    if (started) {
                        statusLabel.text = "● Running"
                        statusLabel.foreground = runningColor
                        stopButton.isEnabled = true
                        devicesPanel.refreshDevices()
                    } else {
                        statusLabel.text = "● Stopped"
                        statusLabel.foreground = stoppedColor
                        startButton.isEnabled = true
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

        stopButton.addActionListener {
            daemonService.stop()
            statusLabel.text = "● Stopped"
            statusLabel.foreground = stoppedColor
            startButton.isEnabled = true
            stopButton.isEnabled = false
        }

        // Run the registered "Generate Test Kit" action (starts the daemon if
        // needed). ActionUtil.invokeAction is the sanctioned way to fire an action
        // programmatically — don't call actionPerformed() directly (override-only).
        generateButton.addActionListener {
            ActionManager.getInstance().getAction("MTR.GenerateKit")?.let { action ->
                val ctx = SimpleDataContext.getProjectContext(project)
                ActionUtil.invokeAction(action, ctx, ActionPlaces.TOOLWINDOW_CONTENT, null, null)
            }
        }

        stopButton.isEnabled = false

        toolbar.add(generateButton)
        toolbar.add(Box.createHorizontalStrut(12))
        toolbar.add(startButton)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(stopButton)
        toolbar.add(Box.createHorizontalStrut(10))
        toolbar.add(statusLabel)
        toolbar.add(Box.createHorizontalGlue())

        mainPanel.add(toolbar, BorderLayout.NORTH)
    }
    
    private fun createTabs() {
        tabbedPane.addTab("Devices", devicesPanel.getPanel())
        tabbedPane.addTab("Screen", screenPanel.getPanel())
        tabbedPane.addTab("Inspector", inspectorPanel.getPanel())
        tabbedPane.addTab("Logs", logsPanel.getPanel())
        
        mainPanel.add(tabbedPane, BorderLayout.CENTER)
    }
    
    fun getContent(): JComponent {
        return mainPanel
    }
}
