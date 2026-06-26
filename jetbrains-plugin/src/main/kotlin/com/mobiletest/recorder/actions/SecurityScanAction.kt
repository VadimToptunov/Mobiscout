package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.mobiletest.recorder.services.MTRDaemonService
import java.io.BufferedReader
import java.io.InputStreamReader

/**
 * STEP 11: JetBrains Plugin Enhancement
 *
 * Action to run security scan on the project using Observe CLI.
 */
class SecurityScanAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Running Security Scan", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Scanning for security vulnerabilities..."

                try {
                    val projectPath = project.basePath ?: return

                    // Run security scan via CLI
                    val process = ProcessBuilder(
                        "observe", "security", "secrets", projectPath, "--format", "json"
                    ).redirectErrorStream(true).start()

                    val output = BufferedReader(InputStreamReader(process.inputStream)).use { it.readText() }
                    val exitCode = process.waitFor()

                    ApplicationManager.getApplication().invokeLater {
                        when (exitCode) {
                            0 -> showNotification(
                                project,
                                "Security Scan Complete",
                                "No vulnerabilities found!",
                                NotificationType.INFORMATION
                            )
                            1 -> showNotification(
                                project,
                                "Security Issues Found",
                                "Found potential security issues. Check the Problems tool window.",
                                NotificationType.WARNING
                            )
                            else -> showNotification(
                                project,
                                "Security Scan Failed",
                                "Scan failed with exit code $exitCode",
                                NotificationType.ERROR
                            )
                        }
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        showNotification(
                            project,
                            "Security Scan Error",
                            "Failed to run scan: ${ex.message}",
                            NotificationType.ERROR
                        )
                    }
                }
            }
        })
    }

    private fun showNotification(project: Project, title: String, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("Observe Framework")
            .createNotification(title, content, type)
            .notify(project)
    }

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }
}
