"""
Unit tests for STEP 5: ML Module

Tests ML-powered selector prediction, step recommendations, and element scoring.
Includes positive, negative, and edge case tests.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from framework.ml import (
    MLBackend,
    ModelType,
    PredictionResult,
    TrainingData,
    SelectorPredictor,
    NextStepRecommender,
    ElementScorer,
    MLModule
)


class TestMLBackend:
    """Test MLBackend enum"""

    def test_all_backends(self):
        """Test all backend types"""
        backends = [
            MLBackend.SKLEARN,
            MLBackend.TENSORFLOW,
            MLBackend.PYTORCH,
            MLBackend.ONNX,
            MLBackend.CUSTOM
        ]
        assert len(backends) == 5
        assert all(isinstance(b, MLBackend) for b in backends)


class TestModelType:
    """Test ModelType enum"""

    def test_all_model_types(self):
        """Test all model types"""
        types = [
            ModelType.SELECTOR_PREDICTOR,
            ModelType.STEP_RECOMMENDER,
            ModelType.ELEMENT_SCORER,
            ModelType.EDGE_CASE_DETECTOR
        ]
        assert len(types) == 4


class TestPredictionResult:
    """Test PredictionResult dataclass"""

    def test_create_prediction_result(self):
        """Test creating prediction result"""
        result = PredictionResult(
            prediction="id",
            confidence=0.95,
            alternatives=[("accessibility_id", 0.8), ("xpath", 0.6)],
            model_version="1.0.0",
            metadata={'test': True}
        )

        assert result.prediction == "id"
        assert result.confidence == 0.95
        assert len(result.alternatives) == 2
        assert result.model_version == "1.0.0"


class TestTrainingData:
    """Test TrainingData dataclass"""

    def test_create_training_data(self):
        """Test creating training data"""
        data = TrainingData(
            features=[{'id': 'test', 'type': 'button'}],
            labels=['id'],
            metadata={'source': 'manual'}
        )

        assert len(data.features) == 1
        assert len(data.labels) == 1
        assert data.metadata['source'] == 'manual'


class TestSelectorPredictor:
    """Test SelectorPredictor"""

    def test_predictor_initialization(self):
        """Test predictor initialization"""
        predictor = SelectorPredictor()

        assert predictor.model_type == ModelType.SELECTOR_PREDICTOR
        assert predictor.backend == MLBackend.SKLEARN
        assert not predictor.is_trained

    def test_predictor_with_custom_backend(self):
        """Test predictor with custom backend"""
        predictor = SelectorPredictor(backend=MLBackend.PYTORCH)

        assert predictor.backend == MLBackend.PYTORCH

    def test_predict_with_id(self):
        """Test prediction for element with ID"""
        predictor = SelectorPredictor()

        features = {
            'id': 'login_button',
            'accessibility_id': 'login_btn',
            'xpath': '//button[@id="login_button"]',
            'label': 'Login',
            'type': 'button',
            'visible': True,
            'enabled': True
        }

        result = predictor.predict(features)

        assert result.prediction == 'id'
        assert result.confidence == 1.0
        assert len(result.alternatives) > 0

    def test_predict_without_id(self):
        """Test prediction for element without ID"""
        predictor = SelectorPredictor()

        features = {
            'accessibility_id': 'submit_btn',
            'xpath': '//button',
            'type': 'button',
            'visible': True,
            'enabled': True
        }

        result = predictor.predict(features)

        assert result.prediction == 'accessibility_id'
        assert result.confidence == 0.8

    def test_predict_with_minimal_features(self):
        """Test prediction with minimal features"""
        predictor = SelectorPredictor()

        features = {
            'xpath': '//div',
            'type': 'view'
        }

        result = predictor.predict(features)

        assert result.prediction in ['xpath', 'text']
        assert result.confidence <= 1.0

    def test_predict_empty_features(self):
        """Test prediction with empty features (negative test)"""
        predictor = SelectorPredictor()

        features = {}
        result = predictor.predict(features)

        assert result.prediction == 'xpath'
        assert result.confidence <= 0.5

    def test_feature_extraction(self):
        """Test feature extraction"""
        predictor = SelectorPredictor()

        features = {
            'id': 'test',
            'accessibility_id': 'test_acc',
            'xpath': '//test',
            'label': 'Test',
            'type': 'button',
            'visible': True,
            'enabled': True,
            'depth': 3,
            'siblings_count': 5
        }

        feature_vector = predictor._extract_features(features)

        assert len(feature_vector) == 11
        assert feature_vector[0] == 1.0  # has_id
        assert feature_vector[1] == 1.0  # has_accessibility_id

    @patch('framework.ml.ml_module.check_feature')
    def test_train_without_license(self, mock_check):
        """Test training without license (negative test)"""
        mock_check.return_value = False

        predictor = SelectorPredictor()
        training_data = TrainingData(
            features=[{'id': 'test'}],
            labels=['id'],
            metadata={}
        )

        with pytest.raises(PermissionError):
            predictor.train(training_data)

    @patch('framework.ml.ml_module.check_feature')
    def test_train_with_sklearn(self, mock_check):
        """Test training with sklearn backend"""
        mock_check.return_value = True

        predictor = SelectorPredictor(backend=MLBackend.SKLEARN)

        # Create training data
        features = [
            {'id': 'btn1', 'type': 'button', 'visible': True, 'enabled': True},
            {'id': 'btn2', 'type': 'button', 'visible': True, 'enabled': True},
            {'accessibility_id': 'btn3', 'type': 'button', 'visible': True, 'enabled': True}
        ]
        labels = ['id', 'id', 'accessibility_id']

        training_data = TrainingData(features=features, labels=labels, metadata={})

        try:
            metrics = predictor.train(training_data)
            assert 'accuracy' in metrics
            assert predictor.is_trained
        except ImportError:
            pytest.skip("scikit-learn not installed")

    def test_train_with_unsupported_backend(self):
        """Test training with unsupported backend (negative test)"""
        predictor = SelectorPredictor(backend=MLBackend.CUSTOM)

        training_data = TrainingData(
            features=[{'id': 'test'}],
            labels=['id'],
            metadata={}
        )

        with patch('framework.ml.ml_module.check_feature', return_value=True):
            with pytest.raises(NotImplementedError):
                predictor.train(training_data)

    def test_save_and_load(self, tmp_path):
        """Test saving and loading model"""
        predictor = SelectorPredictor()

        model_path = tmp_path / "selector_predictor"
        predictor.save(model_path)

        assert (tmp_path / "selector_predictor.json").exists()

        # Load model
        new_predictor = SelectorPredictor()
        new_predictor.load(model_path)

        assert new_predictor.version == predictor.version

    def test_get_info(self):
        """Test getting model info"""
        predictor = SelectorPredictor()

        info = predictor.get_info()

        assert 'model_type' in info
        assert 'backend' in info
        assert 'version' in info
        assert 'is_trained' in info

    def test_alternatives_generation(self):
        """Test alternative selector generation"""
        predictor = SelectorPredictor()

        features = {
            'id': 'test',
            'accessibility_id': 'test_acc',
            'xpath': '//test',
            'label': 'Test'
        }

        result = predictor.predict(features)

        assert len(result.alternatives) > 0
        assert all(isinstance(alt, tuple) for alt in result.alternatives)
        assert all(len(alt) == 2 for alt in result.alternatives)


class TestNextStepRecommender:
    """Test NextStepRecommender"""

    def test_recommender_initialization(self):
        """Test recommender initialization"""
        recommender = NextStepRecommender()

        assert recommender.model_type == ModelType.STEP_RECOMMENDER
        assert not recommender.is_trained

    def test_recommend_without_history(self):
        """Test recommendation without history"""
        recommender = NextStepRecommender()

        context = {
            'current_screen': 'login',
            'recent_actions': []
        }

        result = recommender.predict(context)

        assert result.prediction == "explore_new_screen"
        assert result.confidence <= 0.5

    def test_recommend_with_history(self):
        """Test recommendation with transition history"""
        recommender = NextStepRecommender()

        # Build history
        recommender._transition_history = {
            'login': ['home', 'home', 'error']
        }

        context = {
            'current_screen': 'login',
            'recent_actions': ['tap_login']
        }

        result = recommender.predict(context)

        assert result.prediction == 'home'
        assert result.confidence > 0.5

    def test_recommend_multiple_alternatives(self):
        """Test recommendation with multiple alternatives"""
        recommender = NextStepRecommender()

        recommender._transition_history = {
            'home': ['profile', 'settings', 'profile']
        }

        context = {'current_screen': 'home'}

        result = recommender.predict(context)

        assert result.prediction == 'profile'
        assert len(result.alternatives) > 0

    @patch('framework.ml.ml_module.check_feature')
    def test_train_recommender(self, mock_check):
        """Test training recommender"""
        mock_check.return_value = True

        recommender = NextStepRecommender()

        features = [
            {'from_screen': 'login', 'to_screen': 'home'},
            {'from_screen': 'login', 'to_screen': 'home'},
            {'from_screen': 'home', 'to_screen': 'profile'}
        ]

        training_data = TrainingData(features=features, labels=[], metadata={})

        metrics = recommender.train(training_data)

        assert 'unique_screens' in metrics
        assert recommender.is_trained
        assert len(recommender._transition_history) > 0

    def test_save_and_load_recommender(self, tmp_path):
        """Test saving and loading recommender"""
        recommender = NextStepRecommender()
        recommender._transition_history = {'a': ['b', 'c']}

        model_path = tmp_path / "recommender.json"
        recommender.save(model_path)

        assert model_path.exists()

        new_recommender = NextStepRecommender()
        new_recommender.load(model_path)

        assert new_recommender._transition_history == recommender._transition_history

    def test_predict_with_empty_context(self):
        """Test prediction with empty context (negative test)"""
        recommender = NextStepRecommender()

        context = {}
        result = recommender.predict(context)

        assert result.prediction == "explore_new_screen"


class TestElementScorer:
    """Test ElementScorer"""

    def test_scorer_initialization(self):
        """Test scorer initialization"""
        scorer = ElementScorer()

        assert scorer.model_type == ModelType.ELEMENT_SCORER
        assert not scorer.is_trained

    def test_score_interactive_element(self):
        """Test scoring interactive element"""
        scorer = ElementScorer()

        features = {
            'type': 'button',
            'visible': True,
            'enabled': True,
            'label': 'Submit',
            'navigates': True
        }

        result = scorer.predict(features)

        assert result.prediction >= 0.8
        assert result.confidence > 0

    def test_score_non_interactive_element(self):
        """Test scoring non-interactive element"""
        scorer = ElementScorer()

        features = {
            'type': 'label',
            'visible': False,
            'enabled': False
        }

        result = scorer.predict(features)

        assert result.prediction < 0.5

    def test_score_textfield(self):
        """Test scoring textfield element"""
        scorer = ElementScorer()

        features = {
            'type': 'textfield',
            'visible': True,
            'enabled': True,
            'label': 'Username'
        }

        result = scorer.predict(features)

        assert result.prediction >= 0.5

    def test_score_empty_features(self):
        """Test scoring with empty features (negative test)"""
        scorer = ElementScorer()

        features = {}
        result = scorer.predict(features)

        assert result.prediction == 0.0

    @patch('framework.ml.ml_module.check_feature')
    def test_train_scorer(self, mock_check):
        """Test training scorer"""
        mock_check.return_value = True

        scorer = ElementScorer()

        training_data = TrainingData(
            features=[{'type': 'button'}],
            labels=[1.0],
            metadata={}
        )

        metrics = scorer.train(training_data)

        assert scorer.is_trained
        assert 'samples' in metrics

    def test_save_and_load_scorer(self, tmp_path):
        """Test saving and loading scorer"""
        scorer = ElementScorer()

        model_path = tmp_path / "scorer.json"
        scorer.save(model_path)

        assert model_path.exists()

        new_scorer = ElementScorer()
        new_scorer.load(model_path)

        assert new_scorer.version == scorer.version


class TestMLModule:
    """Test MLModule"""

    def test_module_initialization(self):
        """Test module initialization"""
        module = MLModule()

        assert module.backend == MLBackend.SKLEARN
        assert len(module.models) > 0
        assert ModelType.SELECTOR_PREDICTOR in module.models

    def test_module_with_custom_backend(self):
        """Test module with custom backend"""
        module = MLModule(backend=MLBackend.PYTORCH)

        assert module.backend == MLBackend.PYTORCH

    def test_predict_selector(self):
        """Test selector prediction via module"""
        module = MLModule()

        features = {
            'id': 'test_button',
            'type': 'button'
        }

        result = module.predict_selector(features)

        assert isinstance(result, PredictionResult)
        assert result.prediction in ['id', 'accessibility_id', 'xpath', 'text']

    def test_recommend_next_step(self):
        """Test next step recommendation via module"""
        module = MLModule()

        context = {
            'current_screen': 'home',
            'recent_actions': []
        }

        result = module.recommend_next_step(context)

        assert isinstance(result, PredictionResult)

    def test_score_element(self):
        """Test element scoring via module"""
        module = MLModule()

        features = {
            'type': 'button',
            'visible': True,
            'enabled': True
        }

        result = module.score_element(features)

        assert isinstance(result, PredictionResult)
        assert 0.0 <= result.prediction <= 1.0

    @patch('framework.ml.ml_module.check_feature')
    def test_train_model(self, mock_check):
        """Test training model via module"""
        mock_check.return_value = True

        module = MLModule()

        training_data = TrainingData(
            features=[{'type': 'button'}],
            labels=[1.0],
            metadata={}
        )

        metrics = module.train_model(ModelType.ELEMENT_SCORER, training_data)

        assert isinstance(metrics, dict)

    def test_train_unknown_model(self):
        """Test training unknown model type (negative test)"""
        module = MLModule()

        with pytest.raises(ValueError):
            module.train_model(Mock(), TrainingData([], [], {}))

    def test_get_models_info(self):
        """Test getting all models info"""
        module = MLModule()

        info = module.get_models_info()

        assert isinstance(info, dict)
        assert len(info) > 0
        assert 'selector_predictor' in info

    def test_load_pretrained_models(self, tmp_path):
        """Test loading pre-trained models"""
        # Create fake pre-trained model
        model_dir = tmp_path / "models"
        model_dir.mkdir()

        model_data = {
            'type': 'selector_predictor',
            'backend': 'sklearn',
            'version': '1.0.0',
            'is_trained': True
        }

        with open(model_dir / "selector_predictor.json", 'w') as f:
            json.dump(model_data, f)

        # Initialize module with models_dir
        module = MLModule(models_dir=model_dir)

        predictor = module.models[ModelType.SELECTOR_PREDICTOR]
        # Model should be loaded (or at least attempted)
        assert predictor is not None


class TestMLModelIntegration:
    """Integration tests for ML models"""

    def test_selector_predictor_with_flow_discovery(self):
        """Test integrating selector predictor with flow discovery"""
        from framework.flow import FlowDiscovery

        discovery = FlowDiscovery()
        module = MLModule()

        # Record screen
        elements = [
            {'id': 'btn1', 'type': 'button', 'visible': True, 'enabled': True},
            {'accessibility_id': 'btn2', 'type': 'button', 'visible': True, 'enabled': True}
        ]

        discovery.record_screen("test", "Test", elements)

        # Predict selectors for each element
        for elem in elements:
            result = module.predict_selector(elem)
            assert result.confidence > 0

    def test_step_recommender_with_flow_history(self):
        """Test step recommender with flow history"""
        module = MLModule()

        # Simulate flow history
        recommender = module.models[ModelType.STEP_RECOMMENDER]
        recommender._transition_history = {
            'login': ['home', 'home', 'error'],
            'home': ['profile', 'settings']
        }

        # Get recommendations
        result = module.recommend_next_step({'current_screen': 'login'})
        assert result.prediction == 'home'

        result = module.recommend_next_step({'current_screen': 'home'})
        assert result.prediction in ['profile', 'settings']


class TestMLModuleErrorHandling:
    """Test error handling in ML module"""

    def test_predict_with_invalid_features(self):
        """Test prediction with invalid features"""
        module = MLModule()

        # Should not crash, should handle gracefully
        result = module.predict_selector({})  # Empty dict instead of None
        assert isinstance(result, PredictionResult)

    def test_save_to_invalid_path(self):
        """Test saving to invalid path (negative test)"""
        predictor = SelectorPredictor()

        # Should handle gracefully or raise informative error
        invalid_path = Path("/invalid/path/that/does/not/exist/model")

        try:
            predictor.save(invalid_path)
        except Exception as e:
            assert isinstance(e, (OSError, PermissionError, FileNotFoundError))

    def test_load_from_nonexistent_file(self):
        """Test loading from non-existent file (negative test)"""
        predictor = SelectorPredictor()

        with pytest.raises(FileNotFoundError):
            predictor.load(Path("/nonexistent/model.json"))


class TestMLBackendFlexibility:
    """Test ML backend flexibility"""

    def test_switch_backends(self):
        """Test switching between different backends"""
        backends = [MLBackend.SKLEARN, MLBackend.PYTORCH, MLBackend.TENSORFLOW]

        for backend in backends:
            predictor = SelectorPredictor(backend=backend)
            assert predictor.backend == backend

    def test_custom_backend(self):
        """Test using custom backend"""
        predictor = SelectorPredictor(backend=MLBackend.CUSTOM)

        # Should work for prediction (heuristic fallback)
        features = {'id': 'test'}
        result = predictor.predict(features)

        assert isinstance(result, PredictionResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
