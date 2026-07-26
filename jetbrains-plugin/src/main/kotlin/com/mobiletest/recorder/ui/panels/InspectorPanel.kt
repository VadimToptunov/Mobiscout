package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonObject
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBScrollPane
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService
import java.awt.BorderLayout
import javax.swing.*

class InspectorPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService
) {
    private val panel = JPanel(BorderLayout())
    private val xmlTextArea = JTextArea()

    init {
        xmlTextArea.isEditable = false
        xmlTextArea.font = java.awt.Font("Monospaced", java.awt.Font.PLAIN, 12)

        val scrollPane = JBScrollPane(xmlTextArea)

        // Toolbar
        val toolbar = JPanel()
        val captureButton = JButton("Capture UI Tree")
        captureButton.addActionListener {
            captureUiTree()
        }
        toolbar.add(captureButton)

        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(scrollPane, BorderLayout.CENTER)
    }

    /** Fetch the current screen's element tree over the daemon (ui/getTree) for the
     *  session started in the Screen panel, and render it as a readable listing. */
    private fun captureUiTree() {
        val sessionId = project.getService(MTRToolWindowService::class.java).screenPanel?.activeSessionId()
        if (sessionId == null) {
            xmlTextArea.text = "No active device session. Go to the Screen tab and click Start Session first."
            return
        }
        xmlTextArea.text = "Capturing UI tree…"
        (object : SwingWorker<JsonObject?, Void>() {
            override fun doInBackground(): JsonObject? =
                try {
                    daemonService.getClient()
                        ?.call("ui/getTree", mapOf("session_id" to sessionId))
                        ?.getResultOrThrow()
                } catch (e: Exception) {
                    null
                }

            override fun done() {
                val result = get()
                xmlTextArea.text = if (result != null) formatTree(result) else "Failed to capture UI tree."
                xmlTextArea.caretPosition = 0
            }
        }).execute()
    }

    /** One line per element: type, a label (resource-id/text/content-desc), bounds,
     *  and a tap marker — the flat tree the engine's ui/getTree returns. */
    private fun formatTree(tree: JsonObject): String {
        val platform = tree.get("platform")?.asString ?: "?"
        val toolkit = tree.get("toolkit")?.asString ?: "?"
        val elements = tree.getAsJsonArray("elements") ?: return "(no elements)"
        val sb = StringBuilder()
        sb.append("platform=$platform  toolkit=$toolkit  elements=${elements.size()}\n\n")
        for (element in elements) {
            val e = element.asJsonObject
            val type = e.get("type")?.asString ?: "generic"
            val label = listOf("resource_id", "text", "content_desc")
                .firstNotNullOfOrNull { e.get(it)?.asString?.takeIf { s -> s.isNotBlank() } } ?: ""
            val bounds = e.getAsJsonArray("bounds")?.joinToString(",") { it.asString } ?: ""
            val tap = if (e.get("clickable")?.asBoolean == true) " [tap]" else ""
            sb.append("%-10s %-40s [%s]%s\n".format(type, label.take(40), bounds, tap))
        }
        return sb.toString()
    }

    fun getPanel(): JComponent = panel
}
