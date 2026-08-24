package com.mobiletest.recorder.ui

import com.intellij.openapi.application.ApplicationManager
import com.mobiletest.recorder.services.MTRDaemonService

/**
 * One device as the engine reports it. [toString] is the combo label; the id and platform
 * travel *with* the item, so a selection is resolved by field access, never by parsing them
 * back out of the label — a device name with parentheses ("iPad Pro (11-inch)") used to break
 * that (`substringAfter("(")` returned "11-inch" instead of the UDID). [status] ("booted" /
 * "device" / "shutdown" / "offline" …) lets a caller keep only the running devices.
 */
data class DeviceItem(val id: String, val name: String, val platform: String, val status: String = "") {
    override fun toString(): String = if (name.isNotBlank()) "$name ($id)" else id
}

/**
 * The single source of the device list for every panel and the Generate-kit dialog. Replaces
 * the near-identical loaders those used to hand-roll — two different label parsers (one buggy)
 * and disagreeing platform defaults. The panels bind [DeviceItem] directly; the dialog's combo
 * is editable-String, so it reads the ids/names/platforms off these items but keeps its own combo.
 */
object DeviceList {
    /** Devices for [platform] ("all" | "android" | "ios"); empty when the engine isn't up. */
    fun load(platform: String = "all"): List<DeviceItem> {
        val service = ApplicationManager.getApplication().getService(MTRDaemonService::class.java)
        val devices = service.listDevices(platform)?.getAsJsonArray("devices") ?: return emptyList()
        return devices.mapNotNull {
            val d = it.asJsonObject
            val id = d.get("id")?.asString ?: return@mapNotNull null
            DeviceItem(
                id,
                d.get("name")?.asString ?: "",
                d.get("platform")?.asString ?: "android",
                d.get("status")?.asString ?: "",
            )
        }
    }
}
