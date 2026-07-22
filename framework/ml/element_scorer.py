"""ElementScorer — extracted from ml_module.py (mechanical split; see ml_base.py)."""

import json
from pathlib import Path
from typing import Any, Dict

from framework.ml.ml_base import (
    MLBackend,
    MLModel,
    ModelType,
    PredictionResult,
    TrainingData,
)


class ElementScorer(MLModel):
    """
    Score UI elements by importance for testing

    Helps prioritize which elements to test first
    """

    def __init__(self, backend: MLBackend = MLBackend.SKLEARN) -> None:
        super().__init__(ModelType.ELEMENT_SCORER, backend)

    def predict(self, features: Dict[str, Any]) -> PredictionResult:
        """
        Score element importance

        Args:
            features: Element properties

        Returns:
            Importance score (0.0 - 1.0)
        """
        score = 0.0

        # Interactive elements are important
        if features.get("type") in ["button", "textfield", "link"]:
            score += 0.3

        # Visible and enabled elements are important
        if features.get("visible") and features.get("enabled"):
            score += 0.2

        # Elements with clear labels are important
        if features.get("label"):
            score += 0.2

        # Elements involved in navigation are important
        if features.get("navigates", False):
            score += 0.3

        # Normalize score
        score = min(1.0, score)

        return PredictionResult(
            prediction=score,
            confidence=0.8,
            alternatives=[],
            model_version=self.version,
            metadata={"element_type": features.get("type")},
        )

    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train element scorer"""
        self.is_trained = True
        return {"samples": len(training_data.features)}

    def save(self, path: Path) -> None:
        """Save model"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.get_info(), f, indent=2)

    def load(self, path: Path) -> None:
        """Load model"""
        with open(path, "r") as f:
            data = json.load(f)
        self.version = data["version"]
        self.is_trained = data["is_trained"]
