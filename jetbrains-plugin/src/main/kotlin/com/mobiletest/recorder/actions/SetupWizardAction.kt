package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages
import com.mobiletest.recorder.wizard.SetupWizard

/**
 * Action to launch the Setup Wizard.
 *
 * Can be triggered from the Tools menu or Welcome screen.
 */
class SetupWizardAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project
        val completed = SetupWizard.showWizard(project)

        if (completed) {
            Messages.showInfoMessage(
                project,
                "Mobile Test Recorder has been configured successfully!\n\n" +
                "Open View → Tool Windows → Mobile Test Recorder to get started.",
                "Setup Complete"
            )
        }
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = true
    }
}
