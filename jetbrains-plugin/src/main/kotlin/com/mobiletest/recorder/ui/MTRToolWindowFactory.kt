package com.mobiletest.recorder.ui

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.mobiletest.recorder.wizard.SetupWizard

/**
 * Factory for creating the Mobile Test Recorder tool window.
 *
 * Automatically shows setup wizard on first launch if configuration
 * is incomplete.
 */
class MTRToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val mtrToolWindow = MTRToolWindow(project)
        val contentFactory = ContentFactory.getInstance()
        val content = contentFactory.createContent(mtrToolWindow.getContent(), "", false)
        toolWindow.contentManager.addContent(content)

        // Check if setup wizard should be shown (first run)
        checkAndShowSetupWizard(project)
    }

    private fun checkAndShowSetupWizard(project: Project) {
        if (SetupWizard.shouldShowWizard()) {
            // Show wizard in a separate invocation to allow tool window to fully initialize
            ApplicationManager.getApplication().invokeLater {
                SetupWizard.showWizard(project)
            }
        }
    }

    override fun shouldBeAvailable(project: Project): Boolean = true
}
