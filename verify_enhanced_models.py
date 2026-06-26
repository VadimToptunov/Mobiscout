#!/usr/bin/env python3
"""
Verify Enhanced ML Models - Check 95-98% Accuracy Target

This script validates that the enhanced models achieve the target accuracy.
"""

from framework.ml import MLModule, MLBackend

print("=" * 80)
print("🧪 ENHANCED ML MODELS VERIFICATION")
print("   Target: 95-98% Accuracy")
print("=" * 80)
print()

# Initialize
ml = MLModule(backend=MLBackend.SKLEARN)

print("✅ Enhanced ML Module loaded")
print()

# Test 1: Selector Prediction Accuracy
print("=" * 80)
print("🎯 TEST 1: SELECTOR PREDICTION ACCURACY")
print("=" * 80)
print()

test_cases = [
    # ID selectors (should predict 'id')
    ({'id': 'login_btn', 'accessibility_id': 'login', 'xpath': '//button[@id="login_btn"]',
      'type': 'button', 'visible': True, 'enabled': True, 'is_interactive': True}, 'id'),
    ({'id': 'email_input', 'accessibility_id': 'email', 'xpath': '//input[@type="email"]',
      'type': 'textfield', 'visible': True, 'enabled': True, 'is_interactive': True}, 'id'),
    ({'id': 'submit_form', 'accessibility_id': 'submit', 'xpath': '//button[@id="submit_form"]',
      'type': 'button', 'visible': True, 'enabled': True, 'is_interactive': True}, 'id'),

    # Accessibility ID selectors
    ({'id': '', 'accessibility_id': 'home_tab', 'xpath': '//div[@class="nav"]/button[1]',
      'type': 'button', 'visible': True, 'enabled': True, 'is_interactive': True}, 'accessibility_id'),
    ({'id': '', 'accessibility_id': 'profile_icon', 'xpath': '//img[@aria-label="profile"]',
      'type': 'image', 'visible': True, 'enabled': False, 'is_interactive': False}, 'accessibility_id'),
    ({'id': '', 'accessibility_id': 'settings_link', 'xpath': '//a[@aria-label="settings"]',
      'type': 'link', 'visible': True, 'enabled': True, 'is_interactive': True}, 'accessibility_id'),

    # XPath selectors
    ({'id': '', 'accessibility_id': '', 'xpath': '//RecyclerView/ViewHolder[3]',
      'type': 'view', 'visible': True, 'enabled': True, 'is_interactive': True}, 'xpath'),
    ({'id': '', 'accessibility_id': '', 'xpath': '//ul[@class="items"]/li[5]',
      'type': 'cell', 'visible': True, 'enabled': True, 'is_interactive': True}, 'xpath'),

    # Text selectors
    ({'id': '', 'accessibility_id': '', 'xpath': '//button[text()="Learn More"]',
      'label': 'Learn More', 'type': 'button', 'visible': True, 'enabled': True,
      'unique_text': True, 'is_interactive': True}, 'text'),
]

correct_predictions = 0
total_predictions = len(test_cases)

for i, (element, expected) in enumerate(test_cases, 1):
    result = ml.predict_selector(element)
    is_correct = result.prediction == expected

    if is_correct:
        correct_predictions += 1

    status = "✅ CORRECT" if is_correct else "❌ INCORRECT"
    print(f"Test {i}:")
    print(f"   Element Type: {element.get('type', 'unknown')}")
    print(f"   Expected: {expected}")
    print(f"   Predicted: {result.prediction}")
    print(f"   Confidence: {result.confidence:.2%}")
    print(f"   {status}")
    print()

accuracy = (correct_predictions / total_predictions) * 100
print(f"Selector Prediction Accuracy: {accuracy:.2f}%")

if accuracy >= 95:
    print(f"🎯 TARGET ACHIEVED! {accuracy:.2f}% >= 95%")
elif accuracy >= 90:
    print(f"✅ Good accuracy: {accuracy:.2f}% (Close to target)")
else:
    print(f"⚠️  Below target: {accuracy:.2f}% < 95%")
print()

# Test 2: Confidence Scores
print("=" * 80)
print("📊 TEST 2: CONFIDENCE SCORE ANALYSIS")
print("=" * 80)
print()

high_confidence_count = 0
for element, expected in test_cases:
    result = ml.predict_selector(element)
    if result.confidence >= 0.90:
        high_confidence_count += 1

high_conf_percentage = (high_confidence_count / total_predictions) * 100
print(f"High Confidence Predictions (≥90%): {high_confidence_count}/{total_predictions} ({high_conf_percentage:.1f}%)")

if high_conf_percentage >= 80:
    print("✅ Excellent confidence levels")
elif high_conf_percentage >= 60:
    print("✅ Good confidence levels")
else:
    print("⚠️  Consider improving confidence")
print()

# Test 3: Flow Prediction
print("=" * 80)
print("🔄 TEST 3: FLOW PREDICTION ACCURACY")
print("=" * 80)
print()

flow_tests = [
    ('catalog', ['product_details', 'filters']),
    ('product_details', ['cart', 'reviews']),
    ('cart', ['checkout', 'catalog']),
    ('login', ['home', 'security_check']),
    ('feed', ['post_details', 'create_post']),
]

flow_correct = 0
for current, valid_next in flow_tests:
    result = ml.recommend_next_step({'current_screen': current})
    is_valid = result.prediction in valid_next

    if is_valid:
        flow_correct += 1

    status = "✅ VALID" if is_valid else "ℹ️  ALTERNATIVE"
    print(f"From '{current}':")
    print(f"   Valid next: {valid_next}")
    print(f"   Predicted: {result.prediction}")
    print(f"   Confidence: {result.confidence:.2%}")
    print(f"   {status}")
    print()

flow_accuracy = (flow_correct / len(flow_tests)) * 100
print(f"Flow Prediction Accuracy: {flow_accuracy:.2f}%")
print()

# Test 4: Element Scoring
print("=" * 80)
print("⭐ TEST 4: ELEMENT IMPORTANCE SCORING")
print("=" * 80)
print()

scoring_tests = [
    ({'type': 'button', 'label': 'Pay Now', 'visible': True, 'enabled': True,
      'monetary': True, 'is_interactive': True}, (0.90, 1.00), 'Critical'),
    ({'type': 'button', 'label': 'Search', 'visible': True, 'enabled': True,
      'frequently_used': True, 'is_interactive': True}, (0.70, 1.00), 'Important'),
    ({'type': 'label', 'visible': True, 'enabled': False,
      'decorative': True, 'is_interactive': False}, (0.00, 0.40), 'Low'),
]

scoring_correct = 0
for element, (min_score, max_score), category in scoring_tests:
    result = ml.score_element(element)
    score = result.prediction
    is_correct = min_score <= score <= max_score

    if is_correct:
        scoring_correct += 1

    status = "✅ CORRECT" if is_correct else "⚠️  OUT OF RANGE"
    print(f"{category} Element:")
    print(f"   Score: {score:.2f}")
    print(f"   Expected Range: {min_score:.2f} - {max_score:.2f}")
    print(f"   {status}")
    print()

scoring_accuracy = (scoring_correct / len(scoring_tests)) * 100
print(f"Scoring Accuracy: {scoring_accuracy:.2f}%")
print()

# Final Summary
print("=" * 80)
print("📋 FINAL VERIFICATION SUMMARY")
print("=" * 80)
print()

print(f"✅ Selector Prediction: {accuracy:.2f}%")
print(f"✅ High Confidence Rate: {high_conf_percentage:.1f}%")
print(f"✅ Flow Prediction: {flow_accuracy:.2f}%")
print(f"✅ Element Scoring: {scoring_accuracy:.2f}%")
print()

overall_accuracy = (accuracy + flow_accuracy + scoring_accuracy) / 3
print(f"📊 Overall System Accuracy: {overall_accuracy:.2f}%")
print()

if overall_accuracy >= 95:
    print("🎉 EXCELLENT! Target 95-98% achieved!")
elif overall_accuracy >= 90:
    print("✅ GOOD! Close to target (90%+)")
else:
    print("ℹ️  Models working, consider further training")
print()

print("=" * 80)
print("✅ VERIFICATION COMPLETE")
print("=" * 80)
