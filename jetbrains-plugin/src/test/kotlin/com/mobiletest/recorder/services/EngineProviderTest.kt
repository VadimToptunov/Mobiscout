package com.mobiletest.recorder.services

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

/**
 * The per-OS/arch binary selection decides which release asset the plugin downloads on
 * first run; picking the wrong one means the engine never starts. These pin the mapping.
 */
class EngineProviderTest {

    @Test
    fun `apple silicon maps to the macos arm64 binary`() {
        assertEquals("mobiscout-engine-macos-arm64", EngineProvider.assetName("Mac OS X", "aarch64"))
        assertEquals("mobiscout-engine-macos-arm64", EngineProvider.assetName("Darwin", "arm64"))
    }

    @Test
    fun `intel mac maps to the macos x64 binary`() {
        assertEquals("mobiscout-engine-macos-x64", EngineProvider.assetName("Mac OS X", "x86_64"))
    }

    @Test
    fun `windows maps to the exe asset`() {
        assertEquals("mobiscout-engine-windows-x64.exe", EngineProvider.assetName("Windows 11", "amd64"))
    }

    @Test
    fun `linux maps to the linux x64 binary`() {
        assertEquals("mobiscout-engine-linux-x64", EngineProvider.assetName("Linux", "amd64"))
    }

    @Test
    fun `an unsupported os has no asset`() {
        assertNull(EngineProvider.assetName("SunOS", "sparc"))
    }
}
