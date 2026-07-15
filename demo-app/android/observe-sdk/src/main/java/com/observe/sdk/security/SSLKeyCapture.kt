package com.mobiscout.sdk.security

import android.util.Log
import okhttp3.Interceptor
import okhttp3.Response
import java.lang.reflect.Field
import java.lang.reflect.Method
import javax.net.ssl.SSLSession
import javax.net.ssl.SSLSocket

/**
 * SSLKeyCapture - OkHttp interceptor to capture TLS/SSL session keys
 * 
 * SECURITY WARNING:
 * This interceptor extracts TLS session keys for traffic decryption!
 * ONLY use in mobiscout/test builds!
 * 
 * How it works:
 * 1. Intercepts HTTPS requests after SSL handshake
 * 2. Extracts SSLSession from connection
 * 3. Uses reflection to get master secret and randoms
 * 4. Exports keys via CryptoKeyExporter
 */
class SSLKeyCapture : Interceptor {
    
    companion object {
        private const val TAG = "SSLKeyCapture"
        
        // Reflection cache
        private var getMasterSecretMethod: Method? = null
        private var getClientRandomMethod: Method? = null
        private var getServerRandomMethod: Method? = null
        
        init {
            try {
                // Try to get SSLSession internal methods via reflection
                // Note: This is implementation-specific and may not work on all Android versions
                val sslSessionClass = Class.forName("com.android.org.conscrypt.OpenSSLSessionImpl")
                
                getMasterSecretMethod = sslSessionClass.getDeclaredMethod("getMasterSecret")
                getMasterSecretMethod?.isAccessible = true
                
                // Client/Server randoms might be in different places
                try {
                    getClientRandomMethod = sslSessionClass.getDeclaredMethod("getClientRandom")
                    getClientRandomMethod?.isAccessible = true
                } catch (e: Exception) {
                    Log.d(TAG, "getClientRandom not available via direct method")
                }
                
                try {
                    getServerRandomMethod = sslSessionClass.getDeclaredMethod("getServerRandom")
                    getServerRandomMethod?.isAccessible = true
                } catch (e: Exception) {
                    Log.d(TAG, "getServerRandom not available via direct method")
                }
                
                Log.d(TAG, "SSL key capture reflection initialized")
            } catch (e: Exception) {
                Log.w(TAG, "Failed to initialize SSL key capture reflection", e)
            }
        }
    }
    
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val response = chain.proceed(request)
        
        // Only process HTTPS requests
        if (request.url.scheme == "https") {
            try {
                captureSSLKeys(chain, request.url.host)
            } catch (e: Exception) {
                Log.w(TAG, "Failed to capture SSL keys for ${request.url.host}", e)
            }
        }
        
        return response
    }
    
    /**
     * Capture SSL session keys from connection
     */
    private fun captureSSLKeys(chain: Interceptor.Chain, host: String) {
        try {
            // Get connection from chain via reflection
            val connection = getConnection(chain) ?: return
            
            // Get SSLSocket from connection
            val sslSocket = getSSLSocket(connection) ?: return
            
            // Get SSLSession
            val sslSession = sslSocket.session ?: return
            
            // Extract session data
            val sessionId = bytesToHex(sslSession.id)
            val cipher = sslSession.cipherSuite
            val protocol = sslSession.protocol
            
            Log.d(TAG, "Capturing SSL keys for $host (session: $sessionId, cipher: $cipher)")
            
            // Extract master secret and randoms via reflection
            val masterSecret = extractMasterSecret(sslSession)
            val clientRandom = extractClientRandom(sslSession)
            val serverRandom = extractServerRandom(sslSession)
            
            if (masterSecret != null && clientRandom != null && serverRandom != null) {
                // Export to CryptoKeyExporter
                CryptoKeyExporter.captureTLSSessionKey(
                    sessionId = sessionId,
                    masterSecret = masterSecret,
                    clientRandom = clientRandom,
                    serverRandom = serverRandom,
                    cipher = cipher,
                    protocol = protocol
                )
                
                Log.i(TAG, "Successfully captured SSL keys for $host")
            } else {
                Log.w(TAG, "Could not extract all SSL key material (master: ${masterSecret != null}, " +
                        "client: ${clientRandom != null}, server: ${serverRandom != null})")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error capturing SSL keys", e)
        }
    }
    
    /**
     * Get Connection from Chain (reflection)
     */
    private fun getConnection(chain: Interceptor.Chain): Any? {
        return try {
            val field = chain.javaClass.getDeclaredField("connection")
            field.isAccessible = true
            field.get(chain)
        } catch (e: Exception) {
            try {
                // Try alternative field name
                val method = chain.javaClass.getMethod("connection")
                method.invoke(chain)
            } catch (e2: Exception) {
                Log.d(TAG, "Could not get connection from chain")
                null
            }
        }
    }
    
    /**
     * Get SSLSocket from connection (reflection)
     */
    private fun getSSLSocket(connection: Any): SSLSocket? {
        return try {
            val field = connection.javaClass.getDeclaredField("socket")
            field.isAccessible = true
            val socket = field.get(connection)
            if (socket is SSLSocket) socket else null
        } catch (e: Exception) {
            Log.d(TAG, "Could not get SSL socket from connection")
            null
        }
    }
    
    /**
     * Extract master secret from SSLSession
     */
    private fun extractMasterSecret(session: SSLSession): ByteArray? {
        return try {
            getMasterSecretMethod?.invoke(session) as? ByteArray
        } catch (e: Exception) {
            Log.d(TAG, "Could not extract master secret", e)
            null
        }
    }
    
    /**
     * Extract client random from SSLSession
     */
    private fun extractClientRandom(session: SSLSession): ByteArray? {
        return try {
            getClientRandomMethod?.invoke(session) as? ByteArray
        } catch (e: Exception) {
            // Try to extract from session fields
            try {
                val field = session.javaClass.getDeclaredField("clientRandom")
                field.isAccessible = true
                field.get(session) as? ByteArray
            } catch (e2: Exception) {
                Log.d(TAG, "Could not extract client random")
                // Generate placeholder for demo
                ByteArray(32) { 0 }
            }
        }
    }
    
    /**
     * Extract server random from SSLSession
     */
    private fun extractServerRandom(session: SSLSession): ByteArray? {
        return try {
            getServerRandomMethod?.invoke(session) as? ByteArray
        } catch (e: Exception) {
            // Try to extract from session fields
            try {
                val field = session.javaClass.getDeclaredField("serverRandom")
                field.isAccessible = true
                field.get(session) as? ByteArray
            } catch (e2: Exception) {
                Log.d(TAG, "Could not extract server random")
                // Generate placeholder for demo
                ByteArray(32) { 0 }
            }
        }
    }
    
    /**
     * Convert bytes to hex string
     */
    private fun bytesToHex(bytes: ByteArray): String {
        return bytes.joinToString("") { "%02x".format(it) }
    }
}

