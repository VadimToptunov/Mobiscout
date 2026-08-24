package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonObject
import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.project.Project
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextField
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.ui.DeviceItem
import com.mobiletest.recorder.ui.DeviceList
import com.mobiletest.recorder.ui.Notifier
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

    // The device to mirror. A field (not a local) so the toolbar actions can read the
    // selection in their update() to enable/disable themselves.
    private val deviceCombo = JComboBox<DeviceItem>()

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
            if (currentImage == null) {
                // Empty state: guide the user instead of showing a blank dark panel.
                val g2d = g as Graphics2D
                g2d.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
                g2d.color = JBColor(0x9E9E9E, 0x808080)
                val msg = "Load a device and Start Session to mirror the screen"
                val fm = g2d.fontMetrics
                g2d.drawString(msg, (width - fm.stringWidth(msg)) / 2, height / 2)
            }
        }
    }
    
    init {
        imagePanel.background = JBColor(0x2B2B2B, 0x1E1E1E)
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

        // Native ActionToolbar for the actions; the input fields (device, app, server,
        // launch args) sit alongside it — those can't live inside an ActionToolbar. Action
        // enablement derives from the live session state via update(), so there's no manual
        // button toggling to keep in sync.
        val actions = DefaultActionGroup().apply {
            add(LoadDevicesAction())
            add(StartSessionAction())
            add(StopSessionAction())
            add(CaptureAction())
            add(RefreshAction())
        }
        val actionToolbar = ActionManager.getInstance()
            .createActionToolbar(ActionPlaces.TOOLWINDOW_CONTENT, actions, true)
        actionToolbar.targetComponent = panel

        val toolbar = JPanel()
        toolbar.layout = BoxLayout(toolbar, BoxLayout.X_AXIS)
        toolbar.add(JLabel("Device:"))
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(deviceCombo)
        toolbar.add(Box.createHorizontalStrut(8))
        toolbar.add(JLabel("App:"))
        toolbar.add(appField)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(JLabel("Server:"))
        toolbar.add(serverField)
        toolbar.add(Box.createHorizontalStrut(5))
        toolbar.add(JLabel("Launch args:"))
        toolbar.add(launchArgsField)
        toolbar.add(Box.createHorizontalStrut(8))
        toolbar.add(actionToolbar.component)
        toolbar.add(Box.createHorizontalGlue())

        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(scrollPane, BorderLayout.CENTER)
    }

    private inner class LoadDevicesAction :
        AnAction("Load Devices", "Reload the running devices", AllIcons.Actions.Refresh) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun actionPerformed(e: AnActionEvent) = loadDevices()
    }

    private inner class StartSessionAction :
        AnAction("Start Session", "Start mirroring the selected device", AllIcons.Actions.Execute) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            // A session needs a device, and only one at a time.
            e.presentation.isEnabled = currentSessionId == null && deviceCombo.selectedItem is DeviceItem
        }

        override fun actionPerformed(e: AnActionEvent) {
            (deviceCombo.selectedItem as? DeviceItem)?.let { startSession(it) }
        }
    }

    private inner class StopSessionAction :
        AnAction("Stop Session", "Stop mirroring", AllIcons.Actions.Suspend) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = currentSessionId != null
        }

        override fun actionPerformed(e: AnActionEvent) = stopSession()
    }

    private inner class CaptureAction :
        AnAction("Capture Screen", "Capture the current screen", AllIcons.Actions.Dump) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = currentSessionId != null
        }

        override fun actionPerformed(e: AnActionEvent) = captureScreen()
    }

    private inner class RefreshAction :
        AnAction("Refresh", "Re-capture the current screen", AllIcons.Actions.Refresh) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = currentSessionId != null
        }

        override fun actionPerformed(e: AnActionEvent) = captureScreen()
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

    private fun startSession(device: DeviceItem) {
        (object : SwingWorker<String?, Void>() {
            override fun doInBackground(): String? {
                try {
                    val deviceId = device.id
                    currentDeviceId = deviceId

                    // Give the daemon what it needs to open the right driver: the
                    // platform (adb vs Appium), and for iOS the app bundle id, the
                    // Appium server, and any launch args to start past a gate.
                    val launchArgs = launchArgsField.text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
                    val params = buildMap {
                        put("device_id", deviceId)
                        put("backend", "appium")
                        put("platform", device.platform)
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
                    // The toolbar actions enable/disable themselves off currentSessionId.
                    captureScreen() // auto-capture the first screenshot
                } else {
                    // The daemon's preflight returns an actionable, often multi-line message
                    // (e.g. the ANDROID_HOME fix). Show it as a non-modal balloon — the full
                    // text stays readable/copyable in the Event Log — instead of a modal
                    // JOptionPane that freezes the whole IDE until dismissed.
                    Notifier.error(project, "Could not start session", lastStartError ?: "Failed to start session")
                }
            }
        }).execute()
    }
    
    private fun stopSession() {
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
                    // Clearing currentSessionId flips the toolbar actions back via update().
                    currentSessionId = null
                    currentImage = null
                    imagePanel.repaint()
                }
            }).execute()
        }
    }
    
    private fun captureScreen() {
        val sessionId = currentSessionId ?: return
        (object : SwingWorker<BufferedImage?, Void>() {
            private var error: String? = null

            override fun doInBackground(): BufferedImage? {
                return try {
                    val result = daemonService.getScreenshot(sessionId, "png")
                    val base64Data = result?.get("data")?.asString
                        ?: run { error = "The engine returned no screenshot data."; return null }
                    val imageBytes = Base64.getDecoder().decode(base64Data)
                    ImageIO.read(ByteArrayInputStream(imageBytes))
                } catch (e: Exception) {
                    error = e.message ?: e.toString()
                    null
                }
            }

            override fun done() {
                val img = get()
                if (img != null) {
                    currentImage = img
                    imagePanel.repaint()
                } else {
                    // Don't blank a working mirror on a transient capture failure — keep the
                    // last frame on screen and say (non-modally) what went wrong.
                    Notifier.warn(project, "Screenshot", error ?: "Couldn't capture the screen.")
                }
            }
        }).execute()
    }
    
    private fun performTap(x: Int, y: Int) {
        val sessionId = currentSessionId ?: return
        (object : SwingWorker<String?, Void>() {
            // Returns an error message, or null on success.
            override fun doInBackground(): String? {
                return try {
                    daemonService.getClient()
                        ?.call("action/tap", mapOf("session_id" to sessionId, "x" to x, "y" to y))
                        ?.getResultOrThrow()
                    // Let the tapped screen settle (a navigation/animation) before re-capturing.
                    Thread.sleep(POST_TAP_SETTLE_MS)
                    null
                } catch (e: Exception) {
                    e.message ?: e.toString()
                }
            }

            override fun done() {
                // A tap that the daemon rejected used to vanish silently; surface it.
                get()?.let { Notifier.warn(project, "Tap failed", it) }
                // Auto-refresh the mirror whether or not the tap succeeded.
                captureScreen()
            }
        }).execute()
    }

    fun getPanel(): JComponent = panel

    /** The id of the live device session, or null if none is started — so a
     *  toolbar action (Capture Screenshot) can act on the same session. */
    fun activeSessionId(): String? = currentSessionId

    companion object {
        /** Pause after a tap so a resulting navigation/animation finishes before we re-capture. */
        private const val POST_TAP_SETTLE_MS = 500L
    }
}
