//
//  TopUpView.swift
//  FinDemo
//
//  Top-up screen with amount input and WebView payment
//

import SwiftUI
import WebKit

struct TopUpView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss
    @State private var amount = ""
    @State private var selectedCard = "Visa •••• 1234"
    @State private var showPaymentWebView = false
    @State private var paymentCompleted = false
    
    private let cards = ["Visa •••• 1234", "Mastercard •••• 5678", "Amex •••• 9012"]
    
    var body: some View {
        NavigationView {
            VStack(spacing: 30) {
                if !showPaymentWebView {
                    // Amount input section
                    VStack(spacing: 20) {
                        Text("Enter Amount")
                            .font(.headline)
                            .accessibilityIdentifier("topup_title")
                        
                        HStack {
                            Text("$")
                                .font(.system(size: 48, weight: .bold))
                                .foregroundColor(.secondary)
                            
                            TextField("0.00", text: $amount)
                                .font(.system(size: 48, weight: .bold))
                                .keyboardType(.decimalPad)
                                .multilineTextAlignment(.center)
                                .accessibilityIdentifier("topup_amount_field")
                        }
                        .padding()
                        .background(Color.secondary.opacity(0.1))
                        .cornerRadius(15)
                        .padding(.horizontal)
                        
                        // Quick amount buttons
                        HStack(spacing: 15) {
                            ForEach([25, 50, 100, 200], id: \.self) { value in
                                Button("$\(value)") {
                                    amount = String(value)
                                }
                                .buttonStyle(.bordered)
                                .accessibilityIdentifier("topup_quick_\(value)")
                            }
                        }
                        .accessibilityIdentifier("topup_quick_amounts")
                    }
                    .padding(.top, 30)
                    
                    Spacer()
                    
                    // Card selection
                    VStack(alignment: .leading, spacing: 15) {
                        Text("Select Card")
                            .font(.headline)
                            .padding(.horizontal)
                            .accessibilityIdentifier("topup_card_label")
                        
                        ForEach(cards, id: \.self) { card in
                            Button(action: { selectedCard = card }) {
                                HStack {
                                    Image(systemName: selectedCard == card ? "checkmark.circle.fill" : "circle")
                                        .foregroundColor(.blue)
                                    
                                    Image(systemName: "creditcard.fill")
                                        .foregroundColor(.secondary)
                                    
                                    Text(card)
                                        .foregroundColor(.primary)
                                    
                                    Spacer()
                                }
                                .padding()
                                .background(Color.secondary.opacity(0.1))
                                .cornerRadius(10)
                            }
                            .accessibilityIdentifier("topup_card_\(card.replacingOccurrences(of: " ", with: "_"))")
                        }
                    }
                    .padding(.horizontal)
                    
                    Spacer()
                    
                    // Continue button
                    Button(action: proceedToPayment) {
                        Text("Continue to Payment")
                            .fontWeight(.semibold)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(canProceed ? Color.blue : Color.gray)
                            .foregroundColor(.white)
                            .cornerRadius(10)
                    }
                    .disabled(!canProceed)
                    .padding(.horizontal)
                    .padding(.bottom, 30)
                    .accessibilityIdentifier("topup_continue_button")
                } else {
                    // WebView payment
                    PaymentWebView(
                        amount: amount,
                        onSuccess: {
                            completeTopUp()
                        },
                        onCancel: {
                            showPaymentWebView = false
                        }
                    )
                }
            }
            .navigationTitle("Top Up")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                    .accessibilityIdentifier("topup_cancel_button")
                }
            }
            .alert("Top Up Successful", isPresented: $paymentCompleted) {
                Button("OK") {
                    dismiss()
                }
            } message: {
                Text("$\(amount) has been added to your account")
            }
        }
    }
    
    private var canProceed: Bool {
        guard let amountValue = Double(amount) else { return false }
        return amountValue > 0
    }
    
    private func proceedToPayment() {
        showPaymentWebView = true
    }
    
    private func completeTopUp() {
        if let amountValue = Double(amount) {
            appState.topUp(amount: amountValue)
            paymentCompleted = true
        }
    }
}

struct PaymentWebView: View {
    let amount: String
    let onSuccess: () -> Void
    let onCancel: () -> Void
    
    var body: some View {
        VStack {
            // Mock payment gateway WebView
            WebView(
                url: URL(string: "https://demo-payment-gateway.example.com/pay?amount=\(amount)")!,
                onSuccess: onSuccess
            )
            .accessibilityIdentifier("topup_payment_webview")
            
            // Mock payment buttons
            HStack(spacing: 20) {
                Button("Cancel Payment") {
                    onCancel()
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("topup_payment_cancel")
                
                Button("Confirm Payment") {
                    onSuccess()
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("topup_payment_confirm")
            }
            .padding()
        }
    }
}

struct WebView: UIViewRepresentable {
    let url: URL
    let onSuccess: () -> Void
    
    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        
        // Register WebView for observation
        context.coordinator.registerObservation(webView: webView)
        
        return webView
    }
    
    func updateUIView(_ webView: WKWebView, context: Context) {
        let request = URLRequest(url: url)
        webView.load(request)
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(onSuccess: onSuccess)
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        let onSuccess: () -> Void
        private var webViewMobiscoutd = false
        // Strong reference to ensure WebView exists during deinit cleanup
        // Weak reference would become nil before deinit, preventing cleanup
        private var observedWebView: WKWebView?
        
        init(onSuccess: @escaping () -> Void) {
            self.onSuccess = onSuccess
        }
        
        func registerObservation(webView: WKWebView) {
            guard !webViewMobiscoutd else { return }
            
            // Register WebView with MobiscoutSDK
            MobiscoutSDK.shared.observeWebView(webView, screenName: "TopUpPaymentScreen")
            observedWebView = webView
            webViewMobiscoutd = true
        }
        
        deinit {
            // Unregister WebView from MobiscoutSDK to prevent resource leak
            if let webView = observedWebView {
                MobiscoutSDK.shared.stopObservingWebView(webView)
            }
        }
        
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Check for success callback
            if let url = navigationAction.request.url?.absoluteString,
               url.contains("payment-success") {
                onSuccess()
            }
            decisionHandler(.allow)
        }
    }
}

#Preview {
    TopUpView()
        .environmentObject(AppState())
}

