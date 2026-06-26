"""
ML-based element classifier for automatic UI element type detection.

Uses scikit-learn Random Forest classifier trained on UI hierarchy features
to predict element types with confidence scores.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import joblib
# import numpy  # Unused
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder

from framework.model.app_model import ElementType

logger = logging.getLogger(__name__)


class ElementClassifier:
    """
    ML-based classifier for UI element types.

    Features extracted from UI hierarchy:
    - Element attributes (clickable, focusable, enabled)
    - Text properties (has text, text length)
    - Hierarchy properties (depth, children count)
    - Size properties (width, height, aspect ratio)
    - Type hints from class names

    Target: ElementType enum (BUTTON, INPUT, TEXT, LIST, etc.)
    """

    def __init__(self, model_path: Optional[Path] = None):
        """
        Initialize element classifier.

        Args:
            model_path: Path to saved model file (.pkl)
        """
        self.model: Optional[RandomForestClassifier] = None
        self.label_encoder: Optional[LabelEncoder] = None
        self.feature_names: List[str] = []
        self.trained = False

        if model_path and model_path.exists():
            self.load_model(model_path)

    def extract_features(self, element_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract ML features from element hierarchy data.

        Args:
            element_data: Element attributes from HierarchyCollector

        Returns:
            Feature dictionary
        """
        features = {}

        # Boolean attributes (0/1)
        features['clickable'] = 1.0 if element_data.get('clickable') else 0.0
        features['focusable'] = 1.0 if element_data.get('focusable') else 0.0
        features['enabled'] = 1.0 if element_data.get('enabled', True) else 0.0
        features['checkable'] = 1.0 if element_data.get('checkable') else 0.0
        features['scrollable'] = 1.0 if element_data.get('scrollable') else 0.0
        features['selected'] = 1.0 if element_data.get('selected') else 0.0
        features['password'] = 1.0 if element_data.get('password') else 0.0

        # Text properties
        text = element_data.get('text', '') or ''
        features['has_text'] = 1.0 if text else 0.0
        features['text_length'] = float(len(text))
        features['text_short'] = 1.0 if 0 < len(text) <= 20 else 0.0
        features['text_medium'] = 1.0 if 20 < len(text) <= 100 else 0.0
        features['text_long'] = 1.0 if len(text) > 100 else 0.0

        # Content description
        content_desc = element_data.get('content_desc', '') or element_data.get('label', '') or ''
        features['has_content_desc'] = 1.0 if content_desc else 0.0

        # Test ID
        test_id = element_data.get('resource_id', '') or element_data.get('accessibility_id', '') or ''
        features['has_test_id'] = 1.0 if test_id else 0.0

        # Hierarchy properties
        features['depth'] = float(element_data.get('depth', 0))
        features['children_count'] = float(element_data.get('children_count', 0))
        features['has_children'] = 1.0 if element_data.get('children_count', 0) > 0 else 0.0

        # Size properties
        bounds = element_data.get('bounds', {})
        width = bounds.get('width', 0)
        height = bounds.get('height', 0)
        features['width'] = float(width)
        features['height'] = float(height)
        features['area'] = float(width * height)
        features['aspect_ratio'] = float(width / height) if height > 0 else 0.0

        # Size categories
        features['small'] = 1.0 if width < 100 and height < 100 else 0.0
        features['medium'] = 1.0 if 100 <= width < 300 and 100 <= height < 300 else 0.0
        features['large'] = 1.0 if width >= 300 or height >= 300 else 0.0

        # Class name hints
        class_name = element_data.get('class', '').lower()
        features['class_button'] = 1.0 if 'button' in class_name else 0.0
        features['class_text'] = 1.0 if 'text' in class_name and 'edit' not in class_name else 0.0
        features['class_edit'] = 1.0 if 'edit' in class_name or 'input' in class_name else 0.0
        features['class_image'] = 1.0 if 'image' in class_name else 0.0
        features['class_list'] = 1.0 if 'list' in class_name or 'recycler' in class_name else 0.0
        features['class_view'] = 1.0 if 'view' in class_name and 'text' not in class_name else 0.0
        features['class_switch'] = 1.0 if 'switch' in class_name or 'toggle' in class_name else 0.0
        features['class_checkbox'] = 1.0 if 'checkbox' in class_name or 'check' in class_name else 0.0

        return features

    def prepare_training_data(
            self,
            hierarchy_events: List[Dict[str, Any]]
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare training dataset from recorded hierarchy events.

        Args:
            hierarchy_events: List of HierarchyEvent data with manual labels

        Returns:
            (features_df, labels_series)
        """
        features_list = []
        labels_list = []

        for event in hierarchy_events:
            hierarchy = json.loads(event.get('hierarchy', '{}'))
            elements = self._flatten_hierarchy(hierarchy)

            for element in elements:
                # Skip elements without labels
                if 'element_type' not in element:
                    continue

                features = self.extract_features(element)
                label = element['element_type']

                features_list.append(features)
                labels_list.append(label)

        if not features_list:
            raise ValueError("No labeled training data found")

        features_df = pd.DataFrame(features_list)
        labels_series = pd.Series(labels_list)

        # Store feature names
        self.feature_names = list(features_df.columns)

        logger.info(f"Prepared {len(features_df)} training samples with {len(features_df.columns)} features")
        logger.info(f"Label distribution:\n{labels_series.value_counts()}")

        return features_df, labels_series

    def _flatten_hierarchy(self, node: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
        """Recursively flatten hierarchy tree into list of elements."""
        elements = []

        # Add current node
        element = dict(node)
        element['depth'] = depth
        element['children_count'] = len(node.get('children', []))
        elements.append(element)

        # Process children
        for child in node.get('children', []):
            elements.extend(self._flatten_hierarchy(child, depth + 1))

        return elements

    def train(
            self,
            features: pd.DataFrame,
            labels: pd.Series,
            test_size: float = 0.2,
            random_state: int = 42
    ) -> Dict[str, Any]:
        """
        Train Random Forest classifier.

        Args:
            features: Training features
            labels: Training labels
            test_size: Test set size (0.0-1.0)
            random_state: Random seed for reproducibility

        Returns:
            Training metrics
        """
        # Encode labels
        self.label_encoder = LabelEncoder()
        labels_encoded = self.label_encoder.fit_transform(labels)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            features, labels_encoded,
            test_size=test_size,
            random_state=random_state,
            stratify=labels_encoded
        )

        # Train model
        logger.info("Training Random Forest classifier...")
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=random_state,
            class_weight='balanced',
            n_jobs=-1
        )

        self.model.fit(X_train, y_train)
        self.trained = True

        # Evaluate
        train_score = self.model.score(X_train, y_train)
        test_score = self.model.score(X_test, y_test)

        # Cross-validation
        cv_scores = cross_val_score(self.model, features, labels_encoded, cv=5)

        # Predictions
        y_pred = self.model.predict(X_test)

        # Classification report
        report = classification_report(
            y_test, y_pred,
            target_names=self.label_encoder.classes_,
            output_dict=True
        )

        # Feature importance
        feature_importance = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        metrics = {
            'train_accuracy': float(train_score),
            'test_accuracy': float(test_score),
            'cv_mean': float(cv_scores.mean()),
            'cv_std': float(cv_scores.std()),
            'classification_report': report,
            'feature_importance': feature_importance.to_dict('records'),
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }

        logger.info("Training complete!")
        logger.info(f"Train accuracy: {train_score:.3f}")
        logger.info(f"Test accuracy: {test_score:.3f}")
        logger.info(f"Cross-validation: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
        logger.info(f"\nTop 10 features:\n{feature_importance.head(10)}")

        return metrics

    def train_from_data(
            self,
            training_data: List[Dict[str, Any]],
            test_size: float = 0.2
    ) -> float:
        """
        Train model from list of training examples.

        Args:
            training_data: List of dicts with element features and labels
            test_size: Test set size (0.0-1.0)

        Returns:
            Test accuracy score
        """
        if not training_data:
            raise ValueError("Training data is empty")

        # Extract features and labels from training data
        features_list = []
        labels = []

        for example in training_data:
            features = self.extract_features(example)
            features_list.append(features)
            label = example.get('label', example.get('element_type', 'generic'))
            labels.append(label)

        # Create DataFrame
        features_df = pd.DataFrame(features_list)
        self.feature_names = list(features_df.columns)
        labels_series = pd.Series(labels)

        # Train using the main train method
        metrics = self.train(features_df, labels_series, test_size=test_size)
        return metrics.get('test_accuracy', 0.0)

    def predict(
            self,
            element_data: Dict[str, Any]
    ) -> Tuple[ElementType, float]:
        """
        Predict element type with confidence.

        Args:
            element_data: Element attributes from HierarchyCollector

        Returns:
            (predicted_type, confidence_score)
        """
        if not self.trained or self.model is None:
            raise ValueError("Model not trained. Call train() first or load_model()")

        # Extract features
        features = self.extract_features(element_data)
        features_df = pd.DataFrame([features])[self.feature_names]

        # Predict
        prediction = self.model.predict(features_df)[0]
        probabilities = self.model.predict_proba(features_df)[0]
        confidence = float(probabilities.max())

        # Decode label
        label = self.label_encoder.inverse_transform([prediction])[0]

        # Map to ElementType
        element_type: ElementType
        try:
            element_type = ElementType[label.upper()]
        except KeyError:
            logger.warning(f"Unknown element type: {label}, falling back to GENERIC")
            element_type = ElementType.GENERIC

        return element_type, confidence

    def predict_batch(
            self,
            elements_data: List[Dict[str, Any]]
    ) -> List[Tuple[ElementType, float]]:
        """Predict multiple elements at once."""
        if not self.trained or self.model is None:
            raise ValueError("Model not trained")

        # Extract features for all elements
        features_list = [self.extract_features(el) for el in elements_data]
        features_df = pd.DataFrame(features_list)[self.feature_names]

        # Batch prediction
        predictions = self.model.predict(features_df)
        probabilities = self.model.predict_proba(features_df)
        confidences = probabilities.max(axis=1)

        # Decode labels
        labels = self.label_encoder.inverse_transform(predictions)

        # Map to ElementTypes
        results = []
        for label, confidence in zip(labels, confidences):
            try:
                element_type = ElementType[label.upper()]
            except KeyError:
                element_type = ElementType.GENERIC
            results.append((element_type, float(confidence)))

        return results

    def save_model(self, path: Path):
        """Save trained model to disk."""
        if not self.trained or self.model is None:
            raise ValueError("No trained model to save")

        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            'model': self.model,
            'label_encoder': self.label_encoder,
            'feature_names': self.feature_names
        }

        joblib.dump(model_data, path)
        logger.info(f"Model saved to {path}")

    def load_model(self, path: Path):
        """Load trained model from disk."""
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        model_data = joblib.load(path)

        self.model = model_data['model']
        self.label_encoder = model_data['label_encoder']
        self.feature_names = model_data['feature_names']
        self.trained = True

        logger.info(f"Model loaded from {path}")

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get top N most important features."""
        if not self.trained or self.model is None:
            raise ValueError("Model not trained")

        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False).head(top_n)

        return importance_df
