package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.ui.Notifier

/**
 * Start the engine (menu action), enabled only while it isn't running. The start may download
 * an ~85 MB binary on first run, so it runs OFF the EDT under a progress indicator — freezing
 * the IDE on a menu click is the exact bug P0.4b fixed for the tool window; this menu entry
 * had the same one. Reports the real cause when the start fails.
 */
class StartDaemonAction : AnAction() {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    override fun actionPerformed(e: AnActionEvent) {
        val daemonService = service()
        val project = e.project
        ProgressManager.getInstance().run(
            object : Task.Backgroundable(project, "Starting the Mobiscout engine", false) {
                override fun run(indicator: ProgressIndicator) {
                    indicator.isIndeterminate = true
                    indicator.text = "Preparing the engine (first run may download it)…"
                    if (!daemonService.start()) {
                        // Don't fail silently — a menu start with no tool window open would
                        // otherwise show a spinner and then nothing.
                        ApplicationManager.getApplication().invokeLater {
                            Notifier.error(
                                project,
                                "Couldn't start the engine",
                                daemonService.lastStartError ?: "Check your internet connection and try again.",
                            )
                        }
                    }
                }
            },
        )
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabled = !service().isRunning()
    }

    private fun service() = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
}
