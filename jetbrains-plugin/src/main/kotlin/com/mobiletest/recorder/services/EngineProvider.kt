package com.mobiletest.recorder.services

import java.io.File
import java.net.URI
import java.security.MessageDigest

/**
 * Resolves the command that starts the Mobiscout engine's JSON-RPC daemon.
 *
 * Variant C — the user installs only the plugin, no Python. We prefer a
 * self-contained `mobiscout-engine` binary, cached under the user's home and
 * downloaded from the matching GitHub release on first use. If that isn't
 * available (offline, no release yet, or an unsupported platform) we fall back to
 * an `mobiscout` CLI on PATH, so a developer with the Python package still works.
 *
 * Note the two launch shapes differ: the frozen binary's entry point runs the
 * daemon directly (no arguments), whereas the CLI needs `daemon --stdio`.
 */
object EngineProvider {
    // The engine build to fetch. Must match a published release tag whose assets
    // are the per-platform binaries produced by .github/workflows/build-engine.yml,
    // and MUST stay aligned with framework.__version__ (a release ships the plugin and
    // the engine together). EngineProviderTest asserts that alignment so a release can't
    // ship a plugin that downloads a stale engine. `internal` so that test can read it.
    internal const val ENGINE_VERSION = "v0.12.2"
    private const val RELEASE_BASE = "https://github.com/VadimToptunov/Mobiscout/releases/download"
    private const val CONNECT_TIMEOUT_MS = 15_000
    private const val READ_TIMEOUT_MS = 120_000

    /**
     * The full command (executable + args) to launch the daemon over stdio.
     *
     * @throws IllegalStateException if neither a standalone engine nor a PATH CLI
     *   is available.
     */
    fun resolveDaemonCommand(): List<String> {
        ensureEngineBinary()?.let { return listOf(it.absolutePath) } // frozen entry runs the daemon directly
        findMobiscoutOnPath()?.let { return listOf(it, "daemon", "--stdio") }
        throw IllegalStateException(
            "No engine available: couldn't download the standalone engine and no 'mobiscout' CLI is on PATH.",
        )
    }

    private fun cacheDir(): File =
        File(System.getProperty("user.home"), ".mobiscout/engine/$ENGINE_VERSION").apply { mkdirs() }

    /** The standalone binary, downloading it on first use; null if unavailable. */
    private fun ensureEngineBinary(): File? {
        val asset = assetName() ?: return null
        val target = File(cacheDir(), asset)
        val localDigest = File(cacheDir(), "$asset.sha256")

        // Cache hit: only trust a binary whose bytes STILL match the digest we verified at
        // download time. A truncated (interrupted copy) or tampered file is re-fetched
        // rather than executed on size alone.
        if (target.exists() && localDigest.exists()) {
            val expected = runCatching { localDigest.readText().trim().lowercase() }.getOrNull()
            if (expected != null && expected == sha256Hex(target)) {
                target.setExecutable(true)
                return target
            }
            target.delete()
            localDigest.delete()
        }

        // Download to a .part file, verify, then atomically publish — so a crash mid-copy
        // can never leave a half-written binary that a later launch would trust and run.
        val part = File(cacheDir(), "$asset.part")
        return try {
            val conn = URI("$RELEASE_BASE/$ENGINE_VERSION/$asset").toURL().openConnection().apply {
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = READ_TIMEOUT_MS
            }
            conn.getInputStream().use { input -> part.outputStream().use { input.copyTo(it) } }
            val digest = sha256Hex(part)
            if (part.length() == 0L || digest != publishedChecksum(asset)) {
                part.delete()
                return null
            }
            if (!part.renameTo(target)) {
                part.copyTo(target, overwrite = true)
                part.delete()
            }
            localDigest.writeText(digest) // record for the cache-hit re-verify above
            target.setExecutable(true)
            target
        } catch (e: Exception) {
            part.delete() // don't leave a half-written binary behind
            null
        }
    }

    /** The published `<asset>.sha256` digest, or null if unavailable/malformed. */
    private fun publishedChecksum(asset: String): String? {
        return try {
            val published = URI("$RELEASE_BASE/$ENGINE_VERSION/$asset.sha256").toURL().openConnection().apply {
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = CONNECT_TIMEOUT_MS
            }.getInputStream().use { it.readBytes().decodeToString() }
            published.trim().split(Regex("\\s+")).firstOrNull()?.lowercase()
        } catch (e: Exception) {
            null
        }
    }

    private fun sha256Hex(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { stream ->
            val buffer = ByteArray(8192)
            var read = stream.read(buffer)
            while (read > 0) {
                md.update(buffer, 0, read)
                read = stream.read(buffer)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    /** Release asset name for the given OS/arch (defaults to the running JVM's), or null
     *  if unsupported. Parameters are injectable so the platform mapping is unit-testable. */
    internal fun assetName(
        os: String = System.getProperty("os.name"),
        arch: String = System.getProperty("os.arch"),
    ): String? {
        val o = os.lowercase()
        val a = arch.lowercase()
        return when {
            o.contains("mac") || o.contains("darwin") ->
                if (a.contains("aarch64") || a.contains("arm")) {
                    "mobiscout-engine-macos-arm64"
                } else {
                    "mobiscout-engine-macos-x64"
                }
            o.contains("win") -> "mobiscout-engine-windows-x64.exe"
            o.contains("nux") || o.contains("nix") -> "mobiscout-engine-linux-x64"
            else -> null
        }
    }

    /** An `mobiscout` CLI on PATH (developer fallback), or null. */
    fun findMobiscoutOnPath(): String? {
        val paths = System.getenv("PATH")?.split(File.pathSeparator).orEmpty()
        for (dir in paths) {
            for (name in listOf("mobiscout", "mobiscout.exe")) {
                val f = File(dir, name)
                if (f.exists() && f.canExecute()) return f.absolutePath
            }
        }
        val common = listOf(
            "/usr/local/bin/mobiscout",
            System.getProperty("user.home") + "/.local/bin/mobiscout",
        )
        return common.map { File(it) }.firstOrNull { it.exists() && it.canExecute() }?.absolutePath
    }
}
