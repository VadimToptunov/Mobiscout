package com.mobiletest.recorder.ui.panels

import com.google.gson.JsonObject
import com.intellij.icons.AllIcons
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.ide.CopyPasteManager
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBScrollPane
import com.mobiletest.recorder.services.MTRDaemonService
import com.mobiletest.recorder.services.MTRToolWindowService
import com.mobiletest.recorder.ui.Notifier
import java.awt.BorderLayout
import java.awt.Font
import java.awt.datatransfer.StringSelection
import javax.swing.*

class InspectorPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService
) {
    private val panel = JPanel(BorderLayout())
    private val headerLabel = JLabel("Capture the UI tree of the live session, then pick an element.")

    // One selectable row per element — the JsonObject rides along so "Copy locator" and
    // "Generate selector" act on the real attributes, not a re-parse of the display line.
    private val listModel = DefaultListModel<ElementRow>()
    private val elementList = JBList(listModel)

    // Shows the generated self-healing selector for the picked element.
    private val detailArea = JTextArea(5, 0)

    // Platform of the last captured tree — selector/generate needs it (android vs ios).
    private var currentPlatform = "android"

    /** One element as ui/getTree reports it, plus its formatted list label. */
    data class ElementRow(val element: JsonObject, val display: String) {
        override fun toString(): String = display
    }

    init {
        detailArea.isEditable = false
        detailArea.font = Font("Monospaced", Font.PLAIN, 12)
        elementList.font = Font("Monospaced", Font.PLAIN, 12)
        elementList.selectionMode = ListSelectionModel.SINGLE_SELECTION

        // Native ActionToolbar — Copy locator / Generate selector enable themselves via update()
        // only when an element is picked (no manual ListSelectionListener toggling).
        val actions = DefaultActionGroup().apply {
            add(CaptureTreeAction())
            add(CopyLocatorAction())
            add(GenerateSelectorAction())
        }
        val toolbar = ActionManager.getInstance()
            .createActionToolbar(ActionPlaces.TOOLWINDOW_CONTENT, actions, true)
        toolbar.targetComponent = panel

        // Element list on top, generated-selector detail below.
        val split = JSplitPane(
            JSplitPane.VERTICAL_SPLIT,
            JBScrollPane(elementList),
            JBScrollPane(detailArea),
        ).apply { resizeWeight = 0.75 }

        val center = JPanel(BorderLayout())
        center.add(headerLabel, BorderLayout.NORTH)
        center.add(split, BorderLayout.CENTER)

        panel.add(toolbar.component, BorderLayout.NORTH)
        panel.add(center, BorderLayout.CENTER)
    }

    private inner class CaptureTreeAction :
        AnAction("Capture UI Tree", "Fetch the current screen's element tree", AllIcons.Actions.Refresh) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun actionPerformed(e: AnActionEvent) = captureUiTree()
    }

    private inner class CopyLocatorAction :
        AnAction("Copy locator", "Copy the most stable locator for the selected element", AllIcons.Actions.Copy) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = elementList.selectedValue != null
        }

        override fun actionPerformed(e: AnActionEvent) = copyLocator()
    }

    private inner class GenerateSelectorAction :
        AnAction("Generate selector", "Generate a ranked self-healing selector", AllIcons.Actions.IntentionBulb) {
        override fun getActionUpdateThread() = ActionUpdateThread.EDT
        override fun update(e: AnActionEvent) {
            e.presentation.isEnabled = elementList.selectedValue != null
        }

        override fun actionPerformed(e: AnActionEvent) = generateSelector()
    }

    /** Fetch the current screen's element tree over the daemon (ui/getTree) for the
     *  session started in the Screen panel, and list its elements. */
    private fun captureUiTree() {
        val sessionId = project.getService(MTRToolWindowService::class.java).screenPanel?.activeSessionId()
        if (sessionId == null) {
            headerLabel.text = "No active device session. Go to the Screen tab and click Start Session first."
            listModel.clear()
            return
        }
        headerLabel.text = "Capturing UI tree…"
        listModel.clear()
        detailArea.text = ""
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
                if (result == null) {
                    headerLabel.text = "Failed to capture UI tree."
                    return
                }
                populate(result)
            }
        }).execute()
    }

    /** Fill the list from a ui/getTree result and update the header. */
    private fun populate(tree: JsonObject) {
        currentPlatform = tree.get("platform")?.asString ?: "android"
        val toolkit = tree.get("toolkit")?.asString ?: "?"
        val elements = tree.getAsJsonArray("elements")
        headerLabel.text = "platform=$currentPlatform  toolkit=$toolkit  elements=${elements?.size() ?: 0}"
        listModel.clear()
        elements?.forEach { listModel.addElement(rowFor(it.asJsonObject)) }
    }

    /** One list row: type, a label (resource-id/text/content-desc), bounds, and a tap marker. */
    private fun rowFor(e: JsonObject): ElementRow {
        val type = e.get("type")?.asString ?: "generic"
        val label = attr(e, "resource_id") ?: attr(e, "text") ?: attr(e, "content_desc") ?: ""
        val bounds = e.getAsJsonArray("bounds")?.joinToString(",") { it.asString } ?: ""
        val tap = if (e.get("clickable")?.asBoolean == true) " [tap]" else ""
        return ElementRow(e, "%-10s %-40s [%s]%s".format(type, label.take(40), bounds, tap))
    }

    /** Copy a plain best-effort locator (the most stable attribute) for the picked element. */
    private fun copyLocator() {
        val e = elementList.selectedValue?.element ?: return
        val locator = attr(e, "resource_id")?.let { "resource-id=$it" }
            ?: attr(e, "content_desc")?.let { "content-desc=$it" }
            ?: attr(e, "text")?.let { "text=$it" }
        if (locator == null) {
            Notifier.warn(project, "Copy locator", "This element has no stable id / text / content-desc to key on.")
            return
        }
        CopyPasteManager.getInstance().setContents(StringSelection(locator))
        Notifier.info(project, "Locator copied", locator)
    }

    /** Ask the engine for a ranked, self-healing selector for the picked element, show it
     *  in the detail pane and copy it to the clipboard. */
    private fun generateSelector() {
        val e = elementList.selectedValue?.element ?: return
        detailArea.text = "Generating selector…"
        (object : SwingWorker<JsonObject?, Void>() {
            override fun doInBackground(): JsonObject? =
                try {
                    daemonService.getClient()
                        ?.call("selector/generate", mapOf("platform" to currentPlatform, "element" to elementParams(e)))
                        ?.getResultOrThrow()
                } catch (ex: Exception) {
                    null
                }

            override fun done() {
                val result = get()
                if (result == null || result.get("found")?.asBoolean != true) {
                    detailArea.text = "No self-healing selector could be built for this element."
                    return
                }
                val rendered = renderSelector(result)
                detailArea.text = rendered
                detailArea.caretPosition = 0
                CopyPasteManager.getInstance().setContents(StringSelection(rendered))
                Notifier.info(project, "Selector generated", "Copied to the clipboard.")
            }
        }).execute()
    }

    /** The attribute subset selector/generate accepts as its {element} form. */
    private fun elementParams(e: JsonObject): Map<String, Any> {
        val params = LinkedHashMap<String, Any>()
        attr(e, "resource_id")?.let { params["resource_id"] = it }
        attr(e, "text")?.let { params["text"] = it }
        attr(e, "content_desc")?.let { params["content_desc"] = it }
        attr(e, "class")?.let { params["class"] = it }
        (attr(e, "class_name"))?.let { params.putIfAbsent("class", it) }
        params["clickable"] = e.get("clickable")?.asBoolean ?: false
        e.getAsJsonArray("bounds")?.let { b -> params["bounds"] = b.map { it.asInt } }
        return params
    }

    /** Render the {type, label, selector} result — the primary selector plus its ranked
     *  fallbacks — as readable `strategy = value (score)` lines. */
    private fun renderSelector(result: JsonObject): String {
        val sb = StringBuilder()
        result.get("type")?.asString?.let { sb.append("# $it") }
        result.get("label")?.asString?.takeIf { it.isNotBlank() }?.let { sb.append("  \"$it\"") }
        sb.append("\n")
        val selector = result.getAsJsonObject("selector") ?: return sb.toString().trimEnd()
        sb.append(selectorLine(selector))
        selector.getAsJsonArray("fallbacks")?.forEach { fb ->
            sb.append("\n  ↳ fallback: ").append(selectorLine(fb.asJsonObject))
        }
        return sb.toString().trimEnd()
    }

    /** One `strategy = value (score 0.90)` line from a selector dict. */
    private fun selectorLine(s: JsonObject): String {
        val strategy = s.get("strategy")?.asString ?: "?"
        val value = s.get("value")?.asString ?: ""
        val score = s.get("score")?.takeIf { !it.isJsonNull }?.asDouble
        val scoreStr = score?.let { "  (score %.2f)".format(it) } ?: ""
        return "$strategy = $value$scoreStr"
    }

    /** A non-blank string attribute, or null. */
    private fun attr(e: JsonObject, key: String): String? =
        e.get(key)?.asString?.takeIf { it.isNotBlank() }

    fun getPanel(): JComponent = panel
}
