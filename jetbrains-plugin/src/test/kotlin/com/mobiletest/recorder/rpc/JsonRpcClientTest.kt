package com.mobiletest.recorder.rpc

import com.google.gson.Gson
import com.google.gson.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.util.concurrent.TimeUnit

/**
 * A fake [Process] whose stdout serves canned response line(s) and whose stdin captures
 * everything the client writes — so the JSON-RPC framing can be asserted without a real
 * daemon. `getOutputStream()` is the process's stdin (where the client writes requests);
 * `getInputStream()` is the process's stdout (where the client reads responses).
 */
private class FakeProcess(responseLines: String) : Process() {
    val stdin = ByteArrayOutputStream()
    private val stdout = ByteArrayInputStream(responseLines.toByteArray())

    override fun getOutputStream(): OutputStream = stdin
    override fun getInputStream(): InputStream = stdout
    override fun getErrorStream(): InputStream = ByteArrayInputStream(ByteArray(0))
    override fun waitFor(): Int = 0
    override fun waitFor(timeout: Long, unit: TimeUnit): Boolean = true
    override fun exitValue(): Int = 0
    override fun destroy() {}
    override fun isAlive(): Boolean = false
}

class JsonRpcClientTest {
    private val gson = Gson()

    private fun sentRequests(proc: FakeProcess): List<JsonObject> =
        proc.stdin.toString().trim().lines().filter { it.isNotBlank() }.map {
            gson.fromJson(it, JsonObject::class.java)
        }

    @Test
    fun `call writes a JSON-RPC 2_0 request and parses the result`() {
        val proc = FakeProcess("""{"jsonrpc":"2.0","id":1,"result":{"ok":true}}""" + "\n")
        val client = JsonRpcClient(proc)

        val resp = client.call("device/list", mapOf("platform" to "android"))

        val sent = sentRequests(proc).single()
        assertEquals("2.0", sent.get("jsonrpc").asString)
        assertEquals("device/list", sent.get("method").asString)
        assertEquals(1, sent.get("id").asInt)
        assertEquals("android", sent.getAsJsonObject("params").get("platform").asString)

        assertFalse(resp.isError())
        assertTrue(resp.getResultOrThrow().get("ok").asBoolean)
    }

    @Test
    fun `call increments the request id on each call`() {
        val proc = FakeProcess(
            """{"jsonrpc":"2.0","id":1,"result":{}}""" + "\n" +
                """{"jsonrpc":"2.0","id":2,"result":{}}""" + "\n",
        )
        val client = JsonRpcClient(proc)

        client.call("a")
        client.call("b")

        assertEquals(listOf(1, 2), sentRequests(proc).map { it.get("id").asInt })
    }

    @Test
    fun `call throws when the daemon sends no response`() {
        val client = JsonRpcClient(FakeProcess("")) // empty stdout -> readLine() == null
        val ex = assertThrows(IOException::class.java) { client.call("x") }
        assertTrue(ex.message!!.contains("No response"))
    }

    @Test
    fun `getResultOrThrow raises JsonRpcException on an error response`() {
        val client = JsonRpcClient(
            FakeProcess("""{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"boom"}}""" + "\n"),
        )
        val resp = client.call("x")
        assertTrue(resp.isError())
        val ex = assertThrows(JsonRpcException::class.java) { resp.getResultOrThrow() }
        assertEquals(-32000, ex.code)
    }

    @Test
    fun `notify writes a request with a method but no id`() {
        val proc = FakeProcess("")
        val client = JsonRpcClient(proc)

        client.notify("logs/subscribe", mapOf("k" to "v"))

        val sent = sentRequests(proc).single()
        assertEquals("logs/subscribe", sent.get("method").asString)
        assertEquals("2.0", sent.get("jsonrpc").asString)
        assertFalse(sent.has("id"))
    }
}
