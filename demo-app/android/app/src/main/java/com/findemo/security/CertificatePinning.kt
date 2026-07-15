package com.findemo.security

import android.util.Log
import okhttp3.CertificatePinner
import okhttp3.OkHttpClient
import java.security.cert.CertificateException
import javax.net.ssl.SSLPeerUnverifiedException

/**
 * Certificate Pinning for Production Builds
 * 
 * This implements SSL/TLS certificate pinning to prevent MITM attacks.
 * 
 * IMPORTANT:
 * - ENABLED in production builds
 * - DISABLED in mobiscout/test builds (via MobiscoutSDK bypass)
 * 
 * How it works:
 * - Pins public key hashes of trusted certificates
 * - Rejects connections with untrusted certificates
 * - Multiple pins for redundancy (primary + backup)
 */
object CertificatePinning {
    
    private const val TAG = "CertPinning"
    
    // Production API domain
    private const val API_DOMAIN = "api.findemo.com"
    
    /**
     * Certificate pins for production API
     * 
     * These are SHA-256 hashes of the certificate's Subject Public Key Info (SPKI)
     * 
     * To generate pins:
     * openssl s_client -connect api.findemo.com:443 | openssl x509 -pubkey -noout | \
     *   openssl rsa -pubin -outform der | openssl dgst -sha256 -binary | openssl enc -base64
     */
    private val PRODUCTION_PINS = listOf(
        // Primary certificate pin (current production cert)
        "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        
        // Backup certificate pin (for certificate rotation)
        "sha256/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    )
    
    /**
     * Create OkHttp client with certificate pinning enabled
     * 
     * This should be used in PRODUCTION builds only!
     * 
     * @param enablePinning If false, pinning is disabled (for mobiscout/test)
     * @return OkHttpClient.Builder with pinning configured
     */
    fun createSecureClient(enablePinning: Boolean = true): OkHttpClient.Builder {
        val builder = OkHttpClient.Builder()
        
        if (!enablePinning) {
            Log.w(TAG, " Certificate pinning DISABLED (test/mobiscout build)")
            return builder
        }
        
        // Build certificate pinner
        val certificatePinner = CertificatePinner.Builder()
            .apply {
                PRODUCTION_PINS.forEach { pin ->
                    add(API_DOMAIN, pin)
                }
            }
            .build()
        
        builder.certificatePinner(certificatePinner)
        
        // Add certificate pinning failure handler
        builder.addInterceptor { chain ->
            try {
                chain.proceed(chain.request())
            } catch (e: SSLPeerUnverifiedException) {
                // Certificate pinning failed - possible MITM attack!
                Log.e(TAG, " CERTIFICATE PINNING FAILED - MITM ATTACK DETECTED!", e)
                
                // Report to security monitoring
                SecurityMonitor.reportSecurityEvent(
                    SecurityEvent.CERTIFICATE_PINNING_FAILURE,
                    "domain" to API_DOMAIN,
                    "error" to e.message.orEmpty()
                )
                
                throw CertificateException("Certificate pinning failed: ${e.message}", e)
            }
        }
        
        Log.i(TAG, " Certificate pinning ENABLED for $API_DOMAIN (${PRODUCTION_PINS.size} pins)")
        
        return builder
    }
    
    /**
     * Verify if certificate pinning is active
     */
    fun isPinningActive(): Boolean {
        // Check if running in production build
        return BuildConfig.FLAVOR == "production"
    }
    
    /**
     * Get pinned domains
     */
    fun getPinnedDomains(): List<String> {
        return listOf(API_DOMAIN)
    }
}

