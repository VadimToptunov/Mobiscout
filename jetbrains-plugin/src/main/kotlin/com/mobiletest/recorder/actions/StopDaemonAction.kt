package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.mobiletest.recorder.services.MTRDaemonService

class StopDaemonAction : AnAction() {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    override fun actionPerformed(e: AnActionEvent) {
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        daemonService.stop()
    }
    
    override fun update(e: AnActionEvent) {
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        e.presentation.isEnabled = daemonService.isRunning()
    }
}
