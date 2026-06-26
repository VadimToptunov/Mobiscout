# Regula KYC Integration Guide

## Overview

FinDemo integrates **Regula Document Reader SDK** for KYC (Know Your Customer) verification. This allows users to scan
and verify identity documents like passports, driver's licenses, and ID cards.

---

## Dependencies

### Gradle Configuration

**settings.gradle.kts:**

```kotlin
maven {
    url = uri("https://maven.regulaforensics.com/RegulaDocumentReader")
}
```

**app/build.gradle.kts:**

```kotlin
implementation("com.regula.documentreader:api:7.6.+@aar") {
    isTransitive = true
}

// Camera dependencies
implementation("androidx.camera:camera-camera2:1.3.1")
implementation("androidx.camera:camera-lifecycle:1.3.1")
implementation("androidx.camera:camera-view:1.3.1")
```

---

## Features

### KYC Screen Capabilities:

1. **Document Scanning** - Uses device camera to scan documents
2. **MRZ Reading** - Reads Machine Readable Zone
3. **Data Extraction** - Extracts name, document number, etc.
4. **Verification** - Validates document authenticity (full version)
5. **Permission Handling** - Requests camera permission properly

---

## Usage

### 1. Initialize SDK

SDK initialization happens automatically when KYCScreen loads:

```kotlin
private fun initializeRegulaSDK(
    context: Context,
    callback: (success: Boolean, error: String?) -> Unit
) {
    val config = DocReaderConfig()
    
    DocumentReader.Instance().initializeReader(
        context,
        config,
        object : IDocumentReaderInitCompletion {
            override fun onSuccess() {
                callback(true, null)
            }
            
            override fun onError(error: DocumentReaderException?) {
                callback(false, error?.message)
            }
        }
    )
}
```

### 2. Start Scanning

```kotlin
private fun startDocumentScanning(
    context: Context,
    callback: (result: String?, error: String?) -> Unit
) {
    DocumentReader.Instance().functionality().edit()
        .setScenario(Scenario.SCENARIO_MRZ)
        .apply()
    
    DocumentReader.Instance().showScanner(context, completion)
}
```

### 3. Extract Results

```kotlin
val documentType = results.getTextFieldValueByType(
    eVisualFieldType.FT_DOCUMENT_CLASS_NAME
)

val name = results.getTextFieldValueByType(
    eVisualFieldType.FT_SURNAME_AND_GIVEN_NAMES
)

val documentNumber = results.getTextFieldValueByType(
    eVisualFieldType.FT_DOCUMENT_NUMBER
)
```

---

## User Flow

```
Login → KYC Screen → Scan Document → Home Screen
         ↓
    [Skip for Now] → Home Screen
```

**Navigation:**

1. User logs in successfully
2. Navigated to KYC screen
3. Can either:
    - Scan document (camera opens)
    - Skip for now (demo mode)
4. After successful scan or skip → Home screen

---

## License

### Trial Mode (Current):

- SDK works in trial mode without license
- May have watermarks or limited features
- Sufficient for development and testing

### Production License:

To get production license:

1. Contact Regula Forensics: https://regulaforensics.com
2. Obtain license file
3. Add to project:

```kotlin
val config = DocReaderConfig(license)
DocumentReader.Instance().initializeReader(context, config, callback)
```

---

## UI Components

### KYC Screen Layout:

- **Title**: "Identity Verification"
- **Description**: Instructions for user
- **Status Icon**: Shows verification state
- **Scan Button**: Starts document scanning
    - Test tag: `scan_document_button`
- **Complete Button**: Appears after successful scan
    - Test tag: `complete_kyc_button`
- **Skip Button**: For demo/testing
    - Test tag: `skip_kyc_button`

---

## 🧪 Testing

### Test Scenarios:

1. **Happy Path**:
   ```
   Login → KYC → Click "Scan" → Allow Camera → Scan Document → Success → Complete
   ```

2. **Permission Denied**:
   ```
   Login → KYC → Click "Scan" → Deny Camera → Error shown
   ```

3. **Skip KYC**:
   ```
   Login → KYC → Click "Skip" → Home
   ```

4. **Cancel Scanning**:
   ```
   Login → KYC → Click "Scan" → Open Camera → Back button → Cancelled
   ```

### Test Tags:

```kotlin
// Screen
"kyc_screen"

// Buttons
"scan_document_button"
"complete_kyc_button"
"skip_kyc_button"
```

---

## Permissions

### Required Permissions:

**AndroidManifest.xml:**

```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-feature android:name="android.hardware.camera" android:required="false" />
<uses-feature android:name="android.hardware.camera.autofocus" android:required="false" />
```

### Runtime Permission Handling:

Handled automatically by KYCScreen using:

```kotlin
val cameraPermissionLauncher = rememberLauncherForActivityResult(
    contract = ActivityResultContracts.RequestPermission()
) { isGranted ->
    if (isGranted) {
        startDocumentScanning(...)
    }
}
```

---

## Supported Documents

Regula SDK supports:

- **Passports** (all countries)
- **ID Cards**
- **Driver's Licenses**
- **Visas**
- **Residence Permits**
- **And 10,000+ other document types**

### Scanning Modes:

- **MRZ** (Machine Readable Zone) - Default
- **BARCODE** - 1D/2D barcodes
- **OCR** - Optical Character Recognition
- **Full Recognition** - All features

---

## Troubleshooting

### Issue 1: SDK Fails to Initialize

**Solution:**

- Check internet connection (SDK may download data)
- Verify Maven repository is accessible
- Check logs for specific error

### Issue 2: Camera Not Opening

**Solution:**

- Verify camera permission granted
- Check device has camera
- Try on real device (emulator may not work)

### Issue 3: No Results from Scanning

**Solution:**

- Ensure good lighting
- Hold document flat
- Try different document
- Check document is supported

---

## Resources

- [Regula Documentation](https://docs.regulaforensics.com/)
- [Android Integration Guide](https://docs.regulaforensics.com/android)
- [API Reference](https://docs.regulaforensics.com/android/api-reference)
- [Sample App](https://github.com/regulaforensics/DocumentReader-Android)

---

## Notes for Observe SDK

### Events to Capture:

```json
{
  "event": "kyc_scan_started",
  "screen": "KYCScreen",
  "timestamp": 123456
}

{
  "event": "kyc_scan_completed",
  "screen": "KYCScreen",
  "document_type": "passport",
  "timestamp": 123457
}

{
  "event": "kyc_skipped",
  "screen": "KYCScreen",
  "timestamp": 123458
}
```

### Test Generation:

KYC screen will generate:

- Camera permission tests
- Document scanning tests
- Skip functionality tests
- Navigation tests

---

**Status:**  Integrated  
**Version:** 7.6.x  
**Last Updated:** 2025-12-19

