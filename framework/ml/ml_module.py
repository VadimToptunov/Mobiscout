"""
STEP 5: ML Module - AI-powered selector prediction and test recommendations

Features:
- Selector prediction using ML models
- Next-step recommendations
- Element importance scoring
- Offline inference support
- Online training (ENTERPRISE feature)
- Model versioning and updates
- Configurable ML backends (scikit-learn, TensorFlow, PyTorch)

This module is designed to be flexible and support multiple ML backends
without hardcoding specific implementations.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from framework.licensing.validator import check_feature


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
        pass

    @abstractmethod
    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """
        Train model (ENTERPRISE feature)

        Args:
            training_data: Training dataset

        Returns:
            Training metrics
        """
        pass

    @abstractmethod
    def save(self, path: Path):
        """Save model to disk"""
        pass

    @abstractmethod
    def load(self, path: Path):
        """Load model from disk"""
        pass

    def get_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            'model_type': self.model_type.value,
            'backend': self.backend.value,
            'version': self.version,
            'is_trained': self.is_trained
        }


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
            'has_id', 'has_accessibility_id', 'has_xpath', 'has_text',
            'element_type', 'is_visible', 'is_enabled', 'depth_in_tree',
            'siblings_count', 'has_unique_text', 'position_stable'
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
                metadata={'error': 'invalid_features'}
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
            metadata={'features': features, 'backend': self.backend.value}
        )

    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train selector prediction model (ENTERPRISE feature)"""
        if not check_feature('ml_healing'):
            raise PermissionError("ML training requires ENTERPRISE license")

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
            'type': self.model_type.value,
            'backend': self.backend.value,
            'version': self.version,
            'is_trained': self.is_trained,
            'config': self.config,
            'feature_names': self._feature_names
        }

        # Save model weights if trained
        if self._model is not None and self.backend == MLBackend.SKLEARN:
            model_path = path.with_suffix('.pkl')
            try:
                import joblib
                joblib.dump(self._model, model_path)
            except ImportError:
                # Fallback to pickle
                import pickle
                with open(model_path, 'wb') as model_file:
                    pickle.dump(self._model, model_file)

        # Save metadata
        with open(path.with_suffix('.json'), 'w') as f:
            json.dump(model_data, f, indent=2)

    def load(self, path: Path):
        """Load model from disk"""
        # Load metadata
        with open(path.with_suffix('.json'), 'r') as f:
            model_data = json.load(f)

        self.version = model_data['version']
        self.is_trained = model_data['is_trained']
        self.config = model_data.get('config', {})
        self._feature_names = model_data.get('feature_names', self._feature_names)

        # Load model weights if exists
        pkl_path = path.with_suffix('.pkl')
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
                    UserWarning
                )
                with open(pkl_path, 'rb') as f:
                    self._model = pickle.load(f)

    def _extract_features(self, features: Dict[str, Any]) -> List[float]:
        """Extract numerical feature vector"""
        return [
            1.0 if features.get('id') else 0.0,
            1.0 if features.get('accessibility_id') else 0.0,
            1.0 if features.get('xpath') else 0.0,
            1.0 if features.get('label') else 0.0,
            self._encode_element_type(features.get('type', 'unknown')),
            1.0 if features.get('visible', True) else 0.0,
            1.0 if features.get('enabled', True) else 0.0,
            float(features.get('depth', 0)),
            float(features.get('siblings_count', 0)),
            1.0 if features.get('unique_text', False) else 0.0,
            float(features.get('position_stability', 0.5))
        ]

    def _encode_element_type(self, elem_type: str) -> float:
        """Encode element type as numerical value"""
        type_map = {
            'button': 1.0, 'textfield': 0.8, 'label': 0.6,
            'image': 0.4, 'view': 0.2, 'unknown': 0.0
        }
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
        if features.get('id'):
            return 'id', 1.0
        elif features.get('accessibility_id'):
            return 'accessibility_id', 0.8
        elif features.get('xpath'):
            return 'xpath', 0.6
        elif features.get('label'):
            return 'text', 0.4
        else:
            return 'xpath', 0.3

    def _generate_alternatives(self, features: Dict[str, Any], primary: str) -> List[Tuple[str, float]]:
        """Generate alternative selector strategies"""
        alternatives = []

        selectors = [
            ('id', 1.0 if features.get('id') else 0.0),
            ('accessibility_id', 0.8 if features.get('accessibility_id') else 0.0),
            ('xpath', 0.6 if features.get('xpath') else 0.0),
            ('text', 0.4 if features.get('label') else 0.0)
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
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # Train model
            self._model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
            self._model.fit(X_train, y_train)

            # Evaluate
            y_pred = self._model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)

            self.is_trained = True

            return {
                'accuracy': accuracy,
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'backend': 'sklearn'
            }
        except ImportError:
            raise ImportError("scikit-learn not installed. Run: pip install scikit-learn")

    def _train_tensorflow(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train using TensorFlow (placeholder)"""
        raise NotImplementedError("TensorFlow training not yet implemented")

    def _train_pytorch(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train using PyTorch (placeholder)"""
        raise NotImplementedError("PyTorch training not yet implemented")


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
        current_screen = features.get('current_screen', '')
        recent_actions = features.get('recent_actions', [])

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
                    metadata={'current_screen': current_screen}
                )

        # Default: suggest exploring new screens
        return PredictionResult(
            prediction="explore_new_screen",
            confidence=0.3,
            alternatives=[],
            model_version=self.version,
            metadata={'reason': 'no_history'}
        )

    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train step recommender (ENTERPRISE feature)"""
        if not check_feature('ml_healing'):
            raise PermissionError("ML training requires ENTERPRISE license")

        # Build transition history
        for features in training_data.features:
            from_screen = features.get('from_screen')
            to_screen = features.get('to_screen')

            if from_screen and to_screen:
                if from_screen not in self._transition_history:
                    self._transition_history[from_screen] = []
                self._transition_history[from_screen].append(to_screen)

        self.is_trained = True

        return {
            'unique_screens': len(self._transition_history),
            'total_transitions': sum(len(v) for v in self._transition_history.values())
        }

    def save(self, path: Path):
        """Save model"""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w') as f:
            json.dump({
                'type': self.model_type.value,
                'backend': self.backend.value,
                'version': self.version,
                'is_trained': self.is_trained,
                'transition_history': self._transition_history
            }, f, indent=2)

    def load(self, path: Path):
        """Load model"""
        with open(path, 'r') as f:
            data = json.load(f)

        self.version = data['version']
        self.is_trained = data['is_trained']
        self._transition_history = data.get('transition_history', {})


class ElementScorer(MLModel):
    """
    Score UI elements by importance for testing

    Helps prioritize which elements to test first
    """

    def __init__(self, backend: MLBackend = MLBackend.SKLEARN):
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
        if features.get('type') in ['button', 'textfield', 'link']:
            score += 0.3

        # Visible and enabled elements are important
        if features.get('visible') and features.get('enabled'):
            score += 0.2

        # Elements with clear labels are important
        if features.get('label'):
            score += 0.2

        # Elements involved in navigation are important
        if features.get('navigates', False):
            score += 0.3

        # Normalize score
        score = min(1.0, score)

        return PredictionResult(
            prediction=score,
            confidence=0.8,
            alternatives=[],
            model_version=self.version,
            metadata={'element_type': features.get('type')}
        )

    def train(self, training_data: TrainingData) -> Dict[str, Any]:
        """Train element scorer (ENTERPRISE feature)"""
        if not check_feature('ml_healing'):
            raise PermissionError("ML training requires ENTERPRISE license")

        self.is_trained = True
        return {'samples': len(training_data.features)}

    def save(self, path: Path):
        """Save model"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.get_info(), f, indent=2)

    def load(self, path: Path):
        """Load model"""
        with open(path, 'r') as f:
            data = json.load(f)
        self.version = data['version']
        self.is_trained = data['is_trained']


class MLModule:
    """
    STEP 5: ML Module - Main interface

    Manages ML models and provides unified prediction interface
    """

    def __init__(self, backend: MLBackend = MLBackend.SKLEARN, models_dir: Optional[Path] = None):
        self.backend = backend
        self.models_dir = models_dir or Path.home() / '.observe' / 'models'
        self.models: Dict[ModelType, MLModel] = {}

        # Initialize models
        self._initialize_models()

    def _initialize_models(self):
        """Initialize ML models"""
        self.models[ModelType.SELECTOR_PREDICTOR] = SelectorPredictor(self.backend)
        self.models[ModelType.STEP_RECOMMENDER] = NextStepRecommender(self.backend)
        self.models[ModelType.ELEMENT_SCORER] = ElementScorer(self.backend)

        # Try to load pre-trained models
        self._load_models()

    def _load_models(self):
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
        Train ML model (ENTERPRISE feature)

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
        return {
            model_type.value: model.get_info()
            for model_type, model in self.models.items()
        }
