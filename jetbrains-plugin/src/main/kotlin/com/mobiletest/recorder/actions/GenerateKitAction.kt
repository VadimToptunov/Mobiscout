package com.mobiletest.recorder.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.ui.Messages
import com.intellij.notification.NotificationGroupManager
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.ui.GenerateKitDialog

/**
 * "Generate Test Kit" — opens a parameter form, then runs the engine's
 * parameterized `kit/generate` over the daemon: crawls the app you described and
 * writes the inventory, interaction graph, tests (in your language) and — for a
 * new project — a runnable scaffold. Not a magic button; you configure it.
 */
class GenerateKitAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val dialog = GenerateKitDialog(project)
        if (!dialog.showAndGet()) return
        val params = dialog.params()

        val daemonService = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        if (daemonService.getClient() == null && !daemonService.start()) {
            Messages.showErrorDialog(project, "Could not start the mobiscout daemon. Is the CLI installed?", "Error")
            return
        }

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Generating test kit", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Crawling ${params["package"]} and generating tests…"
                try {
                    val result = daemonService.getClient()?.call("kit/generate", params)?.getResultOrThrow()
                        ?: throw IllegalStateException("No response from daemon")

                    val screens = result.get("screens")?.asInt ?: 0
                    val cases = result.get("cases")?.asInt ?: 0
                    val output = result.get("output")?.asString ?: params["output"]
                    val scaffolded = result.get("scaffolded")?.let { if (it.isJsonNull) null else it.asString }
                    val extra = if (scaffolded != null) " · runnable $scaffolded project" else ""

                    ApplicationManager.getApplication().invokeLater {
                        notify(
                            project,
                            "Test kit generated",
                            "$screens screen(s), $cases test case(s)$extra\nWritten to: $output",
                            NotificationType.INFORMATION,
                        )
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        notify(project, "Generation failed", ex.message ?: "Unknown error", NotificationType.ERROR)
                    }
                }
            }
        })
    }

    private fun notify(project: com.intellij.openapi.project.Project, title: String, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("Mobiscout Framework")
            .createNotification(title, content, type)
            .notify(project)
    }
}
