package com.findemo.ui.topup

import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CreditCard
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.mobiscout.sdk.MobiscoutSDK

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TopUpScreen(
    onNavigateBack: () -> Unit,
    onTopUpSuccess: () -> Unit,
    modifier: Modifier = Modifier
) {
    var currentStep by remember { mutableStateOf(TopUpStep.AMOUNT_INPUT) }
    var amount by remember { mutableStateOf("") }
    var selectedCard by remember { mutableStateOf("**** 1234") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Top Up") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testTag("back_button")
                    ) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { paddingValues ->
        Box(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            when (currentStep) {
                TopUpStep.AMOUNT_INPUT -> {
                    AmountInputStep(
                        amount = amount,
                        onAmountChange = { amount = it },
                        selectedCard = selectedCard,
                        onCardSelect = { selectedCard = it },
                        onContinue = {
                            if (amount.isNotBlank()) {
                                currentStep = TopUpStep.PAYMENT_WEBVIEW
                            }
                        }
                    )
                }
                TopUpStep.PAYMENT_WEBVIEW -> {
                    PaymentWebViewStep(
                        amount = amount,
                        onPaymentSuccess = {
                            currentStep = TopUpStep.SUCCESS
                        },
                        onPaymentCancel = {
                            currentStep = TopUpStep.AMOUNT_INPUT
                        }
                    )
                }
                TopUpStep.SUCCESS -> {
                    SuccessStep(
                        amount = amount,
                        onDone = onTopUpSuccess
                    )
                }
            }
        }
    }
}

@Composable
private fun AmountInputStep(
    amount: String,
    onAmountChange: (String) -> Unit,
    selectedCard: String,
    onCardSelect: (String) -> Unit,
    onContinue: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .testTag("amount_input_step"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.CreditCard,
            contentDescription = null,
            modifier = Modifier.size(80.dp),
            tint = MaterialTheme.colorScheme.primary
        )

        Spacer(modifier = Modifier.height(32.dp))

        Text(
            text = "How much would you like to add?",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold
        )

        Spacer(modifier = Modifier.height(32.dp))

        OutlinedTextField(
            value = amount,
            onValueChange = onAmountChange,
            label = { Text("Amount") },
            placeholder = { Text("0.00") },
            prefix = { Text("$") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier
                .fillMaxWidth()
                .testTag("amount_input"),
            singleLine = true
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Card selection
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("card_selector"),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer
            )
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.CreditCard,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSecondaryContainer
                )
                Spacer(modifier = Modifier.width(16.dp))
                Column {
                    Text(
                        text = "Card ending in",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                    )
                    Text(
                        text = selectedCard,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSecondaryContainer
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(32.dp))

        Button(
            onClick = onContinue,
            enabled = amount.isNotBlank() && amount.toDoubleOrNull() != null && amount.toDouble() > 0,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp)
                .testTag("continue_button")
        ) {
            Text("Continue to Payment")
        }
    }
}

@Composable
private fun PaymentWebViewStep(
    amount: String,
    onPaymentSuccess: () -> Unit,
    onPaymentCancel: () -> Unit
) {
    var isLoading by remember { mutableStateOf(true) }
    
    // Remember the WebView instance across recompositions
    // This prevents the factory from creating multiple WebViews
    val webView = remember {
        mutableStateOf<WebView?>(null)
    }

    // Cleanup on disposal - guaranteed to run once with correct WebView reference
    DisposableEffect(Unit) {
        onDispose {
            webView.value?.let { wv ->
                MobiscoutSDK.stopObservingWebView(wv)
            }
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .testTag("payment_webview_step")
    ) {
        // Mock payment gateway WebView
        AndroidView(
            factory = { context ->
                // Factory lambda is called ONCE per remember block lifetime
                // This ensures we only create and register one WebView
                WebView(context).apply {
                    // Set WebViewClient FIRST before storing reference
                    webViewClient = object : WebViewClient() {
                        override fun onPageFinished(view: WebView?, url: String?) {
                            isLoading = false
                            
                            // Simulate payment confirmation detection
                            if (url?.contains("success") == true) {
                                onPaymentSuccess()
                            }
                        }
                    }
                    
                    // Store reference for cleanup
                    webView.value = this
                    
                    // Register for observation immediately after creation
                    // This matches iOS pattern: register during view creation
                    // Called ONCE per WebView instance (not on every recomposition)
                    MobiscoutSDK.observeWebView(this, "TopUpPaymentScreen")
                    
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    
                    // Load mock payment page
                    loadDataWithBaseURL(
                        null,
                        getMockPaymentHTML(amount),
                        "text/html",
                        "UTF-8",
                        null
                    )
                }
            },
            update = { view ->
                // Update block is called on recomposition
                // We don't need to do anything here as the WebView is stable
                // This explicitly documents that recomposition doesn't recreate WebView
            },
            modifier = Modifier
                .fillMaxSize()
                .testTag("payment_webview")
        )

        if (isLoading) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        }

        // Cancel button overlay
        TextButton(
            onClick = onPaymentCancel,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(16.dp)
                .testTag("cancel_payment_button")
        ) {
            Text("Cancel")
        }
    }
}

@Composable
private fun SuccessStep(
    amount: String,
    onDone: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .testTag("success_step"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.CreditCard,
            contentDescription = null,
            modifier = Modifier.size(80.dp),
            tint = MaterialTheme.colorScheme.primary
        )

        Spacer(modifier = Modifier.height(32.dp))

        Text(
            text = "Top-up Successful!",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "$$amount has been added to your account",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
        )

        Spacer(modifier = Modifier.height(48.dp))

        Button(
            onClick = onDone,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp)
                .testTag("done_button")
        ) {
            Text("Done")
        }
    }
}

private enum class TopUpStep {
    AMOUNT_INPUT,
    PAYMENT_WEBVIEW,
    SUCCESS
}

/**
 * Mock HTML for payment gateway
 * In real app, this would be actual payment provider's page
 */
private fun getMockPaymentHTML(amount: String): String {
    return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    padding: 20px;
                    background: #f5f5f5;
                    margin: 0;
                }
                .container {
                    background: white;
                    border-radius: 12px;
                    padding: 24px;
                    max-width: 400px;
                    margin: 40px auto;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                h2 {
                    color: #1976d2;
                    margin-top: 0;
                }
                .amount {
                    font-size: 32px;
                    font-weight: bold;
                    color: #333;
                    margin: 20px 0;
                }
                .button {
                    background: #1976d2;
                    color: white;
                    border: none;
                    padding: 16px 32px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    width: 100%;
                    margin-top: 20px;
                    cursor: pointer;
                }
                .button:active {
                    background: #1565c0;
                }
                .info {
                    background: #e3f2fd;
                    padding: 12px;
                    border-radius: 8px;
                    margin: 16px 0;
                    color: #1976d2;
                    font-size: 14px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h2> Secure Payment</h2>
                <p>Confirm your top-up amount:</p>
                <div class="amount">$$amount</div>
                <div class="info">
                    ℹ This is a mock payment gateway for demo purposes
                </div>
                <button class="button" onclick="confirmPayment()" id="confirmBtn">
                    Confirm Payment
                </button>
            </div>
            
            <script>
                function confirmPayment() {
                    document.getElementById('confirmBtn').textContent = 'Processing...';
                    document.getElementById('confirmBtn').disabled = true;
                    
                    // Simulate payment processing
                    setTimeout(function() {
                        // Redirect to success URL (triggers WebViewClient)
                        window.location.href = 'https://payment.success?amount=$amount';
                    }, 1500);
                }
            </script>
        </body>
        </html>
    """.trimIndent()
}
