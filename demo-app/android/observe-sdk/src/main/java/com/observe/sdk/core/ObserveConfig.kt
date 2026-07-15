package com.mobiscout.sdk.core

/**
 * Configuration for Mobiscout SDK
 * 
 * @param enabled Enable/disable SDK
 * @param autoStart Automatically start observation on init
 * @param eventBufferSize Number of events to buffer before export
 * @param maxStoredFiles Maximum number of event files to keep
 * @param exportEndpoint Optional network endpoint for event upload
 * @param debugMode Enable verbose logging
 * @param exportCryptoKeys Export TLS/SSL keys for traffic decryption (SECURITY WARNING: test builds only!)
 * @param bypassCertPinning Disable SSL certificate pinning (SECURITY WARNING: test builds only!)
 */
data class MobiscoutConfig(
    val enabled: Boolean = true,
    val autoStart: Boolean = true,
    val eventBufferSize: Int = 50,
    val maxStoredFiles: Int = 10,
    val exportEndpoint: String? = null,
    val debugMode: Boolean = true,
    val exportCryptoKeys: Boolean = false,
    val bypassCertPinning: Boolean = false
) {
    companion object {
        /**
         * Default configuration
         */
        fun default() = MobiscoutConfig()
        
        /**
         * Disabled configuration (for production)
         */
        fun disabled() = MobiscoutConfig(enabled = false)
        
        /**
         * Full observation mode with crypto key export
         * 
         * SECURITY WARNING:
         * This mode disables SSL security and exports encryption keys!
         * ONLY use in mobiscout/test builds!
         */
        fun fullObservation() = MobiscoutConfig(
            enabled = true,
            autoStart = true,
            exportCryptoKeys = true,
            bypassCertPinning = true,
            debugMode = true
        )
    }
}
