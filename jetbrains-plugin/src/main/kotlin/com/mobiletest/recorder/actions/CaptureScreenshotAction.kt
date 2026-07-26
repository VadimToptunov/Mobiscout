package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileChooser.FileChooserFactory
import com.intellij.openapi.fileChooser.FileSaverDescriptor
import com.intellij.openapi.ui.Messages
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService
import java.io.File
import java.util.Base64

class CaptureScreenshotAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        
        // Use the session started from the Screen panel; without one there's no
        // device to screenshot, so tell the user how to get one.
        val sessionId = project.getService(MTRToolWindowService::class.java).screenPanel?.activeSessionId()
        if (sessionId == null) {
            Messages.showInfoMessage(
                project,
                "No active device session. Open the Mobiscout tool window → Screen tab → Start Session first.",
                "No Session",
            )
            return
        }

        try {
            val result = daemonService.getScreenshot(sessionId, "png")
            if (result != null) {
                val base64Data = result.get("data")?.asString ?: return
                val imageBytes = Base64.getDecoder().decode(base64Data)
                
                // Save dialog
                val descriptor = FileSaverDescriptor("Save Screenshot", "Save device screenshot", "png")
                val saveDialog = FileChooserFactory.getInstance().createSaveFileDialog(descriptor, project)
                // Cast the null baseDir to disambiguate the VirtualFile? vs Path? save() overloads.
                val fileWrapper = saveDialog.save(null as com.intellij.openapi.vfs.VirtualFile?, "screenshot.png")
                
                if (fileWrapper != null) {
                    val file = fileWrapper.file
                    file.writeBytes(imageBytes)
                    Messages.showInfoMessage(project, "Screenshot saved to ${file.absolutePath}", "Success")
                }
            }
        } catch (ex: Exception) {
            Messages.showErrorDialog(project, "Failed to capture screenshot: ${ex.message}", "Error")
        }
    }
    
    override fun update(e: AnActionEvent) {
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        e.presentation.isEnabled = daemonService.isRunning()
    }
}
