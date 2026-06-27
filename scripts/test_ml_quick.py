#!/usr/bin/env python3
"""
Быстрая проверка ML моделей
"""

import sys

sys.path.insert(0, '/Users/vadimtoptunov/PycharmProjects/mobile_test_recorder')

print("🤖 Testing ML Module...")

try:
    from framework.ml import MLModule, MLBackend

    print("✅ Import successful")

    # Create module
    ml = MLModule(backend=MLBackend.SKLEARN)
    print("✅ MLModule created")

    # Test prediction
    result = ml.predict_selector({'id': 'test', 'type': 'button'})
    print(f"✅ Prediction works: {result.prediction} (confidence: {result.confidence})")

    print("\n✅ ALL TESTS PASSED!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
