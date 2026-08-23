package com.mobiletest.recorder.ui.panels

import com.intellij.ide.BrowserUtil
import com.intellij.openapi.project.Project
import com.intellij.ui.JBColor
import com.intellij.ui.components.ActionLink
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.JBUI
import com.mobiletest.recorder.services.MTRDaemonService
import java.awt.BorderLayout
import java.awt.Component
import javax.swing.Box
import javax.swing.BoxLayout
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.SwingWorker

/**
 * Surfaces the Mobiscout-PRO layer inside the (free, open-core) plugin: the active
 * tier and the PRO-only features, with an upgrade link. The engine is unlimited on
 * its own; PRO adds cloud grids, reporting and re-crawl automation. Read-only — the
 * funnel, not a paywall on the free engine.
 */
class ProPanel(
    private val project: Project,
    private val daemonService: MTRDaemonService,
) {
    private val panel = JPanel(BorderLayout())
    private val tierLabel = JBLabel("Tier: detecting…")

    // Available now (bring your own account): cloud grid ships in the engine.
    private val available = listOf(
        "Cloud device grid" to
            "Run a generated kit on BrowserStack / Sauce Labs / LambdaTest with your own account: " +
            "`mobiscout grid run <kit> --provider … --device …` (credentials from env vars, nothing stored).",
    )

    // The premium layer (Mobiscout-PRO).
    private val features = listOf(
        "TestRail reporting" to "Push a run's results into TestRail, one result per case.",
        "Crawl dashboards" to "A shareable, self-contained HTML report of a crawl.",
        "Network mocking" to "Deterministic offline responses (WireMock) — no flaky backend.",
        "Auto re-crawl → PR" to "Diff a fresh crawl against your tests → a ready git patch + PR.",
    )

    init {
        val content = JPanel().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
            border = JBUI.Borders.empty(12, 16)
        }

        content.add(left(JBLabel("<html><b>Mobiscout PRO</b></html>")))
        content.add(Box.createVerticalStrut(2))
        content.add(left(JBLabel("The premium layer over the open-core engine.").apply {
            foreground = JBColor(0x9E9E9E, 0x808080)
        }))
        content.add(Box.createVerticalStrut(8))
        content.add(left(tierLabel))
        content.add(Box.createVerticalStrut(12))

        content.add(left(JBLabel("<html><b>Available now</b></html>")))
        content.add(Box.createVerticalStrut(6))
        for ((name, desc) in available) {
            content.add(left(JBLabel("<html><b>$name</b> — $desc</html>")))
            content.add(Box.createVerticalStrut(6))
        }
        content.add(Box.createVerticalStrut(8))

        content.add(left(JBLabel("<html><b>Mobiscout PRO (planned)</b></html>")))
        content.add(Box.createVerticalStrut(6))
        for ((name, desc) in features) {
            content.add(left(JBLabel("<html><b>$name</b> — $desc</html>")))
            content.add(Box.createVerticalStrut(6))
        }

        content.add(Box.createVerticalStrut(8))
        content.add(left(ActionLink("Learn more") {
            BrowserUtil.browse("https://github.com/VadimToptunov/Mobiscout")
        }))

        panel.add(content, BorderLayout.NORTH)
    }

    private fun left(c: JComponent): JComponent = c.apply { alignmentX = Component.LEFT_ALIGNMENT }

    /** Query the engine's active tier (needs the daemon running) and show it. */
    fun refreshTier() {
        (object : SwingWorker<String, Void>() {
            override fun doInBackground(): String {
                val status = try {
                    daemonService.licenseStatus()
                } catch (e: Exception) {
                    null
                } ?: return "Tier: detecting…"
                val features = status.getAsJsonArray("features")?.map { it.asString } ?: emptyList()
                return when {
                    features.any { it != "*" } -> "Tier: PRO — licensed ✓"
                    status.get("unlimited")?.asBoolean == true -> "Tier: Open-core (unlimited)"
                    else -> "Tier: Free — quota-limited (upgrade for unlimited + PRO features)"
                }
            }

            override fun done() {
                tierLabel.text = get()
            }
        }).execute()
    }

    fun getPanel(): JComponent = panel
}
