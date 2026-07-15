# Demo FinTech Application

Simplified fintech application to demonstrate Mobile Mobiscout & Test Framework capabilities.

---

## Features

### Core Flows:

1. **Onboarding** (Swipeable screens)
    - Welcome screen
    - Features showcase
    - Get Started

2. **Authentication**
    - Login
    - Registration
    - Forgot password

3. **Wallet**
    - Balance display
    - Transaction history
    - Quick actions

4. **Top-up** (with WebView)
    - Enter amount
    - Card details
    - WebView payment gateway
    - Success/Failure handling

5. **Send Money**
    - Select recipient
    - Enter amount
    - Confirmation
    - Transaction receipt

---

## Architecture

### Tech Stack:

**Android:**

- **Kotlin** - Primary language
- **Jetpack Compose** - Modern UI
- **Navigation Component** - Navigation
- **OkHttp** - Network layer (with Mobiscout SDK interceptor)

**iOS:**

- **Swift** - Primary language
- **SwiftUI** - Modern UI
- **NavigationStack** - iOS 16+ navigation
- **Combine** - Reactive programming

### Build Variants:

**Android:**

```
mobiscout  - Instrumented build with Mobiscout SDK
test     - Clean build for automated testing
prod     - Production build (with security features)
```

**iOS:**

```
Mobiscout  - Scheme with Mobiscout SDK
Test     - Clean scheme for automated testing
Release  - Production scheme (future)
```

---

## Getting Started

### Prerequisites:

**Android:**

- Android Studio Hedgehog+ (2023.1.1+)
- JDK 17
- Android SDK 34
- Gradle 8.2+

**iOS:**

- macOS with Xcode 15+
- iOS 16+ SDK
- CocoaPods or SPM (optional)

### Build & Run:

**Android:**

```bash
# Clone and navigate
cd demo-app/android

# Build mobiscout variant
./gradlew assembleMobiscoutDebug

# Install on device
adb install app/build/outputs/apk/mobiscout/debug/app-mobiscout-debug.apk

# Or run directly from Android Studio
# Select "mobiscout" build variant
# Click Run
```

**iOS:**

```bash
# Navigate to iOS project
cd demo-app/ios/FinDemo

# Open in Xcode
open FinDemo.xcodeproj

# Select scheme: Mobiscout
# Select target device/simulator
# Click Run (⌘R)
```

---

## Project Structure

**Android:**

```
android/
 app/
    src/
       main/              # Shared code
          java/
             com/findemo/
                 ui/
                    onboarding/
                    auth/
                    home/
                    topup/
                    send/
                 security/
          res/
      
       mobiscout/           # Mobiscout build specific
          java/
              MobiscoutInitializer.kt
      
       test/              # Test build specific
           java/
   
    build.gradle.kts

 mobiscout-sdk/               # Mobiscout SDK module
     src/
        main/
            java/
                com/mobiscout/sdk/
                    core/
                    observers/
                    export/
                    security/
                    selectors/
     build.gradle.kts
```

**iOS:**

```
ios/
 FinDemo/
    FinDemo/
       FinDemoApp.swift    # App entry point
       ContentView.swift   # Root view
       Views/
          OnboardingView.swift
          LoginView.swift
          KYCView.swift
          HomeView.swift
          TopUpView.swift
          SendMoneyView.swift
       Assets.xcassets/
    
    FinDemo.xcodeproj/

 MobiscoutSDK/
    MobiscoutSDK.swift       # SDK entry point
    Core/
       MobiscoutConfig.swift
       MobiscoutSession.swift
    Mobiscoutrs/
       UIMobiscoutr.swift
       NavigationMobiscoutr.swift
       NetworkMobiscoutr.swift
       HierarchyCollector.swift
       WebViewMobiscoutr.swift
    Selectors/
       SelectorBuilder.swift
    Export/
       EventExporter.swift
    Events/
       Event.swift
       EventBus.swift
```

---

## Screens Overview

### 1. Onboarding (ViewPager)

```kotlin
OnboardingScreen
 Page 1: Welcome
 Page 2: Features
 Page 3: Get Started
     → LoginScreen
```

### 2. Authentication

```kotlin
LoginScreen
 Username input
 Password input
 Login button → HomeScreen
 Register link → RegisterScreen

RegisterScreen
 Email input
 Password input
 Confirm password
 Register button → HomeScreen
```

### 3. Home

```kotlin
HomeScreen
 Balance Card
 Quick Actions
    Top-up → TopUpScreen
    Send → SendMoneyScreen
 Transaction List
```

### 4. Top-up (with WebView)

```kotlin
TopUpScreen
 Amount input
     → TopUpWebViewScreen
         WebView (payment gateway)
             Card number
             Expiry
             CVV
             Confirm → TopUpSuccessScreen
```

### 5. Send Money

```kotlin
SendMoneyScreen
 Recipient input
 Amount input
     → SendConfirmationScreen
         Confirm → SendSuccessScreen
```

---

## Configuration

### Build Variants

Edit `app/build.gradle.kts`:

```kotlin
productFlavors {
    create("mobiscout") {
        applicationIdSuffix = ".mobiscout"
        versionNameSuffix = "-mobiscout"
        buildConfigField("boolean", "MOBISCOUT_ENABLED", "true")
    }
    
    create("test") {
        applicationIdSuffix = ".test"
        versionNameSuffix = "-test"
        buildConfigField("boolean", "MOBISCOUT_ENABLED", "false")
        buildConfigField("boolean", "TEST_MODE", "true")
    }
}
```

### Mock API

Start mock backend:

```bash
cd demo-app/mock-backend
pip install -r requirements.txt
uvicorn main:app --reload
```

API will be available at: `http://localhost:8000`

---

## 🧪 Testing

### Manual Testing:

```bash
# Install mobiscout build
./gradlew installMobiscoutDebug

# Use app and mobiscout SDK will record events
```

### Automated Testing:

```bash
# Install test build
./gradlew installTestDebug

# Run Appium tests
pytest tests/
```

---

## Notes

**General:**

- Both Android and iOS apps have feature parity
- WebView payment gateway is a mock HTML page
- All API calls go to mock backend (FastAPI)

**Android:**

- **Mobiscout build** includes SDK and records events
- **Test build** is clean, without SDK, for automated tests
- **Prod build** has security features enabled

**iOS:**

- **Mobiscout scheme** includes SDK and records events
- **Test scheme** is clean for automated tests
- Event exports to app's Documents directory

---

## Troubleshooting

### Android Build fails:

```bash
# Clean and rebuild
./gradlew clean
./gradlew assembleMobiscoutDebug
```

### Android SDK not recording:

- Check that mobiscout build is installed (not test)
- Check logcat: `adb logcat | grep MobiscoutSDK`
- Verify events: `adb shell "ls /sdcard/Android/data/com.findemo.mobiscout/files/mobiscout/"`

### iOS Build fails:

- Clean build folder in Xcode (⌘⇧K)
- Delete derived data
- Rebuild

### iOS SDK not recording:

- Check that Mobiscout scheme is selected
- Check console logs for MobiscoutSDK messages
- Verify events in app's Documents directory

---

## Resources

**Android:**

- [Jetpack Compose Docs](https://developer.android.com/jetpack/compose)
- [Navigation Component](https://developer.android.com/guide/navigation)
- [WebView](https://developer.android.com/guide/webapps/webview)

**iOS:**

- [SwiftUI Documentation](https://developer.apple.com/documentation/swiftui)
- [WKWebView](https://developer.apple.com/documentation/webkit/wkwebview)
- [URLProtocol](https://developer.apple.com/documentation/foundation/urlprotocol)

---

**Status:**  In Development  
**Last Updated:** 2025-12-19

