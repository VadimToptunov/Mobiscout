package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader

/**
 * STEP 11: JetBrains Plugin Enhancement
 *
 * One-click test generation from Page Object files.
 */
class GenerateTestAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return

        // Check if it's a page object file
        if (!isPageObjectFile(file.name)) {
            showNotification(
                project,
                "Not a Page Object",
                "Please select a Page Object file (login_page.py, etc.)",
                NotificationType.WARNING
            )
            return
        }

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Generating Test", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Analyzing page object and generating test..."

                try {
                    val filePath = file.path

                    // Run test generation via CLI
                    val process = ProcessBuilder(
                        "observe", "generate", "test",
                        "--input", filePath,
                        "--format", "pytest"
                    ).redirectErrorStream(true).start()

                    val output = BufferedReader(InputStreamReader(process.inputStream)).use { it.readText() }
                    val exitCode = process.waitFor()

                    if (exitCode == 0) {
                        // Find the generated test file
                        val testFilePath = getTestFilePath(filePath)
                        val testFile = File(testFilePath)

                        ApplicationManager.getApplication().invokeLater {
                            if (testFile.exists()) {
                                // Open the generated file
                                val virtualFile = LocalFileSystem.getInstance().refreshAndFindFileByIoFile(testFile)
                                if (virtualFile != null) {
                                    FileEditorManager.getInstance(project).openFile(virtualFile, true)
                                }

                                showNotification(
                                    project,
                                    "Test Generated",
                                    "Test file created: ${testFile.name}",
                                    NotificationType.INFORMATION
                                )
                            } else {
                                showNotification(
                                    project,
                                    "Test Generated",
                                    "Test generated successfully",
                                    NotificationType.INFORMATION
                                )
                            }
                        }
                    } else {
                        ApplicationManager.getApplication().invokeLater {
                            showNotification(
                                project,
                                "Generation Failed",
                                "Failed to generate test: $output",
                                NotificationType.ERROR
                            )
                        }
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        showNotification(
                            project,
                            "Generation Error",
                            "Failed to generate test: ${ex.message}",
                            NotificationType.ERROR
                        )
                    }
                }
            }
        })
    }

    private fun isPageObjectFile(fileName: String): Boolean {
        val lowerName = fileName.lowercase()
        return (lowerName.endsWith("_page.py") ||
                lowerName.endsWith("page.kt") ||
                lowerName.endsWith("page.swift") ||
                lowerName.endsWith("_screen.py") ||
                lowerName.endsWith("screen.kt"))
    }

    private fun getTestFilePath(pageObjectPath: String): String {
        val file = File(pageObjectPath)
        val dir = file.parentFile.parentFile // Go up from pages/ to project root
        val testsDir = File(dir, "tests")
        val testFileName = "test_${file.nameWithoutExtension}.py"
        return File(testsDir, testFileName).absolutePath
    }

    private fun showNotification(project: Project, title: String, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("Observe Framework")
            .createNotification(title, content, type)
            .notify(project)
    }

    override fun update(e: AnActionEvent) {
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)
        e.presentation.isEnabledAndVisible = e.project != null && file != null
    }
}
