package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileChooser.FileChooserFactory
import com.intellij.openapi.fileChooser.FileSaverDescriptor
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService
import java.io.File
import java.util.Base64
import com.mobiletest.recorder.ui.Notifier

class CaptureScreenshotAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        
        // Use the session started from the Screen panel; without one there's no
        // device to screenshot, so tell the user how to get one.
        val sessionId = project.getService(MTRToolWindowService::class.java).screenPanel?.activeSessionId()
        if (sessionId == null) {
            Notifier.info(
                project,
                "No Session",
                "No active device session. Open the Mobiscout tool window → Screen tab → Start Session first.",
            )
            return
        }

        // The screenshot RPC blocks (an Appium capture takes seconds; the client's timeout
        // backstop is 600 s) — run it off the EDT, then save + notify back on the EDT.
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Capturing screenshot", false) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                val imageBytes = try {
                    val result = daemonService.getScreenshot(sessionId, "png")
                    val base64Data = result?.get("data")?.asString ?: return
                    Base64.getDecoder().decode(base64Data)
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        Notifier.error(project, "Error", "Failed to capture screenshot: ${ex.message}")
                    }
                    return
                }
                ApplicationManager.getApplication().invokeLater { saveScreenshot(project, imageBytes) }
            }
        })
    }

    /** Prompt for a location and write the PNG — on the EDT (the file-save dialog needs it). */
    private fun saveScreenshot(project: Project, imageBytes: ByteArray) {
        val descriptor = FileSaverDescriptor("Save Screenshot", "Save device screenshot", "png")
        val saveDialog = FileChooserFactory.getInstance().createSaveFileDialog(descriptor, project)
        // Cast the null baseDir to disambiguate the VirtualFile? vs Path? save() overloads.
        val fileWrapper = saveDialog.save(null as VirtualFile?, "screenshot.png") ?: return
        val file = fileWrapper.file
        file.writeBytes(imageBytes)
        Notifier.info(project, "Success", "Screenshot saved to ${file.absolutePath}")
    }

    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    override fun update(e: AnActionEvent) {
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        e.presentation.isEnabled = daemonService.isRunning()
    }
}
