package com.mobiletest.recorder.ui

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.io.File

/**
 * The default output dir ("mobile-tests") is relative; the GUI-launched engine's working
 * directory is not the project, so a relative path lands "nowhere" (U1). These pin the
 * resolution: a relative path is anchored to the project root; anything already absolute,
 * or given no project root, is left alone.
 */
class GenerateKitDialogTest {

    @Test
    fun `a relative output is anchored to the project root`() {
        val resolved = GenerateKitDialog.resolveOutputPath("mobile-tests", "/home/u/proj")
        assertEquals(File("/home/u/proj", "mobile-tests").path, resolved)
        assertEquals(File(resolved).isAbsolute, true)
    }

    @Test
    fun `an absolute output is left unchanged`() {
        val abs = File("/tmp/kits").path
        assertEquals(abs, GenerateKitDialog.resolveOutputPath(abs, "/home/u/proj"))
    }

    @Test
    fun `no project root leaves the path as given`() {
        assertEquals("mobile-tests", GenerateKitDialog.resolveOutputPath("mobile-tests", null))
    }

    // --- gate-passing waypoints ------------------------------------------------------
    //
    // A banking app puts a one-time code behind the password, so a crawl that can only pass
    // the password stops one screen short of the app. Verified against a live app: with both
    // gates the crawler types the credentials, then real time-based codes, and tags what it
    // finds behind them as gated. These pin the shape the engine expects.

    @Test
    fun `no username means no gate to pass`() {
        assertEquals(emptyList<Map<String, Any>>(), GenerateKitDialog.buildGates("", "pw", "Log in", "", ""))
    }

    @Test
    fun `a password gate is one waypoint`() {
        val gates = GenerateKitDialog.buildGates("demo", "pw", "Log in", "", "")
        assertEquals(1, gates.size)
        assertEquals("fill", gates[0]["action"])
        val data = gates[0]["data"] as Map<*, *>
        assertEquals(mapOf("user" to "demo", "password" to "pw"), data["fields"])
        assertEquals("Log in", data["submit"])
    }

    @Test
    fun `a one-time code is a second gate, after the password`() {
        val gates = GenerateKitDialog.buildGates("demo", "pw", "Log in", "JBSWY3DPEHPK3PXP", "Verify")
        assertEquals(listOf("fill", "totp"), gates.map { it["action"] })  // order is the passing order
        val otp = gates[1]["data"] as Map<*, *>
        assertEquals("JBSWY3DPEHPK3PXP", otp["secret"])
        assertEquals("Verify", otp["submit"])
    }

    @Test
    fun `the submit labels fall back to sensible defaults`() {
        val gates = GenerateKitDialog.buildGates("demo", "pw", "", "SECRET", "")
        assertEquals("log in", (gates[0]["data"] as Map<*, *>)["submit"])
        assertEquals("verify", (gates[1]["data"] as Map<*, *>)["submit"])
    }

    @Test
    fun `one suite for Android and iOS refuses a framework that cannot run on both`() {
        // Espresso is Android instrumentation and Maestro flows are per platform: neither can be
        // ONE suite for both, so the dialog must say so before a crawl is spent on it.
        assertEquals(true, GenerateKitDialog.CROSS_PLATFORM_UNSUPPORTED.containsKey("kotlin_espresso"))
        assertEquals(true, GenerateKitDialog.CROSS_PLATFORM_UNSUPPORTED.containsKey("maestro"))
        for (target in listOf("python_pytest", "java_testng", "kotlin_appium", "js_webdriverio", "csharp_nunit")) {
            assertEquals(false, GenerateKitDialog.CROSS_PLATFORM_UNSUPPORTED.containsKey(target), target)
        }
    }
}
