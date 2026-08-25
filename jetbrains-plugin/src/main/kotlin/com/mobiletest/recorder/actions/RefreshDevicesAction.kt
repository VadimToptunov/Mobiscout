package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService

class RefreshDevicesAction : AnAction() {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        // Drive the live Devices panel the tool window published; a no-op if the
        // tool window was never opened.
        project.getService(MTRToolWindowService::class.java).devicesPanel?.refreshDevices()
    }
    
    override fun update(e: AnActionEvent) {
        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        e.presentation.isEnabled = daemonService.isRunning()
    }
}
