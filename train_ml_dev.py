"""
ML Training Module - DEV MODE (без license check для разработки)

Версия для разработки и тестирования ML моделей
"""

from pathlib import Path
from unittest.mock import patch


def train_all_models_dev():
    """Тренировка моделей в DEV режиме (обходим license check)"""

    # Patch license check для разработки
    with patch('framework.ml.ml_module.check_feature', return_value=True):
        from framework.ml import MLModule, MLBackend, ModelType, TrainingData

        output_dir = Path.home() / '.observe' / 'models'
        output_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 70)
        print("🤖 ML MODEL TRAINING (DEV MODE)")
        print("=" * 70)
        print()

        # Генерация данных
        print("📊 Generating training data...")

        # 1. Selector Predictor Data
        selector_features = []
        selector_labels = []

        # Элементы с ID (best practice)
        for i in range(100):
            selector_features.append({
                'id': f'btn_{i}',
                'accessibility_id': f'button_{i}',
                'xpath': f'//button[@id="btn_{i}"]',
                'type': 'button',
                'visible': True,
                'enabled': True,
                'depth': 3
            })
            selector_labels.append('id')

        # Элементы с accessibility_id
        for i in range(60):
            selector_features.append({
                'id': '',
                'accessibility_id': f'element_{i}',
                'xpath': f'//div[@class="element_{i}"]',
                'type': 'view',
                'visible': True,
                'enabled': True,
                'depth': 4
            })
            selector_labels.append('accessibility_id')

        # Элементы с xpath only
        for i in range(40):
            selector_features.append({
                'id': '',
                'accessibility_id': '',
                'xpath': f'//div[{i}]/span',
                'type': 'label',
                'visible': True,
                'enabled': True,
                'depth': 5
            })
            selector_labels.append('xpath')

        selector_data = TrainingData(
            features=selector_features,
            labels=selector_labels,
            metadata={'source': 'dev_training'}
        )

        print(f"   ✅ Generated {len(selector_features)} selector samples")

        # 2. Step Recommender Data
        step_features = []

        # Типичные переходы
        flows = [
            ('splash', 'onboarding', 50),
            ('onboarding', 'login', 45),
            ('login', 'home', 80),
            ('home', 'profile', 60),
            ('home', 'settings', 50),
            ('profile', 'edit_profile', 40),
        ]

        for from_screen, to_screen, count in flows:
            step_features.extend([
                {'from_screen': from_screen, 'to_screen': to_screen}
                for _ in range(count)
            ])

        step_data = TrainingData(
            features=step_features,
            labels=[],
            metadata={'source': 'dev_training'}
        )

        print(f"   ✅ Generated {len(step_features)} transition patterns")

        # 3. Element Scorer Data
        element_features = []
        element_labels = []

        # High importance
        for i in range(50):
            element_features.append({
                'type': 'button',
                'visible': True,
                'enabled': True,
                'label': f'Submit {i}',
                'navigates': True
            })
            element_labels.append(0.9)

        # Medium importance
        for i in range(30):
            element_features.append({
                'type': 'link',
                'visible': True,
                'enabled': True,
                'label': f'Link {i}'
            })
            element_labels.append(0.5)

        # Low importance
        for i in range(20):
            element_features.append({
                'type': 'label',
                'visible': True,
                'enabled': False,
                'decorative': True
            })
            element_labels.append(0.1)

        element_data = TrainingData(
            features=element_features,
            labels=element_labels,
            metadata={'source': 'dev_training'}
        )

        print(f"   ✅ Generated {len(element_features)} element samples")
        print()

        # Инициализация ML Module
        ml_module = MLModule(backend=MLBackend.SKLEARN, models_dir=output_dir)

        # Training
        print("=" * 70)
        print("🎓 TRAINING MODELS")
        print("=" * 70)
        print()

        # 1. Train Selector Predictor
        print("1️⃣ Training SelectorPredictor...")
        try:
            import sklearn
            metrics = ml_module.train_model(ModelType.SELECTOR_PREDICTOR, selector_data)
            print(f"   ✅ Training complete!")
            print(f"   Accuracy: {metrics.get('accuracy', 0):.4f}")
            print(f"   Train samples: {metrics.get('train_samples', 0)}")
            print(f"   Test samples: {metrics.get('test_samples', 0)}")
        except ImportError:
            print("   ⚠️  scikit-learn not installed")
            print("   Install: pip install scikit-learn")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        print()

        # 2. Train Step Recommender
        print("2️⃣ Training NextStepRecommender...")
        try:
            metrics = ml_module.train_model(ModelType.STEP_RECOMMENDER, step_data)
            print(f"   ✅ Training complete!")
            print(f"   Unique screens: {metrics.get('unique_screens', 0)}")
            print(f"   Total transitions: {metrics.get('total_transitions', 0)}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        print()

        # 3. Train Element Scorer
        print("3️⃣ Training ElementScorer...")
        try:
            metrics = ml_module.train_model(ModelType.ELEMENT_SCORER, element_data)
            print(f"   ✅ Training complete!")
            print(f"   Samples: {metrics.get('samples', 0)}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        print()

        # Test predictions
        print("=" * 70)
        print("🧪 TESTING PREDICTIONS")
        print("=" * 70)
        print()

        # Test 1: Selector Prediction
        print("📊 Test 1: Predict best selector")
        test_elem = {
            'id': 'submit_btn',
            'accessibility_id': 'submit',
            'xpath': '//button[@id="submit_btn"]',
            'type': 'button',
            'visible': True,
            'enabled': True
        }
        result = ml_module.predict_selector(test_elem)
        print(f"   Element: {test_elem['id']}")
        print(f"   ✅ Predicted: {result.prediction}")
        print(f"   Confidence: {result.confidence:.2f}")
        if result.alternatives:
            print(f"   Alternatives: {result.alternatives[:2]}")
        print()

        # Test 2: Next Step Recommendation
        print("🔮 Test 2: Recommend next step")
        context = {'current_screen': 'login', 'recent_actions': ['tap_login']}
        result = ml_module.recommend_next_step(context)
        print(f"   Current: {context['current_screen']}")
        print(f"   ✅ Recommended: {result.prediction}")
        print(f"   Confidence: {result.confidence:.2f}")
        print()

        # Test 3: Element Importance
        print("⭐ Test 3: Score element importance")
        test_elem = {
            'type': 'button',
            'visible': True,
            'enabled': True,
            'label': 'Submit Form',
            'navigates': True
        }
        result = ml_module.score_element(test_elem)
        print(f"   Element: {test_elem['label']}")
        print(f"   ✅ Score: {result.prediction:.2f}")
        print()

        # Model info
        print("=" * 70)
        print("📋 TRAINED MODELS")
        print("=" * 70)
        print()

        models_info = ml_module.get_models_info()
        for name, info in models_info.items():
            status = "✅ TRAINED" if info['is_trained'] else "❌ NOT TRAINED"
            print(f"📦 {name.upper()}")
            print(f"   Backend: {info['backend']}")
            print(f"   Version: {info['version']}")
            print(f"   Status: {status}")
            print()

        print("=" * 70)
        print("✅ SUCCESS")
        print("=" * 70)
        print()
        print(f"📁 Models saved to: {output_dir}")
        print()
        print("💡 Models are now ready for inference!")
        print()


if __name__ == "__main__":
    train_all_models_dev()
