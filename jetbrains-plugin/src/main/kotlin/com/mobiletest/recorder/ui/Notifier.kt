package com.mobiletest.recorder.ui

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.project.Project

/**
 * One place for the plugin's balloon notifications.
 *
 * Non-blocking replacements for the old modal `Messages.show*` dialogs: an error,
 * warning or status message that needs no answer belongs in the notification balloon,
 * not a popup the user must click through. (Genuine questions — pick one of N, confirm
 * a destructive action — still use a dialog.)
 */
object Notifier {
    private const val GROUP = "Mobiscout Framework"

    fun info(project: Project?, title: String, message: String) =
        show(project, title, message, NotificationType.INFORMATION)

    fun warn(project: Project?, title: String, message: String) =
        show(project, title, message, NotificationType.WARNING)

    fun error(project: Project?, title: String, message: String) =
        show(project, title, message, NotificationType.ERROR)

    private fun show(project: Project?, title: String, message: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup(GROUP)
            .createNotification(title, message, type)
            .notify(project)
    }
}
