package com.mobiletest.recorder.rpc

import com.google.gson.Gson
import com.google.gson.JsonObject
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.io.BufferedReader
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.InputStreamReader
import java.io.OutputStream
import java.io.PipedInputStream
import java.io.PipedOutputStream
import java.io.PrintWriter
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * A fake JSON-RPC daemon over pipes: it reads request lines the client writes and, on its
 * own thread, replies — so responses arrive AFTER their request (as a real daemon does),
 * which is what lets id-correlation be tested. This models a [Process] for the client.
 */
private class FakeDaemon(
    private val respond: (JsonObject, PrintWriter) -> Unit,
) : Process() {
    private val gson = Gson()
    private val clientToDaemon = PipedInputStream(1 shl 16)
    private val daemonToClient = PipedOutputStream()
    private val clientStdin = PipedOutputStream(clientToDaemon) // client writes requests here
    private val clientStdout = PipedInputStream(daemonToClient, 1 shl 16) // client reads responses here
    private val toClient = PrintWriter(daemonToClient, true)
    @Volatile
    var running = true
    val requests = mutableListOf<JsonObject>()

    private val thread = Thread {
        val reader = BufferedReader(InputStreamReader(clientToDaemon))
        try {
            while (running) {
                val line = reader.readLine() ?: break
                val req = gson.fromJson(line, JsonObject::class.java)
                synchronized(requests) { requests.add(req) }
                respond(req, toClient)
            }
        } catch (e: Exception) {
            // pipe closed
        }
    }.apply { isDaemon = true; start() }

    fun pushNotification(json: String) = toClient.println(json)

    fun closeStream() {
        running = false
        toClient.close()
    }

    override fun getOutputStream(): OutputStream = clientStdin
    override fun getInputStream(): InputStream = clientStdout
    override fun getErrorStream(): InputStream = PipedInputStream()
    override fun waitFor(): Int = 0
    override fun waitFor(timeout: Long, unit: TimeUnit): Boolean = true
    override fun exitValue(): Int = 0
    override fun destroy() {
        running = false
    }
    override fun isAlive(): Boolean = running
}

/**
 * A daemon that is alive but silent — the state the engine is in for the whole of a crawl,
 * where it neither reads its stdin nor writes to stdout until the call returns. Its stdout
 * closes only when the process is destroyed, as a real one's does when it exits.
 */
private class SilentDaemon : Process() {
    private val exited = CountDownLatch(1)
    private val clientStdin = ByteArrayOutputStream()
    // The read blocks until the process exits and, like a real pipe read, does NOT observe
    // an interrupt — which is exactly why interrupting the reader thread can't free it and
    // the process has to be killed instead.
    private val clientStdout = object : InputStream() {
        override fun read(): Int {
            while (true) {
                try {
                    exited.await()
                    return -1
                } catch (e: InterruptedException) {
                    // a blocked native read doesn't unwind on interrupt; neither does this
                }
            }
        }
    }

    override fun getOutputStream(): OutputStream = clientStdin
    override fun getInputStream(): InputStream = clientStdout
    override fun getErrorStream(): InputStream = ByteArrayInputStream(ByteArray(0))
    override fun waitFor(): Int = 0
    override fun waitFor(timeout: Long, unit: TimeUnit): Boolean = exited.count == 0L
    override fun exitValue(): Int = 0
    override fun destroy() = exited.countDown()
    override fun isAlive(): Boolean = exited.count > 0L
}

class JsonRpcClientTest {
    private val gson = Gson()
    private var client: JsonRpcClient? = null

    @AfterEach
    fun tearDown() {
        client?.close()
    }

    /** Reply to every request by echoing its method back in the result, id preserved. */
    private fun echoingDaemon(): FakeDaemon = FakeDaemon { req, out ->
        val id = req.get("id").asInt
        val method = req.get("method").asString
        out.println("""{"jsonrpc":"2.0","id":$id,"result":{"method":"$method"}}""")
    }

    @Test
    fun `call sends a JSON-RPC 2_0 request and returns the id-matched result`() {
        val daemon = echoingDaemon()
        val c = JsonRpcClient(daemon).also { client = it }

        val resp = c.call("device/list", mapOf("platform" to "android"))

        assertFalse(resp.isError())
        assertEquals("device/list", resp.getResultOrThrow().get("method").asString)
        val sent = synchronized(daemon.requests) { daemon.requests.single() }
        assertEquals("2.0", sent.get("jsonrpc").asString)
        assertEquals("device/list", sent.get("method").asString)
        assertEquals("android", sent.getAsJsonObject("params").get("platform").asString)
    }

    @Test
    fun `concurrent calls each receive their own response (no stolen lines)`() {
        // Many client threads call at once; the single daemon thread echoes each request's
        // method in its id-matched result. Every call must get the result for ITS method —
        // the core of id-correlation (the old two-reader client stole lines here).
        val daemon = echoingDaemon()
        val c = JsonRpcClient(daemon).also { client = it }

        val n = 20
        val start = CountDownLatch(1)
        val done = CountDownLatch(n)
        val mismatches = AtomicInteger(0)
        for (i in 0 until n) {
            Thread {
                start.await()
                val method = "m$i"
                val got = c.call(method).getResultOrThrow().get("method").asString
                if (got != method) mismatches.incrementAndGet()
                done.countDown()
            }.start()
        }
        start.countDown()
        assertTrue(done.await(30, TimeUnit.SECONDS), "calls did not all complete")
        assertEquals(0, mismatches.get(), "a call received another call's response")
    }

    @Test
    fun `a notification streamed mid-flight goes to the listener, not to a call`() {
        val delivered = CountDownLatch(1)
        val daemon = FakeDaemon { req, out ->
            val id = req.get("id").asInt
            out.println("""{"jsonrpc":"2.0","id":$id,"result":{"method":"ok"}}""")
        }
        val c = JsonRpcClient(daemon).also { client = it }
        c.startListening { note -> if (note.method == "logs/message") delivered.countDown() }

        daemon.pushNotification("""{"jsonrpc":"2.0","method":"logs/message","params":{"line":"x"}}""")
        // the call still gets its own result, unpolluted by the notification
        assertEquals("ok", c.call("kit/generate").getResultOrThrow().get("method").asString)
        assertTrue(delivered.await(5, TimeUnit.SECONDS), "notification not delivered to listener")
    }

    @Test
    fun `call fails when the daemon closes the stream without responding`() {
        val daemon = FakeDaemon { _, _ -> } // never replies
        val c = JsonRpcClient(daemon).also { client = it }
        Thread { Thread.sleep(50); daemon.closeStream() }.start()
        assertThrows(Exception::class.java) { c.call("x", emptyMap(), timeoutMs = 5_000) }
    }

    @Test
    fun `a call made after the daemon has closed fails fast, not after the full timeout`() {
        val daemon = FakeDaemon { _, _ -> } // never replies
        val c = JsonRpcClient(daemon).also { client = it }
        daemon.closeStream()
        // Let the reader observe EOF and mark the connection closed.
        val deadline = System.currentTimeMillis() + 2_000
        Thread.sleep(200)
        while (System.currentTimeMillis() < deadline && daemon.isAlive) Thread.sleep(20)

        val start = System.currentTimeMillis()
        // Without the `closed` fast-path this future is never completed and blocks the whole
        // 10-minute backstop; with it the call fails immediately.
        assertThrows(Exception::class.java) { c.call("x", emptyMap(), timeoutMs = 600_000) }
        val elapsed = System.currentTimeMillis() - start
        assertTrue(elapsed < 5_000, "call blocked ${elapsed}ms after close — it should fail fast")
    }

    @Test
    fun `getResultOrThrow raises JsonRpcException on an error response`() {
        val daemon = FakeDaemon { req, out ->
            val id = req.get("id").asInt
            out.println("""{"jsonrpc":"2.0","id":$id,"error":{"code":-32000,"message":"boom"}}""")
        }
        val c = JsonRpcClient(daemon).also { client = it }
        val resp = c.call("x")
        assertTrue(resp.isError())
        val ex = assertThrows(JsonRpcException::class.java) { resp.getResultOrThrow() }
        assertEquals(-32000, ex.code)
    }

    @Test
    fun `a throwing notification listener does not kill the connection`() {
        val daemon = echoingDaemon()
        val c = JsonRpcClient(daemon).also { client = it }
        c.startListening { throw IllegalStateException("boom") }

        daemon.pushNotification("""{"jsonrpc":"2.0","method":"logs/message","params":{"line":"x"}}""")
        // The reader thread must survive the listener. Before, the throw escaped readLoop's
        // IOException-only catch, marked the connection closed for good and left the UI
        // reporting "Running" over an RPC that failed every later call.
        val after = c.call("ok/after", emptyMap(), timeoutMs = 5_000)
        assertEquals("ok/after", after.getResultOrThrow().get("method").asString)
    }

    @Test
    fun `a JSON line that is not a response we can map does not kill the connection`() {
        val daemon = echoingDaemon()
        val c = JsonRpcClient(daemon).also { client = it }
        // Valid JSON with an id, so it passes the first parse, but the id isn't an int —
        // Gson throws on the SECOND parse, which used to escape the reader loop.
        daemon.pushNotification("""{"jsonrpc":"2.0","id":"not-an-int","result":{}}""")
        val after = c.call("ok/after", emptyMap(), timeoutMs = 5_000)
        assertEquals("ok/after", after.getResultOrThrow().get("method").asString)
    }

    @Test
    fun `close returns promptly against an alive-but-silent daemon`() {
        // The reader thread is parked in readLine() on a pipe no one writes to, and
        // interrupt() can't unblock a pipe read. close() used to run reader.close() BEFORE
        // process.destroy() — and BufferedReader.close() waits on the lock the parked read
        // holds — so Stop Engine (and IDE shutdown behind its @Synchronized stop()) blocked
        // for the rest of the crawl. Destroying the process first is what frees the reader.
        val daemon = SilentDaemon()
        val c = JsonRpcClient(daemon).also { client = it }
        Thread.sleep(200) // let the reader thread reach readLine()

        val closer = Thread { c.close() }.apply { start() }
        closer.join(10_000)
        val blocked = closer.isAlive
        daemon.destroy() // release a close() that blocked, so the rest of the suite can run
        assertFalse(blocked, "close() blocked — it did not kill the process before closing the reader")
    }

    @Test
    fun `notify writes a request with a method but no id`() {
        val daemon = FakeDaemon { _, _ -> }
        val c = JsonRpcClient(daemon).also { client = it }
        c.notify("logs/subscribe", mapOf("k" to "v"))
        // give the daemon thread a moment to read the line
        val deadline = System.currentTimeMillis() + 2_000
        while (System.currentTimeMillis() < deadline && synchronized(daemon.requests) { daemon.requests.isEmpty() }) {
            Thread.sleep(10)
        }
        val sent = synchronized(daemon.requests) { daemon.requests.single() }
        assertEquals("logs/subscribe", sent.get("method").asString)
        assertEquals("2.0", sent.get("jsonrpc").asString)
        assertFalse(sent.has("id"))
    }
}
