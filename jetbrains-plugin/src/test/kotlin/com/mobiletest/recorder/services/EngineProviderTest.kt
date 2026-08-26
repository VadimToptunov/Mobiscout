package com.mobiletest.recorder.services

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.io.IOException

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

    // ---- download → verify → publish -------------------------------------------------
    //
    // This is the plugin's supply-chain gate: the engine binary is executed only after its
    // SHA-256 matches the digest published beside the release asset. It had no test at all,
    // so deleting the check would have shipped a green build. These drive ensureEngineBinary
    // against an in-memory "release" (the fetch + published-digest parameters) and a temp
    // cache dir, so nothing here touches the network or the user's ~/.mobiscout.

    /**
     * Anchors the digest itself to an EXTERNAL published value: SHA-256("abc") as printed in
     * NIST FIPS 180-4's test vectors. Recomputing it here with MessageDigest would only prove
     * the code agrees with itself.
     */
    @Test
    fun `sha256Hex matches the published SHA-256 test vector`(@TempDir dir: File) {
        val file = File(dir, "vector.bin").apply { writeBytes(PAYLOAD) }
        assertEquals(PAYLOAD_SHA256, EngineProvider.sha256Hex(file))
    }

    @Test
    fun `a download whose digest matches the published one is published and executable`(@TempDir dir: File) {
        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { PAYLOAD.inputStream() },
            publishedDigest = { PAYLOAD_SHA256 },
        )
        assertNotNull(binary, "a verified download must be published")
        assertEquals(File(dir, ASSET), binary)
        assertEquals(PAYLOAD.decodeToString(), binary!!.readText())
        assertTrue(binary.canExecute(), "the published binary must be executable")
        // Recorded so the cache-hit path can re-verify the bytes on the next launch.
        assertEquals(PAYLOAD_SHA256, File(dir, "$ASSET.sha256").readText().trim())
    }

    @Test
    fun `a download that does not match the published digest is rejected`(@TempDir dir: File) {
        val tampered = "abd".toByteArray() // one byte off the payload the digest was published for
        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { tampered.inputStream() },
            publishedDigest = { PAYLOAD_SHA256 },
        )
        assertNull(binary, "bytes that fail the digest must never be published")
        assertFalse(File(dir, ASSET).exists(), "no binary may be left at the target path")
        assertEquals(emptyList<String>(), dir.list()!!.toList(), "no scratch file may be left behind")
    }

    @Test
    fun `an empty download is rejected even when the published digest matches`(@TempDir dir: File) {
        // A truncated-to-nothing transfer hashes to the published digest of an empty file if the
        // release itself is broken; the length guard is what stops a 0-byte "engine" being run.
        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { ByteArray(0).inputStream() },
            publishedDigest = { EMPTY_SHA256 },
        )
        assertNull(binary)
        assertFalse(File(dir, ASSET).exists())
    }

    @Test
    fun `an unavailable published digest rejects the download`(@TempDir dir: File) {
        // The .sha256 fetch failed (offline, 404, malformed) — unverifiable bytes are not run.
        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { PAYLOAD.inputStream() },
            publishedDigest = { null },
        )
        assertNull(binary)
        assertFalse(File(dir, ASSET).exists())
    }

    @Test
    fun `a cached binary that no longer matches its recorded digest is re-fetched`(@TempDir dir: File) {
        File(dir, ASSET).writeBytes("truncated".toByteArray())
        File(dir, "$ASSET.sha256").writeText(PAYLOAD_SHA256)

        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { PAYLOAD.inputStream() },
            publishedDigest = { PAYLOAD_SHA256 },
        )
        assertNotNull(binary)
        assertEquals(PAYLOAD.decodeToString(), binary!!.readText(), "the tampered cache must be replaced")
    }

    @Test
    fun `a cached binary matching its recorded digest is used without downloading`(@TempDir dir: File) {
        File(dir, ASSET).writeBytes(PAYLOAD)
        File(dir, "$ASSET.sha256").writeText(PAYLOAD_SHA256)

        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { throw AssertionError("a verified cache hit must not re-download") },
            publishedDigest = { throw AssertionError("a verified cache hit must not re-download") },
        )
        assertEquals(File(dir, ASSET), binary)
    }

    @Test
    fun `a failed download leaves no scratch file behind`(@TempDir dir: File) {
        val binary = EngineProvider.ensureEngineBinary(
            asset = ASSET,
            dir = dir,
            fetch = { throw IOException("connection reset") },
            publishedDigest = { PAYLOAD_SHA256 },
        )
        assertNull(binary)
        assertEquals(emptyList<String>(), dir.list()!!.toList())
    }

    @Test
    fun `an unsupported platform never downloads anything`(@TempDir dir: File) {
        val binary = EngineProvider.ensureEngineBinary(
            asset = null,
            dir = dir,
            fetch = { throw AssertionError("must not download without a known asset") },
            publishedDigest = { throw AssertionError("must not download without a known asset") },
        )
        assertNull(binary)
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

    private companion object {
        private const val ASSET = "mobiscout-engine-linux-x64"

        /** Payload and its SHA-256 as published in NIST FIPS 180-4 (the "abc" test vector). */
        private val PAYLOAD = "abc".toByteArray()
        private const val PAYLOAD_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

        /** The published SHA-256 of the empty message (NIST FIPS 180-4). */
        private const val EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
}
