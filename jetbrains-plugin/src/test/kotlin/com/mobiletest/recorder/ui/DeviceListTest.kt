package com.mobiletest.recorder.ui

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * U4 regression: the id/platform now travel *with* the device item, so a selection is a field
 * access, never a parse of the label. The old code did `label.substringAfter("(")`, which for a
 * simulator named "iPad Pro (11-inch)" returned "11-inch" instead of the UDID and the session
 * never started.
 */
class DeviceListTest {

    @Test
    fun `a device name with parentheses keeps its id and platform (no label parsing)`() {
        val d = DeviceItem("ABCD-1234-UDID", "iPad Pro (11-inch)", "ios")
        assertEquals("ABCD-1234-UDID", d.id) // a field — the buggy parser returned "11-inch" here
        assertEquals("ios", d.platform)
        assertEquals("iPad Pro (11-inch) (ABCD-1234-UDID)", d.toString())
    }

    @Test
    fun `a nameless device falls back to its id as the label`() {
        assertEquals("emulator-5554", DeviceItem("emulator-5554", "", "android").toString())
    }
}
