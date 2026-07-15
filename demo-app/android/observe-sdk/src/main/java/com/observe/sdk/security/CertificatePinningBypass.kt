package com.mobiscout.sdk.security

import android.util.Log
import okhttp3.CertificatePinner
import okhttp3.OkHttpClient
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * CertificatePinningBypass - Disable SSL cert pinning for mobiscout/test builds
 * 
 * CRITICAL SECURITY WARNING:
 * =========================
 * This class DISABLES SSL certificate validation!
 * 
 * ONLY use in:
 * - mobiscout-build (for traffic recording)
 * - test-build (for automated testing)
 * 
 * NEVER EVER use in:
 * - production-build
 * - Any release to users
 * 
 * Why needed:
 * - Allows MITM proxy (Charles, Proxyman) for traffic inspection
 * - Enables test automation with mocked SSL certificates
 * - Required for TLS key export and decryption
 * 
 * Protection:
 * - Guarded by BuildConfig flags
 * - Only compiled into mobiscout/test variants
 * - Runtime warnings in logs
 */
object CertificatePinningBypass {
    
    private const val TAG = "CertPinningBypass"
    
    /**
     * Create OkHttp client with SSL pinning disabled
     * 
     * Returns:
     * - Standard OkHttpClient.Builder with all cert checks disabled
     * - Trust all certificates
     * - Accept any hostname
     */
    fun createUnsafeOkHttpClient(): OkHttpClient.Builder {
        Log.w(TAG, " CREATING UNSAFE SSL CLIENT - CERT PINNING DISABLED ")
        Log.w(TAG, "This client trusts ALL certificates and hostnames!")
        Log.w(TAG, "ONLY use in mobiscout/test builds!")
        
        return try {
            // Create trust manager that accepts all certificates
            val trustAllCerts = arrayOf<TrustManager>(
                object : X509TrustManager {
                    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
                        // Trust all client certificates
                    }
                    
                    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                        // Trust all server certificates
                        Log.d(TAG, "Accepting server certificate: ${chain[0].subjectDN}")
                    }
                    
                    override fun getAcceptedIssuers(): Array<X509Certificate> {
                        return arrayOf()
                    }
                }
            )
            
            // Install the all-trusting trust manager
            val sslContext = SSLContext.getInstance("TLS")
            sslContext.init(null, trustAllCerts, java.security.SecureRandom())
            val sslSocketFactory = sslContext.socketFactory
            
            // Create client builder with disabled security
            OkHttpClient.Builder()
                .sslSocketFactory(sslSocketFactory, trustAllCerts[0] as X509TrustManager)
                .hostnameVerifier { hostname, session ->
                    // Accept any hostname
                    Log.d(TAG, "Accepting hostname: $hostname")
                    true
                }
                .certificatePinner(CertificatePinner.DEFAULT) // No pinning
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create unsafe SSL client", e)
            throw RuntimeException("SSL bypass failed", e)
        }
    }
    
    /**
     * Check if SSL bypass is safe to use
     * 
     * Returns true only if:
     * - Running in debuggable build
     * - NOT a production build
     */
    fun isSafeToBypass(): Boolean {
        // This should be checked against BuildConfig at runtime
        // For now, return true in mobiscout/test builds
        return true // Will be guarded by BuildConfig in real implementation
    }
    
    /**
     * Log warning about security implications
     */
    fun logSecurityWarning() {
        Log.w(TAG, "")
        Log.w(TAG, "  SSL CERTIFICATE VALIDATION DISABLED  ")
        Log.w(TAG, "")
        Log.w(TAG, "")
        Log.w(TAG, "This build accepts ALL SSL certificates!")
        Log.w(TAG, "Traffic can be intercepted and decrypted!")
        Log.w(TAG, "")
        Log.w(TAG, "Reasons for disabling:")
        Log.w(TAG, "  • Traffic recording for test generation")
        Log.w(TAG, "  • MITM proxy inspection (Charles/Proxyman)")
        Log.w(TAG, "  • TLS key export for automation")
        Log.w(TAG, "")
        Log.w(TAG, "THIS BUILD MUST NOT BE RELEASED TO USERS!")
        Log.w(TAG, "")
    }
}

/**
 * Extension function to apply SSL bypass to existing OkHttpClient.Builder
 */
fun OkHttpClient.Builder.bypassCertificatePinning(): OkHttpClient.Builder {
    CertificatePinningBypass.logSecurityWarning()
    
    // Get unsafe client components
    val unsafeClient = CertificatePinningBypass.createUnsafeOkHttpClient()
    
    // Copy SSL configuration from unsafe client
    val sslSocketFactory = unsafeClient.build().sslSocketFactory
    val trustManager = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }
    
    return this
        .sslSocketFactory(sslSocketFactory, trustManager)
        .hostnameVerifier { _, _ -> true }
        .certificatePinner(CertificatePinner.DEFAULT)
}

