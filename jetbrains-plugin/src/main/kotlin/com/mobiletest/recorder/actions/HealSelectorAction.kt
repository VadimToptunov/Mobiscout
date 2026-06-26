package com.mobiletest.recorder.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.popup.JBPopupFactory
import com.intellij.openapi.ui.popup.ListPopup
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.psi.PsiFile
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.io.BufferedReader
import java.io.InputStreamReader

/**
 * STEP 11: JetBrains Plugin Enhancement
 *
 * AI-powered selector healing suggestions.
 * When a selector fails, this action suggests alternative selectors.
 */
class HealSelectorAction : AnAction() {

    data class HealingSuggestion(
        val selector_type: String,
        val selector_value: String,
        val confidence: Double,
        val strategy: String
    )

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val psiFile = e.getData(CommonDataKeys.PSI_FILE) ?: return

        // Get the current line's selector
        val currentLine = getCurrentLine(editor)
        if (currentLine == null || !containsSelector(currentLine)) {
            showNotification(
                project,
                "No Selector Found",
                "Please place cursor on a line containing a selector definition",
                NotificationType.WARNING
            )
            return
        }

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Getting Healing Suggestions", true) {
            override fun run(indicator: ProgressIndicator) {
                indicator.isIndeterminate = true
                indicator.text = "Analyzing selector and finding alternatives..."

                try {
                    val filePath = psiFile.virtualFile.path
                    val lineNumber = editor.caretModel.logicalPosition.line + 1

                    // Run healing suggestions via CLI
                    val process = ProcessBuilder(
                        "observe", "heal", "suggest",
                        "--file", filePath,
                        "--line", lineNumber.toString(),
                        "--format", "json"
                    ).redirectErrorStream(true).start()

                    val output = BufferedReader(InputStreamReader(process.inputStream)).use { it.readText() }
                    val exitCode = process.waitFor()

                    if (exitCode == 0 && output.isNotBlank()) {
                        val suggestions = parseHealingSuggestions(output)

                        ApplicationManager.getApplication().invokeLater {
                            if (suggestions.isNotEmpty()) {
                                showSuggestionsPopup(project, editor, psiFile, suggestions)
                            } else {
                                showNotification(
                                    project,
                                    "No Suggestions",
                                    "No alternative selectors found for this element",
                                    NotificationType.INFORMATION
                                )
                            }
                        }
                    } else {
                        ApplicationManager.getApplication().invokeLater {
                            showNotification(
                                project,
                                "Healing Failed",
                                "Could not get healing suggestions",
                                NotificationType.WARNING
                            )
                        }
                    }
                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        showNotification(
                            project,
                            "Healing Error",
                            "Failed to get suggestions: ${ex.message}",
                            NotificationType.ERROR
                        )
                    }
                }
            }
        })
    }

    private fun getCurrentLine(editor: Editor): String? {
        val document = editor.document
        val caretModel = editor.caretModel
        val lineNumber = caretModel.logicalPosition.line

        if (lineNumber >= document.lineCount) return null

        val lineStart = document.getLineStartOffset(lineNumber)
        val lineEnd = document.getLineEndOffset(lineNumber)
        return document.getText(com.intellij.openapi.util.TextRange(lineStart, lineEnd))
    }

    private fun containsSelector(line: String): Boolean {
        val patterns = listOf(
            "By.id",
            "By.xpath",
            "MobileBy",
            "AccessibilityId",
            "accessibility_id",
            "\"id\",",
            "\"xpath\","
        )
        return patterns.any { line.contains(it, ignoreCase = true) }
    }

    private fun parseHealingSuggestions(json: String): List<HealingSuggestion> {
        return try {
            val gson = Gson()
            val type = object : TypeToken<List<HealingSuggestion>>() {}.type
            gson.fromJson(json, type) ?: emptyList()
        } catch (ex: Exception) {
            emptyList()
        }
    }

    private fun showSuggestionsPopup(
        project: Project,
        editor: Editor,
        psiFile: PsiFile,
        suggestions: List<HealingSuggestion>
    ) {
        val items = suggestions.map { suggestion ->
            "${suggestion.selector_type}: ${suggestion.selector_value.take(50)}... " +
                    "(${(suggestion.confidence * 100).toInt()}% confidence, ${suggestion.strategy})"
        }

        val popup = JBPopupFactory.getInstance()
            .createPopupChooserBuilder(items)
            .setTitle("Select Alternative Selector")
            .setItemChosenCallback { selectedItem ->
                val index = items.indexOf(selectedItem)
                if (index >= 0) {
                    applySuggestion(project, editor, psiFile, suggestions[index])
                }
            }
            .createPopup()

        popup.showInBestPositionFor(editor)
    }

    private fun applySuggestion(
        project: Project,
        editor: Editor,
        psiFile: PsiFile,
        suggestion: HealingSuggestion
    ) {
        WriteCommandAction.runWriteCommandAction(project) {
            val document = editor.document
            val caretModel = editor.caretModel
            val lineNumber = caretModel.logicalPosition.line

            val lineStart = document.getLineStartOffset(lineNumber)
            val lineEnd = document.getLineEndOffset(lineNumber)
            val currentLine = document.getText(com.intellij.openapi.util.TextRange(lineStart, lineEnd))

            // Generate new selector line
            val newSelector = generateSelectorCode(currentLine, suggestion)

            // Add healing comment
            val comment = "    # Auto-healed: ${suggestion.strategy} (${(suggestion.confidence * 100).toInt()}% confidence)\n"
            val newLine = comment + newSelector

            document.replaceString(lineStart, lineEnd, newLine)

            showNotification(
                project,
                "Selector Healed",
                "Applied ${suggestion.selector_type} selector with ${(suggestion.confidence * 100).toInt()}% confidence",
                NotificationType.INFORMATION
            )
        }
    }

    private fun generateSelectorCode(originalLine: String, suggestion: HealingSuggestion): String {
        // Extract the variable name from the original line
        val varMatch = Regex("""(\w+)\s*=""").find(originalLine)
        val varName = varMatch?.groupValues?.get(1) ?: "element"

        // Generate the new selector based on language
        return when {
            originalLine.contains(".py") || originalLine.contains("=") && !originalLine.contains("val ") ->
                """    $varName = ("${suggestion.selector_type}", "${suggestion.selector_value}")"""

            originalLine.contains("val ") ->
                """    val $varName = By.${suggestion.selector_type}("${suggestion.selector_value}")"""

            else ->
                """    $varName = ("${suggestion.selector_type}", "${suggestion.selector_value}")"""
        }
    }

    private fun showNotification(project: Project, title: String, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("Observe Framework")
            .createNotification(title, content, type)
            .notify(project)
    }

    override fun update(e: AnActionEvent) {
        val editor = e.getData(CommonDataKeys.EDITOR)
        e.presentation.isEnabledAndVisible = e.project != null && editor != null
    }
}
