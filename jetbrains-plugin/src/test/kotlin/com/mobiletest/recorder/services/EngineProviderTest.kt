package com.mobiletest.recorder.services

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test
import java.io.File

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

    /**
     * Release gate: the engine version the plugin downloads MUST equal the framework
     * version ("v" + framework.__version__). A release ships the plugin and engine as a
     * pair; a drift here (as in 0.11.0, where the pin lagged at v0.10.0) means plugin users
     * silently get a stale engine — no new features. This fails the build when they diverge.
     */
    @Test
    fun `engine version pin is aligned with the framework version`() {
        val initPy = findUpwards("framework/__init__.py")
        assertNotNull(initPy, "framework/__init__.py not found from ${File(".").absolutePath}")
        val version = Regex("""__version__\s*=\s*["']([^"']+)["']""")
            .find(initPy!!.readText())?.groupValues?.get(1)
        assertNotNull(version, "could not parse __version__ from ${initPy.path}")
        assertEquals(
            "v$version",
            EngineProvider.ENGINE_VERSION,
            "EngineProvider.ENGINE_VERSION must equal \"v\" + framework.__version__ — bump it when releasing",
        )
    }

    private fun findUpwards(relative: String): File? {
        var dir: File? = File(".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, relative)
            if (candidate.exists()) return candidate
            dir = dir.parentFile
        }
        return null
    }
}
