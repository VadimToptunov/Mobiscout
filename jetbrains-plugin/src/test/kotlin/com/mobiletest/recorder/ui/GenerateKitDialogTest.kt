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
}
