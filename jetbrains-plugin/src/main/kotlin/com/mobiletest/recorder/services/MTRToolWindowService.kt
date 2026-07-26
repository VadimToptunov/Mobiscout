package com.mobiletest.recorder.services

import com.intellij.openapi.components.Service
import com.mobiletest.recorder.ui.panels.DevicesPanel
import com.mobiletest.recorder.ui.panels.ScreenPanel

/**
 * Project-scoped handle to the live tool-window panels.
 *
 * Toolbar/menu actions are instantiated by the platform without any reference to
 * the panels they act on, so they can't reach them directly. The tool window
 * registers its panels here on creation, and actions look them up by project —
 * e.g. [com.mobiletest.recorder.actions.RefreshDevicesAction] drives
 * [DevicesPanel.refreshDevices]. References are cleared when the window closes so
 * we don't pin a disposed panel.
 */
@Service(Service.Level.PROJECT)
class MTRToolWindowService {
    @Volatile
    var devicesPanel: DevicesPanel? = null

    @Volatile
    var screenPanel: ScreenPanel? = null
}
