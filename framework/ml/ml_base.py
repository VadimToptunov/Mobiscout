"""Shared ML value types and the model base class.

Extracted from ml_module.py during decomposition: the backend/model enums, the
prediction/training dataclasses, and the abstract MLModel that every concrete
model (selector predictor, step recommender, element scorer) inherits.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Tuple


class MLBackend(Enum):
    """Supported ML backends"""

    SKLEARN = "sklearn"
    TENSORFLOW = "tensorflow"
    PYTORCH = "pytorch"
    ONNX = "onnx"
    CUSTOM = "custom"


class ModelType(Enum):
    """ML model types"""

    SELECTOR_PREDICTOR = "selector_predictor"
    STEP_RECOMMENDER = "step_recommender"
    ELEMENT_SCORER = "element_scorer"
    EDGE_CASE_DETECTOR = "edge_case_detector"


@dataclass
class PredictionResult:
    """ML prediction result"""

    prediction: Any
    confidence: float  # 0.0 - 1.0
    alternatives: List[Tuple[Any, float]]  # [(prediction, confidence), ...]
    model_version: str
    metadata: Dict[str, Any]


@dataclass
class TrainingData:
    """Training data for ML models"""

    features: List[Dict[str, Any]]
    labels: List[Any]
    metadata: Dict[str, Any]


class MLModel(ABC):
    """
    Abstract base class for ML models

    Provides interface for prediction, training, and serialization
    """

    def __init__(self, model_type: ModelType, backend: MLBackend):
        self.model_type = model_type
        self.backend = backend
        self.version = "1.0.0"
        self.is_trained = False

    @abstractmethod
    def predict(self, features: Dict[str, Any]) -> PredictionResult:
        """
        Make prediction

        Args:
            features: Feature dictionary

        Returns:
            Prediction result with confidence
        """

    @abstractmethod
    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """
        Train model

        Args:
            training_data: Training dataset

        Returns:
            Training metrics
        """

    @abstractmethod
    def save(self, path: Path):
        """Save model to disk"""

    @abstractmethod
    def load(self, path: Path):
        """Load model from disk"""

    def get_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "model_type": self.model_type.value,
            "backend": self.backend.value,
            "version": self.version,
            "is_trained": self.is_trained,
        }
