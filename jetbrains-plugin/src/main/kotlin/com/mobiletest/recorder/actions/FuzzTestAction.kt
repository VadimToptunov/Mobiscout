package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.ui.components.JBTextField
import com.intellij.ui.dsl.builder.panel
import java.io.BufferedReader
import java.io.InputStreamReader
import javax.swing.JComponent

/**
 * STEP 11: JetBrains Plugin Enhancement
 *
 * Run fuzzing tests on UI elements from the IDE.
 */
class FuzzTestAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return

        // Show configuration dialog
        val dialog = FuzzConfigDialog(project)
        if (!dialog.showAndGet()) {
            return
        }

        val targetId = dialog.getTargetId()
        val inputType = dialog.getInputType()
        val count = dialog.getCount()

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Running Fuzz Test", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = false
                indicator.text = "Fuzzing $targetId..."

                try {
                    // Run fuzzing via CLI
                    val process = ProcessBuilder(
                        "observe", "fuzz", "ui", targetId,
                        "--input-type", inputType,
                        "--count", count.toString(),
                        "--output", "${project.basePath}/fuzz_results.json"
                    ).redirectErrorStream(true).start()

                    val output = BufferedReader(InputStreamReader(process.inputStream)).use { reader ->
                        var line: String?
                        val sb = StringBuilder()
                        var progress = 0
                        while (reader.readLine().also { line = it } != null) {
                            sb.appendLine(line)
                            progress++
                            indicator.fraction = progress.toDouble() / count
                        }
                        sb.toString()
                    }

                    val exitCode = process.waitFor()

                    ApplicationManager.getApplication().invokeLater {
                        if (exitCode == 0) {
                            showNotification(
                                project,
                                "Fuzz Test Complete",
                                "Fuzzing completed. Results saved to fuzz_results.json",
                                NotificationType.INFORMATION
                            )
                        } else {
                            showNotification(
                                project,
                                "Fuzz Test Issues",
                                "Fuzzing completed with issues. Check fuzz_results.json",
                                NotificationType.WARNING
                            )
                        }
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        showNotification(
                            project,
                            "Fuzz Test Error",
                            "Failed to run fuzz test: ${ex.message}",
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

    private class FuzzConfigDialog(project: Project) : DialogWrapper(project) {
        private val targetIdField = JBTextField("username_input")
        private val inputTypeField = JBTextField("text")
        private val countField = JBTextField("50")

        init {
            title = "Configure Fuzz Test"
            init()
        }

        override fun createCenterPanel(): JComponent {
            return panel {
                row("Target Element ID:") {
                    cell(targetIdField)
                        .comment("The ID of the UI element to fuzz")
                }
                row("Input Type:") {
                    cell(inputTypeField)
                        .comment("text, email, number, password, url, json")
                }
                row("Number of Inputs:") {
                    cell(countField)
                        .comment("Number of fuzz inputs to generate")
                }
            }
        }

        fun getTargetId(): String = targetIdField.text
        fun getInputType(): String = inputTypeField.text
        fun getCount(): Int = countField.text.toIntOrNull() ?: 50
    }
}
