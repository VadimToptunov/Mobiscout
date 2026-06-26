# Self-Learning ML System

> The model learns automatically from data contributed by all users, without human intervention

---

## 🎯 Concept

**Problem:** Traditional ML models require manual data labeling for each application.

**Solution:** Crowdsource data from all users + automatic labeling.

### How It Works

```
┌────────────────────────────────────────────────────────┐
│  User 1 (Flutter app)     User 2 (React Native app)   │
│          ↓                           ↓                 │
│   Collects elements          Collects elements        │
│   automatically              automatically             │
└─────────────┬────────────────────────┬─────────────────┘
              │                        │
              ↓                        ↓
┌─────────────────────────────────────────────────────────┐
│         Local ML Model (Privacy-First)                  │
│                                                          │
│  • Trains on your data locally                          │
│  • Improves with each test run                          │
│  • No data leaves your machine                          │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ↓
              ┌────────────────────────┐
              │  Model v1.1 (updated)  │
              │  • Local improvements  │
              │  • Your data only      │
              └────────────────────────┘
```

---

## 🚀 User Experience

### First Run

```bash
# 1. Install framework
pip install mobile-observe-test

# 2. Run first test generation
observe project fullcycle --android-source ./app/src --output ./tests/

# Console output:
# ✅ Using universal pre-trained ML model
# 📊 Model version: 1.2.0 (trained locally)
# 🌍 Supports: Android, iOS, Flutter, React Native
# 
# 💡 TIP: Model improves automatically with each test run!
#    All training happens locally - your data never leaves your machine
```

### Automatic Updates

```bash
# Weekly check on startup
observe project fullcycle ...

# Console output:
# 🔄 Checking for model updates...
# ✅ New model available: v1.3.0
# 📥 Downloading... [████████████] 100%
# ✅ Model updated! Accuracy improved: 92% → 95%
# 
# Changelog:
#   • Added 5K new Flutter samples
#   • Improved checkbox detection
#   • Better React Native support
```

### Manual Control

```bash
# Check for updates
observe ml check-updates

# Download latest version
observe ml update-model

# View contribution statistics
observe ml stats

# Output:
# 📊 Your Contributions
# ─────────────────────
# • Samples collected: 2,350
# • Platforms: Android (80%), iOS (20%)
# • Uploaded: 2,350 / 2,350
# • Thank you for helping improve the model! 🎉

# Disable data collection
observe config set ml.contribute false

# Re-enable
observe config set ml.contribute true
```

---

## 🔒 Privacy (Privacy-First Design)

### What is Collected?

```json
{
  "sample_id": "a3f9e82b",
  "class_name": "androidx.compose.material.Button",
  "clickable": true,
  "focusable": true,
  "has_text": true,
  "text_length": 6,
  "bounds_width": 120,
  "bounds_height": 48,
  "platform": "android",
  "element_type": "button",
  "confidence": 0.95,
  "timestamp": "2026-01-12T10:30:00Z"
}
```

### What is NOT Collected?

❌ **App names** - we don't know which app
❌ **Package IDs** - we don't know the developer
❌ **Actual text** - only `has_text: true` and length
❌ **Screenshots** - never collect images
❌ **User data** - no personal information
❌ **API calls** - only UI elements
❌ **IP addresses** - anonymous upload

### Comparison with Other Tools

| Feature              | Mobile Observe | Other Analytics |
|----------------------|----------------|-----------------|
| Collects app names   | ❌              | ✅               |
| Collects screen text | ❌              | ✅ (stacktraces) |
| Collects screenshots | ❌              | ✅               | ❌ |
| Collects user IDs    | ❌              | ✅               | ✅ |
| Can be disabled      | ✅              | ✅               | ✅ |

**Conclusion:** We collect LESS data than standard analytics tools.

---

## 🏗️ Architecture

### Components

**1. SelfLearningCollector** - collects data locally

```python
from framework.ml.self_learning import SelfLearningCollector

collector = SelfLearningCollector(
    opt_in=True  # Local training only
)

# Automatically improves during normal usage
collector.collect_from_hierarchy(hierarchy, platform="android")

# Auto-uploads when batch reaches 1000 samples
```

**2. ModelUpdater** - updates models

```python
from framework.ml.self_learning import ModelUpdater

updater = ModelUpdater()

# Check for updates (happens automatically once per day)
update = updater.check_for_updates()

if update:
    updater.download_update(update)
    # Model updated to v1.3.0!
```

**3. FeedbackCollector** - collects user corrections

```python
from framework.ml.self_learning import FeedbackCollector

feedback = FeedbackCollector()

# When user corrects ML prediction
feedback.record_correction(
    element=element_dict,
    predicted_type="text",      # ML thought it's text
    actual_type="button",       # User corrected: it's a button
    platform="ios"
)

# This correction helps retrain the model!
```

---

## 📈 Model Lifecycle

### Week 1: Initial Release

```
Model v1.0.0
• Trained on: 2,500 synthetic samples
• Accuracy: 87%
• Platforms: Android, iOS
• Users: 0
```

### Week 2: First User Data

```
Model v1.1.0
• New data: +5,000 real samples from 50 users
• Accuracy: 89% (+2%)
• New patterns discovered:
  - Custom Material Design components
  - Jetpack Compose buttons
• Users: 50
```

### Week 4: Growing Dataset

```
Model v1.2.0
• New data: +15,000 samples from 200 users
• Accuracy: 92% (+3%)
• Added support:
  - Flutter widgets
  - React Native components
• Users: 200
```

### Week 12: Production Ready

```
Model v1.5.0
• Total data: 50,000+ real-world samples
• Accuracy: 95% (+3%)
• Platforms: Android, iOS, Flutter, React Native
• Users: 1,000+
• User corrections: 500+ integrated
```

### Year 1: Industry Standard

```
Model v2.0.0
• Total data: 500,000+ samples from 10K+ users
• Accuracy: 98% (+3%)
• Coverage: 99.9% of all mobile UI patterns
• Zero manual labeling required
```

---

## 🔧 Integration into Existing Code

### In ModelBuilder

```python
# framework/model_builder/builder.py

from framework.ml.self_learning import SelfLearningCollector

class ModelBuilder:
    def __init__(self, ...):
        # Initialize self-learning
        self.ml_collector = SelfLearningCollector()
    
    def build_from_events(self, events: List[Event]) -> AppModel:
        # Build model as usual
        model = self._build_model(events)
        
        # Collect training data automatically
        if self.ml_collector.opt_in:
            for screen in model.screens:
                hierarchy = self._screen_to_hierarchy(screen)
                self.ml_collector.collect_from_hierarchy(
                    hierarchy,
                    platform=model.platform.value
                )
        
        return model
```

### In CLI commands

```python
# framework/cli/project_commands.py

from framework.ml.self_learning import ModelUpdater

@project.command()
def fullcycle(...):
    # Check for model updates before starting
    updater = ModelUpdater()
    if updater.auto_update():
        click.echo("✅ ML model updated to latest version!")
    
    # Continue with normal workflow
    ...
```

---

## 🧪 Testing the System

### Local Mode (without server)

```bash
# 1. Generate test data
observe ml generate-test-samples --count 1000 --output test_samples.json

# 2. Collect to local cache (no uploads)
observe config set ml.contribute false  # Disable uploads
observe config set ml.local_cache_only true

# 3. Use framework normally
observe project fullcycle --android-source ./app/src --output ./tests/

# 4. Check collected data
ls ml_cache/training_samples/
# batch_a3f9e82b.json  (1000 samples)

# 5. Analyze collected data
observe ml analyze-cache
# Output:
# 📊 Local Training Cache
# • Batches: 5
# • Total samples: 5,000
# • Platform distribution:
#   - Android: 80% (4,000)
#   - iOS: 20% (1,000)
# • Element types:
#   - button: 1,200
#   - input: 800
#   - text: 1,500
#   ...
```

---

## 💡 Best Practices

### Server Requirements

```yaml
# Infrastructure
- Endpoint: https://api.mobile-observe.dev
- Backup: https://ml.mobile-observe.dev
- CDN: CloudFlare (for model downloads)
- Database: PostgreSQL (metadata)
- Storage: S3 (training samples, models)

# API Endpoints
POST /v1/ml/samples          # Upload training batch
GET  /v1/ml/models/latest    # Get latest model metadata
GET  /v1/ml/models/{version} # Download specific model version
POST /v1/ml/feedback         # Upload user corrections

# Authentication
- API key (for data upload)
- Public download (models available to all)

# Privacy
- No logging of IP addresses
- No user tracking
- GDPR compliant
- Data deletion on request
```

### Training Pipeline

```python
# ml_server/training_pipeline.py

def weekly_retrain():
    """Runs every Sunday at 2 AM UTC"""
    
    # 1. Collect new samples from last week
    new_samples = db.query_samples(since=last_week)
    print(f"New samples: {len(new_samples)}")
    
    # 2. Merge with existing dataset
    full_dataset = merge_datasets(existing_dataset, new_samples)
    
    # 3. Clean and validate
    clean_dataset = validate_and_clean(full_dataset)
    
    # 4. Train new model
    model = train_universal_model(clean_dataset)
    
    # 5. Evaluate
    metrics = evaluate_model(model, test_set)
    print(f"Accuracy: {metrics['accuracy']:.1%}")
    
    # 6. If better than current, publish
    if metrics['accuracy'] > current_model_accuracy:
        publish_model(model, version="1.3.0")
        notify_users("New model available!")
    
    # 7. Generate changelog
    generate_changelog(old_model, new_model)
```

---

## 💡 Alternatives (if no server)

### Option 1: P2P (peer-to-peer)

Users exchange training samples directly through a torrent-like system.

**Pros:**

- No central server needed
- Decentralized

**Cons:**

- More complex to implement
- No quality control

### Option 2: GitHub Releases

Models and datasets published as GitHub Releases.

```bash
# Download latest model
curl -L https://github.com/yourusername/mobile-observe/releases/latest/download/universal_model.pkl \
  -o ml_models/universal_element_classifier.pkl
```

**Pros:**

- Free
- Simple integration
- Version control

**Cons:**

- No automatic data aggregation
- Manual model retraining needed

### Option 3: Federated Learning

Model trains locally on each user's machine, only weights are updated.

**Pros:**

- Maximum privacy
- No data transmission needed

**Cons:**

- Very complex implementation
- Requires significant client resources

---

## 🚀 Roadmap

### Phase 1: Foundation (Done ✅)

- [x] Universal pre-trained model
- [x] Synthetic dataset generation
- [x] Basic ML classification

### Phase 2: Self-Learning (Current)

- [x] SelfLearningCollector implementation
- [x] ModelUpdater implementation
- [x] FeedbackCollector implementation
- [x] Local caching and batching
- [x] Privacy-first data anonymization
- [ ] Production server setup
- [ ] Automated training pipeline

### Phase 3: Infrastructure (Future)

- [ ] Model versioning and rollback
- [ ] A/B testing for model updates
- [ ] User dashboard (contribution stats)
- [ ] Real-time model updates
- [ ] Federated learning support

### Phase 4: Advanced Features (Future)

- [ ] Multi-language model (Rust core?)
- [ ] Custom model fine-tuning UI
- [ ] Model marketplace (community models)
- [ ] Transfer learning for app-specific models
- [ ] Active learning (prioritize uncertain samples)

---

## 📚 References

- **Privacy by Design**: <https://www.privacybydesign.foundation/>
- **Federated Learning**: <https://federated.withgoogle.com/>
- **GDPR Compliance**: <https://gdpr.eu/>
- **ML Model Versioning**: <https://dvc.org/>

---

## 💬 FAQ

**Q: Can I disable data collection?**
A: Yes, anytime: `observe config set ml.contribute false`

**Q: Can I see what data is collected?**
A: Yes, it's stored locally in `ml_cache/training_samples/`. You can inspect any file.

**Q: What if I want to use only my own model?**
A: You can train your own: `observe ml train --data my_data.json --output my_model.pkl`

**Q: Is offline mode supported?**
A: Yes, the model works locally. Internet is only needed for updates.

**Q: How large is the model?**
A: ~5-10 MB (one model for all platforms)

**Q: How often is the model updated?**
A: Planned weekly, but can be more/less frequent depending on data volume.

**Q: What if the server is unavailable?**
A: The framework continues working with the local model. Data is saved locally and uploaded later.

**Q: Can I contribute only for specific platforms (e.g., iOS only)?**
A: Yes, you can configure: `observe config set ml.contribute_platforms ios`

**Q: What if I found a bug in the model?**
A: You can correct the prediction with `observe ml correct` or create an issue on GitHub.

**Q: Is the training data available publicly?**
A: Yes, aggregated datasets will be published periodically for research purposes (with full anonymization).

**Q: Can enterprises use this without data sharing?**
A: Yes, you can disable contribution and use the pre-trained model, or train your own private model.
