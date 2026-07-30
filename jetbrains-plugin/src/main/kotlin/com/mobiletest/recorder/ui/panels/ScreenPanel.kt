package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonObject
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextField
import com.mobiletest.recorder.services.MTRDaemonService
import java.awt.*
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import java.awt.image.BufferedImage
import java.io.ByteArrayInputStream
import java.util.Base64
import javax.imageio.ImageIO
import javax.swing.*

class ScreenPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService
) {
    private val panel = JPanel(BorderLayout())
    private var currentSessionId: String? = null
    private var currentImage: BufferedImage? = null
    private var currentDeviceId: String? = null

    // The daemon runs a fail-fast preflight on session/start and returns an
    // actionable JSON-RPC error (e.g. the ANDROID_HOME fix) — surface it verbatim
    // instead of a generic "failed" message.
    private var lastStartError: String? = null

    // App under test + Appium server for the session — iOS needs a bundle id to
    // open an Appium session; both are harmless on Android.
    private val appField = JBTextField(16)
    private val serverField = JBTextField("http://localhost:4723", 16)
    private val launchArgsField = JBTextField(14)
    // "name (id)" combo string -> platform, so a session starts on the right backend.
    private val devicePlatform = mutableMapOf<String, String>()

    private val imagePanel = object : JPanel() {
        override fun paintComponent(g: Graphics) {
            super.paintComponent(g)
            currentImage?.let { img ->
                val g2d = g as Graphics2D
                g2d.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR)
                
                // Scale to fit panel
                val scale = minOf(
                    width.toDouble() / img.width,
                    height.toDouble() / img.height
                )
                val scaledWidth = (img.width * scale).toInt()
                val scaledHeight = (img.height * scale).toInt()
                val x = (width - scaledWidth) / 2
                val y = (height - scaledHeight) / 2
                
                g2d.drawImage(img, x, y, scaledWidth, scaledHeight, null)
            }
        }
    }
    
    init {
        imagePanel.background = Color.DARK_GRAY
        imagePanel.preferredSize = Dimension(400, 800)
        
        // Handle clicks on image
        imagePanel.addMouseListener(object : MouseAdapter() {
            override fun mouseClicked(e: MouseEvent) {
                if (currentImage != null && currentSessionId != null) {
                    // Convert screen coords to device coords
                    val scale = minOf(
                        imagePanel.width.toDouble() / currentImage!!.width,
                        imagePanel.height.toDouble() / currentImage!!.height
                    )
                    val scaledWidth = (currentImage!!.width * scale).toInt()
                    val scaledHeight = (currentImage!!.height * scale).toInt()
                    val offsetX = (imagePanel.width - scaledWidth) / 2
                    val offsetY = (imagePanel.height - scaledHeight) / 2
                    
                    val deviceX = ((e.x - offsetX) / scale).toInt()
                    val deviceY = ((e.y - offsetY) / scale).toInt()
                    
                    if (deviceX >= 0 && deviceY >= 0 && 
                        deviceX < currentImage!!.width && deviceY < currentImage!!.height) {
                        performTap(deviceX, deviceY)
                    }
                }
            }
        })
        
        val scrollPane = JBScrollPane(imagePanel)
        
        // Toolbar
        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)
        
        val deviceCombo = JComboBox<String>()
        val startButton = JButton("Start Session")
        val stopButton = JButton("Stop Session")
        val captureButton = JButton("Capture Screen")
        val refreshButton = JButton("Refresh")
        
        stopButton.isEnabled = false
        captureButton.isEnabled = false
        refreshButton.isEnabled = false
        
        // Load devices
        val loadDevicesButton = JButton("Load Devices")
        loadDevicesButton.addActionListener {
            loadDevices(deviceCombo)
        }
        
        startButton.addActionListener {
            val selectedDevice = deviceCombo.selectedItem as? String
            if (selectedDevice != null) {
                startSession(selectedDevice, startButton, stopButton, captureButton, refreshButton)
            }
        }
        
        stopButton.addActionListener {
            stopSession(startButton, stopButton, captureButton, refreshButton)
        }
        
        captureButton.addActionListener {
            captureScreen()
        }
        
        refreshButton.addActionListener {
            captureScreen()
        }
        
        toolbar.add(JLabel("Device:"))
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(deviceCombo)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(loadDevicesButton)
        toolbar.add(Box.createHorizontalStrut(8))
        toolbar.add(JLabel("App:"))
        toolbar.add(appField)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(JLabel("Server:"))
        toolbar.add(serverField)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(JLabel("Launch args:"))
        toolbar.add(launchArgsField)
        toolbar.add(Box.createHorizontalStrut(10))
        toolbar.add(startButton)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(stopButton)
        toolbar.add(Box.createHorizontalStrut(10))
        toolbar.add(captureButton)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(refreshButton)
        toolbar.add(Box.createHorizontalGlue())
        
        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(scrollPane, BorderLayout.CENTER)
    }
    
    private fun loadDevices(combo: JComboBox<String>) {
        (object : SwingWorker<List<String>, Void>() {
            override fun doInBackground(): List<String> {
                try {
                    val result = daemonService.listDevices("all")
                    val devices = result?.getAsJsonArray("devices") ?: return emptyList()
                    return devices.map {
                        val dev = it.asJsonObject
                        val label = "${dev.get("name")?.asString} (${dev.get("id")?.asString})"
                        // Remember the platform so the session starts on the right backend.
                        devicePlatform[label] = dev.get("platform")?.asString ?: "android"
                        label
                    }
                } catch (e: Exception) {
                    return emptyList()
                }
            }
            
            override fun done() {
                combo.removeAllItems()
                get().forEach { combo.addItem(it) }
            }
        }).execute()
    }
    
    private fun startSession(deviceStr: String, startBtn: JButton, stopBtn: JButton, 
                            captureBtn: JButton, refreshBtn: JButton) {
        (object : SwingWorker<String?, Void>() {
            override fun doInBackground(): String? {
                try {
                    // Extract device ID from string
                    val deviceId = deviceStr.substringAfter("(").substringBefore(")")
                    currentDeviceId = deviceId

                    // Give the daemon what it needs to open the right driver: the
                    // platform (adb vs Appium), and for iOS the app bundle id, the
                    // Appium server, and any launch args to start past a gate.
                    val launchArgs = launchArgsField.text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
                    val params = buildMap {
                        put("device_id", deviceId)
                        put("backend", "appium")
                        put("platform", devicePlatform[deviceStr] ?: "android")
                        if (appField.text.isNotBlank()) put("bundle_id", appField.text.trim())
                        if (serverField.text.isNotBlank()) put("server", serverField.text.trim())
                        if (launchArgs.isNotEmpty()) put("launch_args", launchArgs)
                    }
                    lastStartError = null
                    val client = daemonService.getClient()
                    val response = client?.call("session/start", params)
                    return response?.getResultOrThrow()?.get("session_id")?.asString
                } catch (e: Exception) {
                    lastStartError = e.message ?: e.toString()
                    return null
                }
            }
            
            override fun done() {
                val sessionId = get()
                if (sessionId != null) {
                    currentSessionId = sessionId
                    startBtn.isEnabled = false
                    stopBtn.isEnabled = true
                    captureBtn.isEnabled = true
                    refreshBtn.isEnabled = true
                    
                    // Auto-capture first screenshot
                    captureScreen()
                } else {
                    // Show the daemon's actionable message (preflight/ANDROID_HOME
                    // fix) verbatim; it can be multi-line, so use a scrollable area.
                    val message = lastStartError ?: "Failed to start session"
                    val area = JTextArea(message).apply {
                        isEditable = false
                        lineWrap = true
                        wrapStyleWord = true
                        rows = minOf(10, message.lines().size + 1)
                        columns = 60
                    }
                    JOptionPane.showMessageDialog(
                        panel,
                        JScrollPane(area),
                        "Could not start session",
                        JOptionPane.ERROR_MESSAGE
                    )
                }
            }
        }).execute()
    }
    
    private fun stopSession(startBtn: JButton, stopBtn: JButton, 
                           captureBtn: JButton, refreshBtn: JButton) {
        currentSessionId?.let { sessionId ->
            (object : SwingWorker<Void?, Void>() {
                override fun doInBackground(): Void? {
                    try {
                        val params = mapOf("session_id" to sessionId)
                        daemonService.getClient()?.call("session/stop", params)
                    } catch (e: Exception) {
                        // Ignore
                    }
                    return null
                }
                
                override fun done() {
                    currentSessionId = null
                    currentImage = null
                    imagePanel.repaint()
                    
                    startBtn.isEnabled = true
                    stopBtn.isEnabled = false
                    captureBtn.isEnabled = false
                    refreshBtn.isEnabled = false
                }
            }).execute()
        }
    }
    
    private fun captureScreen() {
        currentSessionId?.let { sessionId ->
            (object : SwingWorker<BufferedImage?, Void>() {
                override fun doInBackground(): BufferedImage? {
                    try {
                        val result = daemonService.getScreenshot(sessionId, "png")
                        val base64Data = result?.get("data")?.asString ?: return null
                        val imageBytes = Base64.getDecoder().decode(base64Data)
                        return ImageIO.read(ByteArrayInputStream(imageBytes))
                    } catch (e: Exception) {
                        return null
                    }
                }
                
                override fun done() {
                    currentImage = get()
                    imagePanel.repaint()
                }
            }).execute()
        }
    }
    
    private fun performTap(x: Int, y: Int) {
        currentSessionId?.let { sessionId ->
            (object : SwingWorker<Void?, Void>() {
                override fun doInBackground(): Void? {
                    try {
                        val params = mapOf(
                            "session_id" to sessionId,
                            "x" to x,
                            "y" to y
                        )
                        daemonService.getClient()?.call("action/tap", params)
                        
                        // Wait a bit for UI to update
                        Thread.sleep(500)
                    } catch (e: Exception) {
                        // Ignore
                    }
                    return null
                }
                
                override fun done() {
                    // Auto-refresh screenshot after tap
                    captureScreen()
                }
            }).execute()
        }
    }
    
    fun getPanel(): JComponent = panel

    /** The id of the live device session, or null if none is started — so a
     *  toolbar action (Capture Screenshot) can act on the same session. */
    fun activeSessionId(): String? = currentSessionId
}
