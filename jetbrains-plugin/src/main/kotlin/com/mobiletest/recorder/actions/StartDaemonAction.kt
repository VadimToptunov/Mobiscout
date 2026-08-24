package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.mobiletest.recorder.services.MTRDaemonService

/**
 * Restart the engine (menu action). The start may download an ~85 MB binary on first run, so
 * it runs OFF the EDT under a progress indicator — freezing the IDE on a menu click is the
 * exact bug P0.4b fixed for the tool window; this menu entry had the same one.
 */
class StartDaemonAction : AnAction() {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    override fun actionPerformed(e: AnActionEvent) {
        val daemonService = service()
        ProgressManager.getInstance().run(
            object : Task.Backgroundable(e.project, "Starting the Mobiscout engine", false) {
                override fun run(indicator: ProgressIndicator) {
                    indicator.isIndeterminate = true
                    indicator.text = "Preparing the engine (first run may download it)…"
                    daemonService.start()
                }
            },
        )
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabled = !service().isRunning()
    }

    private fun service() = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
}
