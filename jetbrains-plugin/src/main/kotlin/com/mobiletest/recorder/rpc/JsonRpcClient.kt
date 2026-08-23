package com.mobiletest.recorder.rpc

import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.*
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
    private val writer = PrintWriter(BufferedWriter(OutputStreamWriter(process.outputStream)), true)
    private val reader = BufferedReader(InputStreamReader(process.inputStream))
    private val requestId = AtomicInteger(0)
    private val writeLock = Any()
    private val pending = ConcurrentHashMap<Int, CompletableFuture<JsonRpcResponse>>()

    @Volatile
    private var notificationCallback: ((JsonRpcNotification) -> Unit)? = null

    @Volatile
    private var running = true

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
            // The daemon went away: fail every in-flight call instead of hanging forever.
            val closed = JsonRpcException(-1, "daemon connection closed")
            pending.values.forEach { it.completeExceptionally(closed) }
            pending.clear()
        }
    }

    private fun dispatch(line: String) {
        val json = try {
            gson.fromJson(line, JsonObject::class.java)
        } catch (e: Exception) {
            return // ignore a malformed line rather than killing the reader
        } ?: return
        val idEl = json.get("id")
        if (idEl != null && !idEl.isJsonNull) {
            val response = gson.fromJson(line, JsonRpcResponse::class.java)
            response.id?.let { pending.remove(it)?.complete(response) }
        } else if (json.has("method")) {
            notificationCallback?.invoke(gson.fromJson(line, JsonRpcNotification::class.java))
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
        try {
            readerThread.interrupt()
            writer.close()
            reader.close()
            process.destroy()
            process.waitFor(5, TimeUnit.SECONDS)
            if (process.isAlive) {
                process.destroyForcibly()
            }
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
