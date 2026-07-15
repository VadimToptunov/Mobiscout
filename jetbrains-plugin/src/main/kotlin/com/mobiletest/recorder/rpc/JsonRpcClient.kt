package com.mobiletest.recorder.rpc

import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.*
import java.util.concurrent.atomic.AtomicInteger

/**
 * JSON-RPC 2.0 client for mobiscout daemon communication.
 */
class JsonRpcClient(
    private val process: Process
) {
    private val gson = Gson()
    private val writer = PrintWriter(BufferedWriter(OutputStreamWriter(process.outputStream)), true)
    private val reader = BufferedReader(InputStreamReader(process.inputStream))
    private val requestId = AtomicInteger(0)
    
    @Volatile
    private var running = true
    
    /**
     * Send JSON-RPC request and get response.
     */
    fun call(method: String, params: Map<String, Any> = emptyMap()): JsonRpcResponse {
        val id = requestId.incrementAndGet()
        val request = JsonRpcRequest(
            jsonrpc = "2.0",
            id = id,
            method = method,
            params = params
        )
        
        val requestJson = gson.toJson(request)
        writer.println(requestJson)
        
        // Read response
        val responseLine = reader.readLine() ?: throw IOException("No response from daemon")
        return gson.fromJson(responseLine, JsonRpcResponse::class.java)
    }
    
    /**
     * Send notification (no response expected).
     */
    fun notify(method: String, params: Map<String, Any> = emptyMap()) {
        val notification = mapOf(
            "jsonrpc" to "2.0",
            "method" to method,
            "params" to params
        )
        val notificationJson = gson.toJson(notification)
        writer.println(notificationJson)
    }
    
    /**
     * Start listening for notifications from server.
     */
    fun startListening(callback: (JsonRpcNotification) -> Unit) {
        Thread {
            try {
                while (running) {
                    val line = reader.readLine() ?: break
                    val json = gson.fromJson(line, JsonObject::class.java)
                    
                    // Check if this is a notification (has method but no id)
                    if (json.has("method") && !json.has("id")) {
                        val notification = gson.fromJson(line, JsonRpcNotification::class.java)
                        callback(notification)
                    }
                }
            } catch (e: IOException) {
                if (running) {
                    println("Error reading from daemon: ${e.message}")
                }
            }
        }.start()
    }
    
    /**
     * Close the connection.
     */
    fun close() {
        running = false
        try {
            writer.close()
            reader.close()
            process.destroy()
            process.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)
            if (process.isAlive) {
                process.destroyForcibly()
            }
        } catch (e: Exception) {
            println("Error closing client: ${e.message}")
        }
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
