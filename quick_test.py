#!/usr/bin/env python3
"""Quick test script"""
import sys

print("Python version:", sys.version)

try:
    from framework.ml import MLModule

    print("✅ MLModule imported successfully")

    module = MLModule()
    print("✅ MLModule instantiated successfully")

    result = module.predict_selector({'id': 'test'})
    print(f"✅ Prediction works: {result.prediction}")

    print("\n✅ ALL CHECKS PASSED")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
