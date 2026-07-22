"""
STEP 5: ML Module - ML-based selector prediction and test recommendations

This module grew past 640 lines, so the value types + model base
(:mod:`framework.ml.ml_base`) and each concrete model
(:mod:`~framework.ml.selector_predictor`,
:mod:`~framework.ml.next_step_recommender`,
:mod:`~framework.ml.element_scorer`) now live in their own modules. This module
keeps the ``MLModule`` orchestrator and re-exports the public names so existing
imports (``from framework.ml.ml_module import ...``) keep working unchanged.

Features:
- Selector prediction using ML models
- Next-step recommendations
- Element importance scoring
- Offline inference support / online training
- Model versioning and updates
- Configurable ML backends (scikit-learn, TensorFlow, PyTorch)
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from framework.ml.element_scorer import ElementScorer
from framework.ml.ml_base import (
    MLBackend,
    MLModel,
    ModelType,
    PredictionResult,
    TrainingData,
)
from framework.ml.next_step_recommender import NextStepRecommender
from framework.ml.selector_predictor import SelectorPredictor

__all__ = [
    "MLBackend",
    "ModelType",
    "PredictionResult",
    "TrainingData",
    "MLModel",
    "SelectorPredictor",
    "NextStepRecommender",
    "ElementScorer",
    "MLModule",
]


class MLModule:
    """
    STEP 5: ML Module - Main interface

    Manages ML models and provides unified prediction interface
    """

    def __init__(self, backend: MLBackend = MLBackend.SKLEARN, models_dir: Optional[Path] = None) -> None:
        self.backend = backend
        self.models_dir = models_dir or Path.home() / ".mobiscout" / "models"
        self.models: Dict[ModelType, MLModel] = {}

        # Initialize models
        self._initialize_models()

    def _initialize_models(self) -> None:
        """Initialize ML models"""
        self.models[ModelType.SELECTOR_PREDICTOR] = SelectorPredictor(self.backend)
        self.models[ModelType.STEP_RECOMMENDER] = NextStepRecommender(self.backend)
        self.models[ModelType.ELEMENT_SCORER] = ElementScorer(self.backend)

        # Try to load pre-trained models
        self._load_models()

    def _load_models(self) -> None:
        """Load pre-trained models if available"""
        if not self.models_dir.exists():
            return

        for model_type, model in self.models.items():
            model_path = self.models_dir / f"{model_type.value}.json"
            if model_path.exists():
                try:
                    model.load(model_path)
                except (OSError, json.JSONDecodeError, KeyError, ValueError, ModuleNotFoundError):
                    pass  # Use untrained model

    def predict_selector(self, element_features: Dict[str, Any]) -> PredictionResult:
        """
        Predict best selector for element

        Args:
            element_features: Element properties

        Returns:
            Selector prediction with confidence
        """
        model = self.models[ModelType.SELECTOR_PREDICTOR]
        return model.predict(element_features)

    def recommend_next_step(self, context: Dict[str, Any]) -> PredictionResult:
        """
        Recommend next test step

        Args:
            context: Current test context

        Returns:
            Step recommendation with confidence
        """
        model = self.models[ModelType.STEP_RECOMMENDER]
        return model.predict(context)

    def score_element(self, element_features: Dict[str, Any]) -> PredictionResult:
        """
        Score element importance

        Args:
            element_features: Element properties

        Returns:
            Importance score
        """
        model = self.models[ModelType.ELEMENT_SCORER]
        return model.predict(element_features)

    def train_model(self, model_type: ModelType, training_data: TrainingData) -> Dict[str, Any]:
        """
        Train ML model

        Args:
            model_type: Type of model to train
            training_data: Training dataset

        Returns:
            Training metrics
        """
        if model_type not in self.models:
            raise ValueError(f"Unknown model type: {model_type}")

        model = self.models[model_type]
        metrics = model.train(training_data)

        # Save trained model
        self.models_dir.mkdir(parents=True, exist_ok=True)
        model_path = self.models_dir / f"{model_type.value}.json"
        model.save(model_path)

        return metrics

    def get_models_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all models"""
        return {model_type.value: model.get_info() for model_type, model in self.models.items()}
