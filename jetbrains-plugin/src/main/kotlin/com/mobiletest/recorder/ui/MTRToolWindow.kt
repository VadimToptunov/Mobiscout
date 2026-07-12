package com.mobiletest.recorder.ui

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBTabbedPane
import com.mobiletest.recorder.services.MTRDaemonService
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
        createToolbar()
        createTabs()
    }
    
    private fun createToolbar() {
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)
        
        // Start/Stop Daemon buttons
        val startButton = JButton("Start Daemon")
        val stopButton = JButton("Stop Daemon")
        val statusLabel = JLabel("Daemon: Stopped")
        
        startButton.addActionListener {
            (object : SwingWorker<Boolean, Void>() {
                override fun doInBackground(): Boolean {
                    return daemonService.start()
                }
                
                override fun done() {
                    val started = get()
                    if (started) {
                        statusLabel.text = "Daemon: Running"
                        statusLabel.foreground = java.awt.Color.GREEN
                        startButton.isEnabled = false
                        stopButton.isEnabled = true
                        
                        // Refresh devices
                        devicesPanel.refreshDevices()
                    } else {
                        JOptionPane.showMessageDialog(
                            mainPanel,
                            "Failed to start the engine. It is downloaded automatically on first use; " +
                                "check your internet connection, or install the 'observe' CLI on PATH.",
                            "Error",
                            JOptionPane.ERROR_MESSAGE
                        )
                    }
                }
            }).execute()
        }
        
        stopButton.addActionListener {
            daemonService.stop()
            statusLabel.text = "Daemon: Stopped"
            statusLabel.foreground = java.awt.Color.RED
            startButton.isEnabled = true
            stopButton.isEnabled = false
        }
        
        stopButton.isEnabled = false
        
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
