package com.mobiletest.recorder.services

import java.io.File
import java.net.URI
import java.security.MessageDigest

/**
 * Resolves the command that starts the Observe engine's JSON-RPC daemon.
 *
 * Variant C — the user installs only the plugin, no Python. We prefer a
 * self-contained `observe-engine` binary, cached under the user's home and
 * downloaded from the matching GitHub release on first use. If that isn't
 * available (offline, no release yet, or an unsupported platform) we fall back to
 * an `observe` CLI on PATH, so a developer with the Python package still works.
 *
 * Note the two launch shapes differ: the frozen binary's entry point runs the
 * daemon directly (no arguments), whereas the CLI needs `daemon --stdio`.
 */
object EngineProvider {
    // The engine build to fetch. Must match a published release tag whose assets
    // are the per-platform binaries produced by .github/workflows/build-engine.yml.
    private const val ENGINE_VERSION = "v0.5.0"
    private const val RELEASE_BASE = "https://github.com/VadimToptunov/mobile_test_recorder/releases/download"
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
        findObserveOnPath()?.let { return listOf(it, "daemon", "--stdio") }
        throw IllegalStateException(
            "No engine available: couldn't download the standalone engine and no 'observe' CLI is on PATH.",
        )
    }

    private fun cacheDir(): File =
        File(System.getProperty("user.home"), ".mobile-observe/engine/$ENGINE_VERSION").apply { mkdirs() }

    /** The standalone binary, downloading it on first use; null if unavailable. */
    private fun ensureEngineBinary(): File? {
        val asset = assetName() ?: return null
        val target = File(cacheDir(), asset)
        if (target.exists() && target.length() > 0) return target
        return try {
            val conn = URI("$RELEASE_BASE/$ENGINE_VERSION/$asset").toURL().openConnection().apply {
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = READ_TIMEOUT_MS
            }
            conn.getInputStream().use { input -> target.outputStream().use { input.copyTo(it) } }
            // Never run an unverified downloaded executable: the release publishes a
            // <asset>.sha256; fail closed (delete + fall back) if it's missing or wrong.
            if (target.length() == 0L || !checksumMatches(target, asset)) {
                target.delete()
                return null
            }
            target.setExecutable(true)
            target
        } catch (e: Exception) {
            if (target.exists()) target.delete() // don't leave a half-written binary behind
            null
        }
    }

    /** Verify the binary against the published `<asset>.sha256`. */
    private fun checksumMatches(binary: File, asset: String): Boolean {
        return try {
            val published = URI("$RELEASE_BASE/$ENGINE_VERSION/$asset.sha256").toURL().openConnection().apply {
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = CONNECT_TIMEOUT_MS
            }.getInputStream().use { it.readBytes().decodeToString() }
            val expected = published.trim().split(Regex("\\s+")).firstOrNull()?.lowercase() ?: return false
            expected == sha256Hex(binary)
        } catch (e: Exception) {
            false
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

    /** Release asset name for the current OS/arch, or null if unsupported. */
    private fun assetName(): String? {
        val os = System.getProperty("os.name").lowercase()
        val arch = System.getProperty("os.arch").lowercase()
        return when {
            os.contains("mac") || os.contains("darwin") ->
                if (arch.contains("aarch64") || arch.contains("arm")) {
                    "observe-engine-macos-arm64"
                } else {
                    "observe-engine-macos-x64"
                }
            os.contains("win") -> "observe-engine-windows-x64.exe"
            os.contains("nux") || os.contains("nix") -> "observe-engine-linux-x64"
            else -> null
        }
    }

    /** An `observe` CLI on PATH (developer fallback), or null. */
    fun findObserveOnPath(): String? {
        val paths = System.getenv("PATH")?.split(File.pathSeparator).orEmpty()
        for (dir in paths) {
            for (name in listOf("observe", "observe.exe")) {
                val f = File(dir, name)
                if (f.exists() && f.canExecute()) return f.absolutePath
            }
        }
        val common = listOf(
            "/usr/local/bin/observe",
            System.getProperty("user.home") + "/.local/bin/observe",
        )
        return common.map { File(it) }.firstOrNull { it.exists() && it.canExecute() }?.absolutePath
    }
}
