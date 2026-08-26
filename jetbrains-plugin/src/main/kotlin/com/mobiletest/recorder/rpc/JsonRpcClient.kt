package com.mobiletest.recorder.rpc

import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.*
import java.nio.charset.StandardCharsets
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.concurrent.atomic.AtomicInteger

/**
 * JSON-RPC 2.0 client for mobiscout daemon communication.
 *
 * A **single** reader thread owns the input stream and dispatches each line by id:
 * responses complete the matching request's future, notifications go to the callback.
 * Callers of [call] never touch the stream — they await their own future — so concurrent
 * requests and a streaming notification can't steal each other's lines (the previous
 * design had [call] and the notification listener both `readLine()`-ing the same stream,
 * which dropped responses and hung calls). Writes are serialized so two threads can't
 * interleave a frame.
 */
class JsonRpcClient(
    private val process: Process
) {
    private val gson = Gson()
    // Both stream charsets are pinned to UTF-8 instead of the JVM default. Requests routinely
    // carry non-ASCII — the output dir is the project path, so a Windows profile directory
    // with a Cyrillic/umlaut name lands in every kit/generate, as do login waypoints — and a
    // charset the daemon doesn't share turns those into mojibake or kills its read loop.
    private val writer =
        PrintWriter(BufferedWriter(OutputStreamWriter(process.outputStream, StandardCharsets.UTF_8)), true)
    private val reader = BufferedReader(InputStreamReader(process.inputStream, StandardCharsets.UTF_8))
    private val requestId = AtomicInteger(0)
    private val writeLock = Any()
    private val pending = ConcurrentHashMap<Int, CompletableFuture<JsonRpcResponse>>()

    @Volatile
    private var notificationCallback: ((JsonRpcNotification) -> Unit)? = null

    @Volatile
    private var running = true

    // Set once the reader thread has exited (daemon stream closed/errored). After this no
    // future will ever be completed by the reader, so a call() registered now must fail fast
    // instead of blocking for the whole timeout backstop.
    @Volatile
    private var closed = false

    private val readerThread = Thread({ readLoop() }, "mobiscout-rpc-reader").apply {
        isDaemon = true
        start()
    }

    private fun readLoop() {
        try {
            while (running) {
                val line = reader.readLine() ?: break
                dispatch(line)
            }
        } catch (e: IOException) {
            // stream error — handled by the finally (all pending calls fail)
        } finally {
            // The daemon went away: mark the connection closed and fail every in-flight call
            // instead of hanging forever. `closed` is set FIRST so a call() racing in behind us
            // sees it and fails fast rather than parking on a future no one will complete.
            closed = true
            val error = JsonRpcException(-1, "daemon connection closed")
            pending.values.forEach { it.completeExceptionally(error) }
            pending.clear()
        }
    }

    private fun dispatch(line: String) {
        val json = try {
            gson.fromJson(line, JsonObject::class.java)
        } catch (e: Exception) {
            return // ignore a malformed line rather than killing the reader
        } ?: return
        // Everything below runs on the one reader thread. A JsonSyntaxException from a JSON
        // line whose shape isn't ours, or a throw from a notification listener, would escape
        // readLoop's IOException-only catch and close the connection for good — while the
        // daemon process is still alive, so nothing detects it and the UI keeps saying
        // "Running" over an RPC that fails every call from then on.
        try {
            val idEl = json.get("id")
            if (idEl != null && !idEl.isJsonNull) {
                val response = gson.fromJson(line, JsonRpcResponse::class.java)
                response.id?.let { pending.remove(it)?.complete(response) }
            } else if (json.has("method")) {
                notificationCallback?.invoke(gson.fromJson(line, JsonRpcNotification::class.java))
            }
        } catch (e: Exception) {
            // one bad line (or one bad listener) must not take the connection down
        }
    }

    /**
     * Send a JSON-RPC request and await its response (correlated by id). Fails with an
     * IOException if the daemon closes the stream or does not answer within [timeoutMs]
     * (a generous backstop for a hung-but-alive daemon; a dead one fails immediately when
     * its stream closes).
     */
    fun call(method: String, params: Map<String, Any> = emptyMap(), timeoutMs: Long = DEFAULT_TIMEOUT_MS): JsonRpcResponse {
        val id = requestId.incrementAndGet()
        val future = CompletableFuture<JsonRpcResponse>()
        pending[id] = future
        // If the reader already exited (daemon dead), nobody will ever complete this future —
        // fail immediately instead of parking on it for the full timeout. Checked AFTER
        // registering so we can't slip in between the reader's drain and its `closed = true`.
        if (closed) {
            pending.remove(id)
            throw IOException("Daemon connection is closed; cannot call '$method'.")
        }
        val request = JsonRpcRequest(jsonrpc = "2.0", id = id, method = method, params = params)
        synchronized(writeLock) { writer.println(gson.toJson(request)) }
        return try {
            future.get(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (e: TimeoutException) {
            pending.remove(id)
            throw IOException("No response from daemon for '$method' within ${timeoutMs}ms")
        } catch (e: java.util.concurrent.ExecutionException) {
            throw (e.cause as? Exception) ?: IOException("RPC '$method' failed: ${e.message}")
        }
    }

    /**
     * Send a notification (no response expected).
     */
    fun notify(method: String, params: Map<String, Any> = emptyMap()) {
        val notification = mapOf("jsonrpc" to "2.0", "method" to method, "params" to params)
        synchronized(writeLock) { writer.println(gson.toJson(notification)) }
    }

    /**
     * Register the callback for server-initiated notifications. The single reader thread
     * is already running (started in the constructor); this only sets where notifications
     * are delivered.
     */
    fun startListening(callback: (JsonRpcNotification) -> Unit) {
        notificationCallback = callback
    }

    /**
     * Close the connection.
     */
    fun close() {
        running = false
        readerThread.interrupt()
        // Order matters. Closing stdin first lets a daemon that is READING shut down cleanly
        // on EOF. A daemon busy inside a long call (a crawl) never gets to that read, so the
        // process must be killed next: its exit is the only thing that closes its stdout and
        // releases the reader thread parked in readLine() — and BufferedReader.close() waits
        // on that same lock, so closing the reader before the kill blocked close() for the
        // rest of the crawl, and with it stop(), the Stop action and IDE shutdown. Each step
        // is guarded on its own so a failure in one can't skip the kill and orphan the engine.
        quietly { writer.close() }
        quietly { process.destroy() }
        quietly { if (!process.waitFor(5, TimeUnit.SECONDS)) process.destroyForcibly() }
        quietly { reader.close() }
    }

    private fun quietly(action: () -> Unit) {
        try {
            action()
        } catch (e: Exception) {
            // best-effort teardown
        }
    }

    companion object {
        // Backstop for a hung-but-alive daemon; long enough not to abort a real crawl.
        private const val DEFAULT_TIMEOUT_MS = 600_000L
    }
}

data class JsonRpcRequest(
    val jsonrpc: String,
    val id: Int,
    val method: String,
    val params: Map<String, Any>
)

data class JsonRpcResponse(
    val jsonrpc: String,
    val id: Int?,
    val result: JsonObject?,
    val error: JsonRpcError?
) {
    fun isError(): Boolean = error != null
    
    fun getResultOrThrow(): JsonObject {
        if (error != null) {
            throw JsonRpcException(error.code, error.message)
        }
        return result ?: throw JsonRpcException(-1, "No result in response")
    }
}

data class JsonRpcError(
    val code: Int,
    val message: String,
    val data: Any? = null
)

data class JsonRpcNotification(
    val jsonrpc: String,
    val method: String,
    val params: JsonObject
)

class JsonRpcException(
    val code: Int,
    message: String
) : Exception("JSON-RPC Error ($code): $message")
