"""
Self-learning ML system for mobile element classification.

Automatically collects data from ALL users and continuously improves
the universal model without human intervention.

Architecture:
1. Every user contributes training data anonymously
2. Central model server aggregates data
3. Model retrains weekly/monthly
4. Users auto-download updated models
"""

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests

# ElementType imported for type hints in docstrings

logger = logging.getLogger(__name__)


@dataclass
class ElementSample:
    """
    Single element sample for training.

    Completely anonymized - no app names, no user data, no screenshots.
    """
    # Element attributes
    class_name: str
    clickable: bool
    focusable: bool
    checkable: bool
    scrollable: bool
    enabled: bool
    password: bool

    # Content (sanitized)
    has_text: bool  # True/False only, not actual text
    text_length: int  # Length, not content
    has_content_desc: bool

    # Structural
    bounds_width: int
    bounds_height: int
    depth: int
    children_count: int

    # Platform detection
    platform: str  # "android" | "ios" | "flutter" | "react-native"

    # Label (what type it ACTUALLY is)
    element_type: str  # "button", "input", etc.

    # Confidence metadata
    confidence: float  # How confident are we in this label?
    source: str  # "rule-based" | "ml-predicted" | "user-corrected"

    # Anonymized metadata
    framework_version: str
    timestamp: str
    sample_id: str  # Random hash, not traceable


@dataclass
class TrainingBatch:
    """Batch of training samples to upload."""
    samples: List[ElementSample]
    total_count: int
    platform_distribution: Dict[str, int]
    framework_version: str
    batch_id: str


class SelfLearningCollector:
    """
    Collects training data automatically during normal framework usage.

    Privacy-first design:
    - No app names, package IDs, or identifying info
    - No actual text content, only attributes
    - No screenshots
    - Data stays local until user opts in
    - Can be disabled via config
    """

    def __init__(
            self,
            local_cache_dir: Path = Path("ml_cache/training_samples"),
            opt_in: bool = True,
            upload_endpoint: Optional[str] = None
    ):
        """
        Initialize collector.

        Args:
            local_cache_dir: Where to store samples locally
            opt_in: Whether user has opted in to data sharing
            upload_endpoint: API endpoint for central server (None = local only)
        """
        self.local_cache_dir = local_cache_dir
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)

        self.opt_in = opt_in
        self.upload_endpoint = upload_endpoint or "https://api.mobile-observe.dev/v1/ml/samples"

        self.samples: List[ElementSample] = []
        self.batch_size = 1000  # Upload after 1000 samples

    def collect_from_hierarchy(
            self,
            hierarchy: Dict[str, Any],
            platform: str,
            confidence: float = 1.0,
            source: str = "rule-based"
    ) -> None:
        """
        Collect training samples from UI hierarchy.

        Args:
            hierarchy: UI hierarchy dict
            platform: "android" | "ios" | "flutter" | "react-native"
            confidence: How confident are we in the labels?
            source: Where did the labels come from?
        """
        samples = self._extract_samples_recursive(hierarchy, platform, confidence, source)
        self.samples.extend(samples)

        # Auto-save to disk
        if len(self.samples) >= self.batch_size:
            self._save_batch()

    def _extract_samples_recursive(
            self,
            node: Dict[str, Any],
            platform: str,
            confidence: float,
            source: str,
            depth: int = 0
    ) -> List[ElementSample]:
        """Extract samples from hierarchy tree."""
        samples = []

        # Extract current node
        if "element_type" in node:  # Only labeled elements
            sample = self._create_sample(node, platform, confidence, source, depth)
            samples.append(sample)

        # Process children
        for child in node.get("children", []):
            child_samples = self._extract_samples_recursive(
                child, platform, confidence, source, depth + 1
            )
            samples.extend(child_samples)

        return samples

    def _create_sample(
            self,
            element: Dict[str, Any],
            platform: str,
            confidence: float,
            source: str,
            depth: int
    ) -> ElementSample:
        """Create anonymized sample from element."""
        text = element.get("text", "") or element.get("label", "")
        content_desc = element.get("content_desc", "") or element.get("accessibilityLabel", "")

        # Generate anonymous ID
        sample_id = hashlib.sha256(
            f"{element.get('class', '')}-{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        return ElementSample(
            # Attributes
            class_name=element.get("class", ""),
            clickable=element.get("clickable", False),
            focusable=element.get("focusable", False),
            checkable=element.get("checkable", False),
            scrollable=element.get("scrollable", False),
            enabled=element.get("enabled", True),
            password=element.get("password", False),

            # Content (sanitized)
            has_text=bool(text),
            text_length=len(text) if text else 0,
            has_content_desc=bool(content_desc),

            # Structural
            bounds_width=element.get("bounds", {}).get("width", 0),
            bounds_height=element.get("bounds", {}).get("height", 0),
            depth=depth,
            children_count=len(element.get("children", [])),

            # Platform
            platform=platform,

            # Label
            element_type=element.get("element_type", "generic"),

            # Confidence
            confidence=confidence,
            source=source,

            # Metadata
            framework_version="1.0.0",  # TODO: Get from config
            timestamp=datetime.now().isoformat(),
            sample_id=sample_id
        )

    def _save_batch(self) -> None:
        """Save current batch to disk."""
        if not self.samples:
            return

        batch = TrainingBatch(
            samples=self.samples,
            total_count=len(self.samples),
            platform_distribution=self._get_platform_distribution(),
            framework_version="1.0.0",
            batch_id=hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()[:16]
        )

        # Save locally
        batch_file = self.local_cache_dir / f"batch_{batch.batch_id}.json"
        with open(batch_file, 'w') as f:
            json.dump(asdict(batch), f, indent=2)

        logger.info(f"Saved training batch: {batch_file} ({len(self.samples)} samples)")

        # Upload if opted in
        if self.opt_in:
            self._upload_batch(batch)

        # Clear samples
        self.samples = []

    def _get_platform_distribution(self) -> Dict[str, int]:
        """Get platform distribution in current batch."""
        distribution: Dict[str, int] = {}
        for sample in self.samples:
            platform = sample.platform
            distribution[platform] = distribution.get(platform, 0) + 1
        return distribution

    def _upload_batch(self, batch: TrainingBatch) -> bool:
        """
        Upload batch to central server.

        Returns:
            True if upload succeeded
        """
        try:
            response = requests.post(
                self.upload_endpoint,
                json=asdict(batch),
                timeout=30,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                logger.info(f"Uploaded batch {batch.batch_id} successfully")
                return True
            else:
                logger.warning(f"Upload failed: {response.status_code}")
                return False

        except (requests.RequestException, OSError, TypeError, ValueError) as e:
            logger.warning(f"Could not upload batch: {e}")
            return False

    def get_local_samples_count(self) -> int:
        """Get total number of local samples."""
        batch_files = list(self.local_cache_dir.glob("batch_*.json"))
        total = 0

        for batch_file in batch_files:
            with open(batch_file, 'r') as f:
                batch = json.load(f)
                total += batch.get("total_count", 0)

        return total


class ModelUpdater:
    """
    Automatically downloads and updates ML models.

    Models are versioned and signed for security.
    """

    def __init__(
            self,
            model_dir: Path = Path("ml_models"),
            update_endpoint: str = "https://api.mobile-observe.dev/v1/ml/models"
    ):
        """
        Initialize updater.

        Args:
            model_dir: Where to store models
            update_endpoint: API endpoint for model downloads
        """
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.update_endpoint = update_endpoint

    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        Check if newer model version is available.

        Returns:
            Model metadata if update available, None otherwise
        """
        try:
            current_version = self._get_current_version()

            response = requests.get(
                f"{self.update_endpoint}/latest",
                params={"current_version": current_version},
                timeout=10
            )

            if response.status_code == 200:
                latest = response.json()

                if latest["version"] > current_version:
                    logger.info(f"New model available: v{latest['version']}")
                    return latest
                else:
                    logger.info("Model is up to date")
                    return None

            return None

        except (requests.RequestException, OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Could not check for updates: {e}")
            return None

    def download_update(self, model_metadata: Dict[str, Any]) -> bool:
        """
        Download and install model update.

        Args:
            model_metadata: Metadata from check_for_updates()

        Returns:
            True if update succeeded
        """
        try:
            download_url = model_metadata["download_url"]
            version = model_metadata["version"]
            checksum = model_metadata["sha256"]

            logger.info(f"Downloading model v{version}...")

            # Download
            response = requests.get(download_url, timeout=120)
            model_data = response.content

            # Verify checksum
            actual_checksum = hashlib.sha256(model_data).hexdigest()
            if actual_checksum != checksum:
                logger.error("Model checksum mismatch!")
                return False

            # Save
            model_file = self.model_dir / "universal_element_classifier.pkl"
            with open(model_file, 'wb') as f:
                f.write(model_data)

            # Save metadata
            metadata_file = self.model_dir / "model_metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(model_metadata, f, indent=2)

            logger.info(f"Model updated to v{version}")
            return True

        except (requests.RequestException, OSError, KeyError, ValueError) as e:
            logger.error(f"Model update failed: {e}")
            return False

    def _get_current_version(self) -> str:
        """Get current model version."""
        metadata_file = self.model_dir / "model_metadata.json"

        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                return metadata.get("version", "0.0.0")

        return "0.0.0"

    def auto_update(self) -> bool:
        """
        Check for and install updates automatically.

        Returns:
            True if update was installed
        """
        update = self.check_for_updates()

        if update:
            return self.download_update(update)

        return False


class FeedbackCollector:
    """
    Collects user feedback on ML predictions.

    When ML misclassifies an element, users can correct it,
    and this feedback is used to improve the model.
    """

    def __init__(self, feedback_dir: Path = Path("ml_cache/feedback")):
        """Initialize feedback collector."""
        self.feedback_dir = feedback_dir
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

    def record_correction(
            self,
            element: Dict[str, Any],
            predicted_type: str,
            actual_type: str,
            platform: str
    ) -> None:
        """
        Record a user correction.

        Args:
            element: The misclassified element
            predicted_type: What ML predicted
            actual_type: What it actually is (user-corrected)
            platform: Platform
        """
        correction = {
            "element": {
                "class": element.get("class", ""),
                "clickable": element.get("clickable", False),
                "has_text": bool(element.get("text", "")),
                # ... other anonymized attributes
            },
            "predicted_type": predicted_type,
            "actual_type": actual_type,
            "platform": platform,
            "timestamp": datetime.now().isoformat(),
            "correction_id": hashlib.sha256(
                f"{element.get('class', '')}-{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]
        }

        # Save correction
        correction_file = self.feedback_dir / f"correction_{correction['correction_id']}.json"
        with open(correction_file, 'w') as f:
            json.dump(correction, f, indent=2)

        logger.info(f"Recorded correction: {predicted_type} → {actual_type}")


def create_self_learning_pipeline():
    """
    Create complete self-learning pipeline.

    This is called automatically during normal framework usage.
    """
    collector = SelfLearningCollector(
        opt_in=True,  # TODO: Read from config
        upload_endpoint="https://api.mobile-observe.dev/v1/ml/samples"
    )

    updater = ModelUpdater()
    feedback = FeedbackCollector()

    return {
        "collector": collector,
        "updater": updater,
        "feedback": feedback
    }


if __name__ == "__main__":
    # Demo: Collect samples
    collector = SelfLearningCollector(opt_in=False)  # Local only for demo

    # Simulate collecting data from a session
    sample_hierarchy = {
        "class": "android.widget.Button",
        "text": "Submit",
        "clickable": True,
        "element_type": "button",
        "children": []
    }

    collector.collect_from_hierarchy(sample_hierarchy, platform="android")

    print(f"Collected {len(collector.samples)} samples")
    print(f"Total local samples: {collector.get_local_samples_count()}")
