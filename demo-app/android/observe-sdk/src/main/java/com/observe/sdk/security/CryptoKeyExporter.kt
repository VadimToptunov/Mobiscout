package com.mobiscout.sdk.security

import android.content.Context
import android.util.Base64
import android.util.Log
import com.mobiscout.sdk.core.MobiscoutConfig
import java.io.File
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.PublicKey
import javax.crypto.SecretKey
import javax.crypto.spec.SecretKeySpec
import org.json.JSONObject

/**
 * CryptoKeyExporter - Exports device crypto keys for test traffic decryption
 * 
 * SECURITY WARNING:
 * This should ONLY be used in mobiscout/test builds!
 * NEVER enable in production builds!
 * 
 * Purpose:
 * - Export TLS/SSL session keys
 * - Export device encryption keys
 * - Enable traffic decryption during tests
 * - Bypass certificate pinning in test builds
 */
object CryptoKeyExporter {
    private const val TAG = "CryptoKeyExporter"
    
    // Storage for session keys
    private val tlsSessionKeys = mutableMapOf<String, TLSSessionKey>()
    
    // Device encryption keys (for app-level encryption)
    private var deviceKeyPair: KeyPair? = null
    private var symmetricKey: SecretKey? = null
    
    /**
     * TLS Session Key data
     */
    data class TLSSessionKey(
        val sessionId: String,
        val masterSecret: ByteArray,
        val clientRandom: ByteArray,
        val serverRandom: ByteArray,
        val cipher: String,
        val protocol: String,
        val timestamp: Long
    ) {
        fun toJson(): JSONObject {
            return JSONObject().apply {
                put("session_id", sessionId)
                put("master_secret", Base64.encodeToString(masterSecret, Base64.NO_WRAP))
                put("client_random", Base64.encodeToString(clientRandom, Base64.NO_WRAP))
                put("server_random", Base64.encodeToString(serverRandom, Base64.NO_WRAP))
                put("cipher", cipher)
                put("protocol", protocol)
                put("timestamp", timestamp)
            }
        }
    }
    
    /**
     * Device crypto keys export
     */
    data class DeviceKeys(
        val publicKey: String,
        val privateKey: String,
        val symmetricKey: String,
        val keyType: String = "RSA",
        val keySize: Int = 2048
    ) {
        fun toJson(): JSONObject {
            return JSONObject().apply {
                put("public_key", publicKey)
                put("private_key", privateKey)
                put("symmetric_key", symmetricKey)
                put("key_type", keyType)
                put("key_size", keySize)
            }
        }
    }
    
    /**
     * Initialize crypto key exporter
     */
    fun initialize(config: MobiscoutConfig) {
        if (!config.exportCryptoKeys) {
            Log.w(TAG, "Crypto key export disabled by config")
            return
        }
        
        Log.i(TAG, "Initializing crypto key exporter")
        
        // Generate device key pair if needed
        if (deviceKeyPair == null) {
            generateDeviceKeys()
        }
        
        Log.i(TAG, "Crypto key exporter initialized")
    }
    
    /**
     * Generate device encryption keys
     */
    private fun generateDeviceKeys() {
        try {
            // Generate RSA key pair
            val keyGen = KeyPairGenerator.getInstance("RSA")
            keyGen.initialize(2048)
            deviceKeyPair = keyGen.generateKeyPair()
            
            // Generate symmetric AES key
            val aesKeyGen = javax.crypto.KeyGenerator.getInstance("AES")
            aesKeyGen.init(256)
            symmetricKey = aesKeyGen.generateKey()
            
            Log.d(TAG, "Device keys generated successfully")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to generate device keys", e)
        }
    }
    
    /**
     * Capture TLS session key
     * 
     * This is called by NetworkMobiscoutr when SSL handshake completes
     */
    fun captureTLSSessionKey(
        sessionId: String,
        masterSecret: ByteArray,
        clientRandom: ByteArray,
        serverRandom: ByteArray,
        cipher: String,
        protocol: String
    ) {
        val key = TLSSessionKey(
            sessionId = sessionId,
            masterSecret = masterSecret,
            clientRandom = clientRandom,
            serverRandom = serverRandom,
            cipher = cipher,
            protocol = protocol,
            timestamp = System.currentTimeMillis()
        )
        
        tlsSessionKeys[sessionId] = key
        
        Log.d(TAG, "Captured TLS session key: $sessionId (cipher: $cipher, protocol: $protocol)")
    }
    
    /**
     * Export all crypto keys to file
     */
    fun exportKeys(context: Context, sessionId: String): File? {
        try {
            val exportDir = File(context.getExternalFilesDir(null), "mobiscout/crypto")
            if (!exportDir.exists()) {
                exportDir.mkdirs()
            }
            
            val exportFile = File(exportDir, "crypto_keys_$sessionId.json")
            
            val exportData = JSONObject().apply {
                put("session_id", sessionId)
                put("export_timestamp", System.currentTimeMillis())
                
                // Device keys
                deviceKeyPair?.let { keyPair ->
                    val deviceKeys = DeviceKeys(
                        publicKey = Base64.encodeToString(keyPair.public.encoded, Base64.NO_WRAP),
                        privateKey = Base64.encodeToString(keyPair.private.encoded, Base64.NO_WRAP),
                        symmetricKey = symmetricKey?.let { 
                            Base64.encodeToString(it.encoded, Base64.NO_WRAP) 
                        } ?: ""
                    )
                    put("device_keys", deviceKeys.toJson())
                }
                
                // TLS session keys
                val tlsKeys = org.json.JSONArray()
                tlsSessionKeys.values.forEach { key ->
                    tlsKeys.put(key.toJson())
                }
                put("tls_session_keys", tlsKeys)
                
                // Metadata
                put("key_count", tlsSessionKeys.size)
            }
            
            exportFile.writeText(exportData.toString(2))
            
            Log.i(TAG, "Exported ${tlsSessionKeys.size} TLS keys to: ${exportFile.absolutePath}")
            
            return exportFile
        } catch (e: Exception) {
            Log.e(TAG, "Failed to export crypto keys", e)
            return null
        }
    }
    
    /**
     * Export TLS keys in NSS Key Log format (for Wireshark)
     * 
     * Format: CLIENT_RANDOM <client_random> <master_secret>
     */
    fun exportNSSKeyLog(context: Context, sessionId: String): File? {
        try {
            val exportDir = File(context.getExternalFilesDir(null), "mobiscout/crypto")
            if (!exportDir.exists()) {
                exportDir.mkdirs()
            }
            
            val keyLogFile = File(exportDir, "tls_keys_$sessionId.txt")
            
            val keyLogContent = StringBuilder()
            keyLogContent.appendLine("# TLS Key Log - Session: $sessionId")
            keyLogContent.appendLine("# Timestamp: ${System.currentTimeMillis()}")
            keyLogContent.appendLine("# Format: CLIENT_RANDOM <client_random> <master_secret>")
            keyLogContent.appendLine("#")
            
            tlsSessionKeys.values.forEach { key ->
                val clientRandom = bytesToHex(key.clientRandom)
                val masterSecret = bytesToHex(key.masterSecret)
                keyLogContent.appendLine("CLIENT_RANDOM $clientRandom $masterSecret")
            }
            
            keyLogFile.writeText(keyLogContent.toString())
            
            Log.i(TAG, "Exported NSS key log to: ${keyLogFile.absolutePath}")
            
            return keyLogFile
        } catch (e: Exception) {
            Log.e(TAG, "Failed to export NSS key log", e)
            return null
        }
    }
    
    /**
     * Get device public key (for server-side encryption)
     */
    fun getDevicePublicKey(): PublicKey? = deviceKeyPair?.public
    
    /**
     * Get device private key (for decryption)
     */
    fun getDevicePrivateKey(): PrivateKey? = deviceKeyPair?.private
    
    /**
     * Get symmetric key (for fast encryption)
     */
    fun getSymmetricKey(): SecretKey? = symmetricKey
    
    /**
     * Clear all captured keys
     */
    fun clearKeys() {
        tlsSessionKeys.clear()
        Log.d(TAG, "Cleared all TLS session keys")
    }
    
    /**
     * Get stats
     */
    fun getStats(): Map<String, Any> {
        return mapOf(
            "tls_keys_count" to tlsSessionKeys.size,
            "device_keys_generated" to (deviceKeyPair != null)
        )
    }
    
    // Helper: Convert bytes to hex string
    private fun bytesToHex(bytes: ByteArray): String {
        return bytes.joinToString("") { "%02x".format(it) }
    }
}

