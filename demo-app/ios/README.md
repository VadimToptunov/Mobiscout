# iOS Demo App

iOS version of FinDemo application built with SwiftUI.

---

## Features

### Implemented:

- Onboarding (swipeable pages with TabView)
- Authentication (Login screen)
- KYC screen (mock document scanning)
- Home screen with balance and quick actions
- Top-up with amount input and WebView payment
- Send money flow with recipient selection
- Transaction history display
- Accessibility identifiers on all interactive elements

### TODO (For Production):

- [ ] Regula Document Reader SDK integration
- [ ] Real API integration (currently mock)
- [ ] Biometric authentication
- [ ] QR code scanner
- [ ] Local data persistence (CoreData/SwiftData)
- [ ] Error handling and validation

---

## Project Structure

```
FinDemo/
 FinDemo.xcodeproj/        # Xcode project file
 FinDemo/
     FinDemoApp.swift       # App entry point + AppState
     ContentView.swift      # Main navigation controller
     Views/
        OnboardingView.swift    # Swipeable onboarding screens
        LoginView.swift         # Login with username/password
        KYCView.swift           # Document verification (mock)
        HomeView.swift          # Main screen with balance
        TopUpView.swift         # Add funds with WebView
        SendMoneyView.swift     # Transfer money flow
     Assets.xcassets/       # Images and colors
```

---

## Tech Stack

- **SwiftUI** - Modern declarative UI framework
- **Combine** - Reactive state management via `@Published`
- **WKWebView** - Embedded web view for payment gateway
- **NavigationView** - Screen navigation
- **Environment Objects** - Shared app state across views

---

## Accessibility Identifiers

All interactive elements have `accessibilityIdentifier` for test automation:

### Onboarding

- `onboarding_previous_button`
- `onboarding_next_button`
- `onboarding_get_started_button`
- `onboarding_image`
- `onboarding_title`
- `onboarding_description`

### Login

- `login_logo`
- `login_title`
- `login_username_field`
- `login_password_field`
- `login_button`
- `login_forgot_password`
- `login_signup_button`
- `login_error_message`

### KYC

- `kyc_title`
- `kyc_description`
- `kyc_document_type_label`
- `kyc_document_type_picker`
- `kyc_document_icon`
- `kyc_verification_status`
- `kyc_scan_instruction`
- `kyc_scan_button`
- `kyc_continue_button`
- `kyc_skip_button`

### Home

- `home_balance_label`
- `home_balance_value`
- `home_balance_status`
- `home_quick_actions_title`
- `home_topup_button`
- `home_send_button`
- `home_scanqr_button`
- `home_transactions_title`
- `home_logout_button`

### Top-Up

- `topup_title`
- `topup_amount_field`
- `topup_quick_25`, `topup_quick_50`, `topup_quick_100`, `topup_quick_200`
- `topup_quick_amounts`
- `topup_card_label`
- `topup_card_Visa_••••_1234`
- `topup_continue_button`
- `topup_cancel_button`
- `topup_payment_webview`
- `topup_payment_confirm`
- `topup_payment_cancel`

### Send Money

- `send_recipient_label`
- `send_recipient_John_Doe`, `send_recipient_Jane_Smith`, `send_recipient_Bob_Johnson`
- `send_amount_label`
- `send_amount_field`
- `send_quick_10`, `send_quick_25`, `send_quick_50`, `send_quick_100`
- `send_quick_amounts`
- `send_available_balance`
- `send_note_label`
- `send_note_field`
- `send_review_button`
- `send_cancel_button`
- `send_confirm_recipient`
- `send_confirm_amount`
- `send_confirm_note`
- `send_confirm_button`
- `send_confirm_cancel`

---

## How to Build & Run

### Requirements:

- macOS with Xcode 15.0+
- iOS 16.0+ deployment target
- Swift 5.9+

### Steps:

1. **Open Project:**
   ```bash
   cd demo-app/ios/FinDemo
   open FinDemo.xcodeproj
   ```

2. **Select Target:**
    - Choose iPhone simulator or device
    - Run scheme: `FinDemo`

3. **Build & Run:**
    - Press `⌘R` or click the Play button
    - App will launch on selected simulator/device

4. **Mock Login Credentials:**
    - Username: Any non-empty string
    - Password: Any non-empty string

---

## Configuration

### Build Settings:

- **Deployment Target:** iOS 16.0
- **Swift Version:** 5.0
- **Code Signing:** Automatic (for development)

### Future Build Schemes:

(To be implemented in Phase 3)

- **Observe** - With Observe SDK instrumentation
- **Test** - Clean build for test automation
- **Production** - Release configuration

---

## App Flow

```
Onboarding (3 screens)
    ↓
Login Screen
    ↓
KYC Verification
    ↓
Home Screen
    → Top-Up (with WebView payment)
    → Send Money (recipient + amount)
    → Scan QR (TODO)
```

---

## Security Notes

- Passwords are NOT stored (demo only)
- No real payment processing
- WebView loads mock payment URL
- KYC scanning is simulated (no real document processing)

**For production:** Implement proper authentication, secure storage, and real KYC integration.

---

## Current Status

**Status:** 🟢 Core Demo Complete (Phase 3 - Step 1)  
**Next Steps:**

1. iOS Observe SDK implementation
2. iOS Static Analyzer for SwiftUI
3. Cross-platform generator updates
4. Regula SDK integration

---

## Implementation Notes

### SwiftUI vs Jetpack Compose Parity:

| Feature           | Android (Compose)       | iOS (SwiftUI)                   |
|-------------------|-------------------------|---------------------------------|
| Swipeable screens | HorizontalPager         | TabView                         |
| Test IDs          | testTag                 | accessibilityIdentifier         |
| State management  | remember/mutableStateOf | @State                          |
| Shared state      | ViewModel               | @EnvironmentObject              |
| WebView           | AndroidView + WebView   | UIViewRepresentable + WKWebView |
| Navigation        | NavHost                 | NavigationView                  |

### Key Design Decisions:

- Used `@EnvironmentObject` for `AppState` instead of ViewModels (simpler for demo)
- Mock API calls instead of real networking (can be swapped easily)
- Skipped CoreData/SwiftData (not needed for demo)
- WebView payment flow matches Android implementation

---

## 🧪 Testing

The app is ready for:

- Manual testing on simulators/devices
- Appium/XCUITest automation (all elements have accessibility IDs)
- Observe SDK integration (next phase)

---

**Phase 3 - iOS Demo App:**  Complete!

