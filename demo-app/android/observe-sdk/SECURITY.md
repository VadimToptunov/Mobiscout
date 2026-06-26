# Security Features & Warnings

## CRITICAL SECURITY WARNING

This SDK includes **DANGEROUS security bypass features** that **DISABLE SSL/TLS protection**!

### Features That Compromise Security:

1. **Crypto Key Export** - Exports TLS session keys for traffic decryption
2. **Certificate Pinning Bypass** - Disables SSL certificate validation
3. **SSL Key Capture** - Intercepts and stores encryption keys

---

## Purpose

These features are designed for **TEST AUTOMATION ONLY**:

- Enable traffic inspection during QA testing
- Allow MITM proxies (Charles, Proxyman) to intercept HTTPS
- Export encryption keys for automated test correlation
- Decrypt API responses in test scenarios

---

## Safe Usage

### ONLY enable in:

**`observe` build variant** - For recording user flows  
**`test` build variant** - For automated testing  
**Local development** - For debugging

### NEVER enable in:

**`production` build variant** - User-facing app  
**Release builds** - Distributed to users  
**App Store submissions** - Will be rejected

---

## Configuration

### Safe Configuration (Production)

```kotlin
// Production build - All security features enabled
ObserveSDK.initialize(
    app = this,
    config = ObserveConfig.disabled()
)
```

### Full Observation Mode (Test/Observe Only)

```kotlin
// ONLY in observe/test builds!
ObserveSDK.initialize(
    app = this,
    config = ObserveConfig.fullObservation()  //  DISABLES SSL SECURITY!
)
```

### Custom Configuration

```kotlin
ObserveConfig(
    enabled = true,
    exportCryptoKeys = true,     //  Export TLS keys
    bypassCertPinning = true,    //  Disable cert validation
    debugMode = true
)
```

---

## What Gets Exported

### 1. TLS Session Keys

```json
{
  "tls_session_keys": [
    {
      "session_id": "abc123...",
      "master_secret": "base64_encoded...",
      "client_random": "base64_encoded...",
      "server_random": "base64_encoded...",
      "cipher": "TLS_AES_128_GCM_SHA256",
      "protocol": "TLSv1.3",
      "timestamp": 1234567890
    }
  ]
}
```

### 2. Device Encryption Keys

```json
{
  "device_keys": {
    "public_key": "base64_encoded_rsa_public_key",
    "private_key": "base64_encoded_rsa_private_key",
    "symmetric_key": "base64_encoded_aes_key",
    "key_type": "RSA",
    "key_size": 2048
  }
}
```

### 3. NSS Key Log (Wireshark Format)

```
# TLS Key Log - Session: session_abc123
# Format: CLIENT_RANDOM <client_random> <master_secret>
CLIENT_RANDOM 1234567890abcdef... fedcba0987654321...
```

---

## Using Exported Keys

### Export Keys from Device

```kotlin
// Export all crypto keys (JSON format)
val keysFile = ObserveSDK.exportCryptoKeys()
println("Keys exported to: ${keysFile?.absolutePath}")

// Export TLS keys for Wireshark
val tlsFile = ObserveSDK.exportTLSKeys()
println("TLS keys: ${tlsFile?.absolutePath}")
```

### Pull Keys via ADB

```bash
# Pull crypto keys from device
adb pull /sdcard/Android/data/com.yourapp/files/observe/crypto/crypto_keys_session123.json

# Pull TLS keys for Wireshark
adb pull /sdcard/Android/data/com.yourapp/files/observe/crypto/tls_keys_session123.txt
```

### Decrypt Traffic with Wireshark

1. Open Wireshark
2. Go to **Edit → Preferences → Protocols → TLS**
3. Set **(Pre)-Master-Secret log filename** to the exported `.txt` file
4. Wireshark will now decrypt HTTPS traffic!

---

## Protection Mechanisms

### Build Variant Guards

```kotlin
// In app/build.gradle.kts
productFlavors {
    create("observe") {
        buildConfigField("boolean", "CRYPTO_EXPORT_ENABLED", "true")
    }
    create("production") {
        buildConfigField("boolean", "CRYPTO_EXPORT_ENABLED", "false")
    }
}
```

### Runtime Checks

```kotlin
if (!BuildConfig.CRYPTO_EXPORT_ENABLED) {
    throw SecurityException("Crypto export disabled in production!")
}
```

### ProGuard Rules (Production)

```proguard
# Strip crypto export classes from production builds
-assumenosideeffects class com.observe.sdk.security.CryptoKeyExporter {
    public *;
}
```

---

## Security Audit Checklist

Before releasing to production:

- [ ] `ObserveConfig.exportCryptoKeys` is **false**
- [ ] `ObserveConfig.bypassCertPinning` is **false**
- [ ] `observe-sdk` is **not included** in production build
- [ ] No crypto key files on device
- [ ] Certificate pinning is **enabled**
- [ ] ProGuard strips security bypass code

---

## Technical Details

### How Certificate Pinning Bypass Works

```kotlin
// Create trust manager that accepts ALL certificates
val trustAllCerts = arrayOf<TrustManager>(
    object : X509TrustManager {
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            // Trust everything (DANGEROUS!)
        }
        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }
)
```

### How TLS Key Capture Works

```kotlin
// Extract session keys via reflection
val session: SSLSession = sslSocket.session
val masterSecret = getMasterSecretMethod?.invoke(session) as ByteArray
val clientRandom = getClientRandomMethod?.invoke(session) as ByteArray
```

---

## Performance Impact

| Feature             | CPU Overhead | Memory Overhead | Storage       |
|---------------------|--------------|-----------------|---------------|
| Crypto Key Export   | < 1%         | ~5 MB           | ~1 MB/session |
| SSL Key Capture     | < 2%         | ~10 MB          | ~2 MB/session |
| Cert Pinning Bypass | None         | None            | None          |

---

## Risk Assessment

| Risk                    | Likelihood                   | Impact       | Mitigation           |
|-------------------------|------------------------------|--------------|----------------------|
| Keys leaked to attacker | **HIGH** if enabled in prod  | **CRITICAL** | Build variant guards |
| MITM attack             | **HIGH** if pinning bypassed | **HIGH**     | Only in test builds  |
| App rejection           | **CERTAIN** if in release    | **CRITICAL** | Automated checks     |
| User data exposure      | **MEDIUM** if misconfigured  | **CRITICAL** | Runtime validation   |

---

## References

- [OWASP Mobile Security Testing Guide](https://owasp.org/www-project-mobile-security-testing-guide/)
- [NSS Key Log Format](https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSS/Key_Log_Format)
- [Wireshark TLS Decryption](https://wiki.wireshark.org/TLS#tls-decryption)
- [Android Network Security Config](https://developer.android.com/training/articles/security-config)

---

## 🤝 Support

For security questions or concerns:

- Review this document thoroughly
- Test in isolated environment
- Never enable in production
- Report security issues privately

---

**Remember: With great power comes great responsibility!** 

