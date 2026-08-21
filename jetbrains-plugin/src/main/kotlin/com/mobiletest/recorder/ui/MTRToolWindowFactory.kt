package com.mobiletest.recorder.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory

/**
 * Factory for the Mobiscout tool window. There is no setup step — the engine starts
 * itself when the window opens (see [MTRToolWindow]), and the crawl config is filled
 * from the project via "Detect from project…" in Generate Test Kit. One flow, no wizard.
 */
class MTRToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val mtrToolWindow = MTRToolWindow(project)
        val content = ContentFactory.getInstance().createContent(mtrToolWindow.getContent(), "", false)
        toolWindow.contentManager.addContent(content)
    }

    override fun shouldBeAvailable(project: Project): Boolean = true
}
