"""
Machine Learning module for element classification and related capabilities.

Provides:
- Element type classification (the live crawl-time typing path)
- Visual element detection (OpenCV/OCR)
- Flow pattern recognition
- Training data generation (synthetic + real, incl. the RICO importer)
- Universal pre-trained model

Selector-healing helpers (stateless strategies, fallback promotion, healing
types) live in ``framework.healing`` — they belong with the healing package, not
here. The former ``ml_module`` / ``selector_predictor`` / ``element_scorer`` /
``next_step_recommender`` stubs (unimplemented TF/PyTorch backends, mock data)
were removed.
"""

# Optional imports — the analyzer extras (sklearn, opencv, …) may be absent.
try:
    from framework.ml.element_classifier import ElementClassifier
    from framework.ml.visual_detector import VisualDetector
    from framework.ml.pattern_recognizer import PatternRecognizer
    from framework.ml.training_data_generator import TrainingDataGenerator
    from framework.ml.universal_model import UniversalModelBuilder, create_universal_pretrained_model
except ImportError:
    pass

__all__ = [
    "ElementClassifier",
    "VisualDetector",
    "PatternRecognizer",
    "TrainingDataGenerator",
    "UniversalModelBuilder",
    "create_universal_pretrained_model",
]
