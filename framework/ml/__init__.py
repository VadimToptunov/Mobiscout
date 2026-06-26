"""
Machine Learning module for intelligent element classification and prediction.

This module provides AI/ML capabilities for:
- Element type classification
- Visual element detection
- Selector healing
- Flow pattern recognition
- Analytics dashboards
- Training data generation
- Universal pre-trained model

STEP 5 additions:
- ML-powered selector prediction
- Next-step recommendations
- Element importance scoring
- Flexible ML backend support (sklearn, TensorFlow, PyTorch)
"""

# Legacy imports (optional - may fail if dependencies missing)
try:
    from framework.ml.element_classifier import ElementClassifier
    from framework.ml.visual_detector import VisualDetector
    from framework.ml.selector_healer import SelectorHealer
    from framework.ml.pattern_recognizer import PatternRecognizer
    from framework.ml.analytics_dashboard import AnalyticsDashboard
    from framework.ml.training_data_generator import TrainingDataGenerator
    from framework.ml.universal_model import UniversalModelBuilder, create_universal_pretrained_model
except ImportError:
    # Legacy modules not available (missing dependencies)
    pass

# STEP 5: New ML module (core - no external dependencies)
from framework.ml.ml_module import (
    MLBackend,
    ModelType,
    PredictionResult,
    TrainingData,
    MLModel,
    SelectorPredictor,
    NextStepRecommender,
    ElementScorer,
    MLModule
)

__all__ = [
    'ElementClassifier',
    'VisualDetector',
    'SelectorHealer',
    'PatternRecognizer',
    'AnalyticsDashboard',
    'TrainingDataGenerator',
    'UniversalModelBuilder',
    'create_universal_pretrained_model',
]
