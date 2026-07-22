"""NextStepRecommender — extracted from ml_module.py (mechanical split; see ml_base.py)."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from framework.ml.ml_base import (
    MLBackend,
    MLModel,
    ModelType,
    PredictionResult,
    TrainingData,
)


class NextStepRecommender(MLModel):
    """
    Recommend next test steps based on flow history

    Analyzes navigation patterns and suggests likely next actions
    """

    def __init__(self, backend: MLBackend = MLBackend.SKLEARN):
        super().__init__(ModelType.STEP_RECOMMENDER, backend)
        self._transition_history: Dict[str, List[str]] = {}

    def predict(self, features: Dict[str, Any]) -> PredictionResult:
        """
        Predict next likely test step

        Args:
            features: Current context (screen, recent actions, etc.)

        Returns:
            Recommended next step with confidence
        """
        current_screen = features.get("current_screen", "")

        # Use transition history for prediction
        if current_screen in self._transition_history:
            next_screens = self._transition_history[current_screen]
            if next_screens:
                # Most common next screen
                from collections import Counter

                counter = Counter(next_screens)
                most_common = counter.most_common(3)

                prediction = most_common[0][0]
                total = sum(counter.values())
                confidence = most_common[0][1] / total

                alternatives = [(screen, count / total) for screen, count in most_common[1:]]

                return PredictionResult(
                    prediction=prediction,
                    confidence=confidence,
                    alternatives=alternatives,
                    model_version=self.version,
                    metadata={"current_screen": current_screen},
                )

        # Default: suggest exploring new screens
        return PredictionResult(
            prediction="explore_new_screen",
            confidence=0.3,
            alternatives=[],
            model_version=self.version,
            metadata={"reason": "no_history"},
        )

    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train step recommender"""
        # Build transition history
        for features in training_data.features:
            from_screen = features.get("from_screen")
            to_screen = features.get("to_screen")

            if from_screen and to_screen:
                if from_screen not in self._transition_history:
                    self._transition_history[from_screen] = []
                self._transition_history[from_screen].append(to_screen)

        self.is_trained = True

        return {
            "unique_screens": len(self._transition_history),
            "total_transitions": sum(len(v) for v in self._transition_history.values()),
        }

    def save(self, path: Path):
        """Save model"""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(
                {
                    "type": self.model_type.value,
                    "backend": self.backend.value,
                    "version": self.version,
                    "is_trained": self.is_trained,
                    "transition_history": self._transition_history,
                },
                f,
                indent=2,
            )

    def load(self, path: Path):
        """Load model"""
        with open(path, "r") as f:
            data = json.load(f)

        self.version = data["version"]
        self.is_trained = data["is_trained"]
        self._transition_history = data.get("transition_history", {})
