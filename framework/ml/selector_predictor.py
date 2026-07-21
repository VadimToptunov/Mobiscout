"""SelectorPredictor — extracted from ml_module.py (mechanical split; see ml_base.py)."""

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


class SelectorPredictor(MLModel):
    """
    Predict best selector strategy for UI elements

    Uses element properties, context, and historical data to predict
    which selector will be most stable.
    """

    def __init__(self, backend: MLBackend = MLBackend.SKLEARN, config: Optional[Dict[str, Any]] = None):
        super().__init__(ModelType.SELECTOR_PREDICTOR, backend)
        self.config = config or {}
        self._model = None
        self._feature_names = [
            "has_id",
            "has_accessibility_id",
            "has_xpath",
            "has_text",
            "element_type",
            "is_visible",
            "is_enabled",
            "depth_in_tree",
            "siblings_count",
            "has_unique_text",
            "position_stable",
        ]

    def predict(self, features: Dict[str, Any]) -> PredictionResult:
        """
        Predict best selector for element

        Args:
            features: Element features (id, accessibility_id, type, etc.)

        Returns:
            Prediction with confidence score
        """
        # Handle None or invalid features
        if not features or not isinstance(features, dict):
            return PredictionResult(
                prediction="xpath",
                confidence=0.0,
                alternatives=[],
                model_version=self.version,
                metadata={"error": "invalid_features"},
            )

        # Extract and normalize features
        feature_vector = self._extract_features(features)

        # If model is trained, use it
        if self.is_trained and self._model is not None:
            prediction, confidence = self._predict_with_model(feature_vector)
        else:
            # Fallback to heuristic-based prediction
            prediction, confidence = self._heuristic_prediction(features)

        # Generate alternatives
        alternatives = self._generate_alternatives(features, prediction)

        return PredictionResult(
            prediction=prediction,
            confidence=confidence,
            alternatives=alternatives,
            model_version=self.version,
            metadata={"features": features, "backend": self.backend.value},
        )

    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train selector prediction model"""
        if self.backend == MLBackend.SKLEARN:
            return self._train_sklearn(training_data)
        elif self.backend == MLBackend.TENSORFLOW:
            return self._train_tensorflow(training_data)
        elif self.backend == MLBackend.PYTORCH:
            return self._train_pytorch(training_data)
        else:
            raise NotImplementedError(f"Training not implemented for {self.backend}")

    def save(self, path: Path):
        """Save model to disk"""
        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "type": self.model_type.value,
            "backend": self.backend.value,
            "version": self.version,
            "is_trained": self.is_trained,
            "config": self.config,
            "feature_names": self._feature_names,
        }

        # Save model weights if trained
        if self._model is not None and self.backend == MLBackend.SKLEARN:
            model_path = path.with_suffix(".pkl")
            try:
                import joblib

                joblib.dump(self._model, model_path)
            except ImportError:
                # Fallback to pickle
                import pickle

                with open(model_path, "wb") as model_file:
                    pickle.dump(self._model, model_file)

        # Save metadata
        with open(path.with_suffix(".json"), "w") as f:
            json.dump(model_data, f, indent=2)

    def load(self, path: Path):
        """Load model from disk"""
        # Load metadata
        with open(path.with_suffix(".json"), "r") as f:
            model_data = json.load(f)

        self.version = model_data["version"]
        self.is_trained = model_data["is_trained"]
        self.config = model_data.get("config", {})
        self._feature_names = model_data.get("feature_names", self._feature_names)

        # Load model weights if exists
        pkl_path = path.with_suffix(".pkl")
        if pkl_path.exists() and self.backend == MLBackend.SKLEARN:
            # Use joblib for safer deserialization (still requires trusted source)
            # WARNING: Only load models from trusted sources
            try:
                import joblib

                self._model = joblib.load(pkl_path)
            except ImportError:
                # Fallback to pickle with warning
                import pickle
                import warnings

                warnings.warn(
                    "Loading model with pickle. For better security, install joblib. "
                    "Only load models from trusted sources.",
                    UserWarning,
                )
                with open(pkl_path, "rb") as f:
                    self._model = pickle.load(f)

    def _extract_features(self, features: Dict[str, Any]) -> List[float]:
        """Extract numerical feature vector"""
        return [
            1.0 if features.get("id") else 0.0,
            1.0 if features.get("accessibility_id") else 0.0,
            1.0 if features.get("xpath") else 0.0,
            1.0 if features.get("label") else 0.0,
            self._encode_element_type(features.get("type", "unknown")),
            1.0 if features.get("visible", True) else 0.0,
            1.0 if features.get("enabled", True) else 0.0,
            float(features.get("depth", 0)),
            float(features.get("siblings_count", 0)),
            1.0 if features.get("unique_text", False) else 0.0,
            float(features.get("position_stability", 0.5)),
        ]

    def _encode_element_type(self, elem_type: str) -> float:
        """Encode element type as numerical value"""
        type_map = {"button": 1.0, "textfield": 0.8, "label": 0.6, "image": 0.4, "view": 0.2, "unknown": 0.0}
        return type_map.get(elem_type.lower(), 0.0)

    def _predict_with_model(self, feature_vector: List[float]) -> Tuple[str, float]:
        """Use trained model for prediction"""
        try:
            if self.backend == MLBackend.SKLEARN:
                import numpy as np

                X = np.array([feature_vector])
                prediction = self._model.predict(X)[0]
                proba = self._model.predict_proba(X)[0]
                confidence = float(max(proba))
                return prediction, confidence
        except (ValueError, TypeError, AttributeError, ImportError):
            # Fallback if prediction fails
            pass

        return "id", 0.5

    def _heuristic_prediction(self, features: Dict[str, Any]) -> Tuple[str, float]:
        """Heuristic-based prediction without ML"""
        if features.get("id"):
            return "id", 1.0
        elif features.get("accessibility_id"):
            return "accessibility_id", 0.8
        elif features.get("xpath"):
            return "xpath", 0.6
        elif features.get("label"):
            return "text", 0.4
        else:
            return "xpath", 0.3

    def _generate_alternatives(self, features: Dict[str, Any], primary: str) -> List[Tuple[str, float]]:
        """Generate alternative selector strategies"""
        alternatives = []

        selectors = [
            ("id", 1.0 if features.get("id") else 0.0),
            ("accessibility_id", 0.8 if features.get("accessibility_id") else 0.0),
            ("xpath", 0.6 if features.get("xpath") else 0.0),
            ("text", 0.4 if features.get("label") else 0.0),
        ]

        # Remove primary and sort by confidence
        alternatives = [(s, c) for s, c in selectors if s != primary and c > 0]
        alternatives.sort(key=lambda x: x[1], reverse=True)

        return alternatives[:3]  # Top 3 alternatives

    def _train_sklearn(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train using scikit-learn"""
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, classification_report
            import numpy as np

            # Prepare data
            X = np.array([self._extract_features(f) for f in training_data.features])
            y = np.array(training_data.labels)

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

            # Train model
            self._model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
            self._model.fit(X_train, y_train)

            # Evaluate
            y_pred = self._model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)

            self.is_trained = True

            return {
                "accuracy": accuracy,
                "train_samples": len(X_train),
                "test_samples": len(X_test),
                "backend": "sklearn",
            }
        except ImportError:
            raise ImportError("scikit-learn not installed. Run: pip install scikit-learn")

    def _train_tensorflow(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train using TensorFlow (placeholder)"""
        raise NotImplementedError("TensorFlow training not yet implemented")

    def _train_pytorch(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train using PyTorch (placeholder)"""
        raise NotImplementedError("PyTorch training not yet implemented")
