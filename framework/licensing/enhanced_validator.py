"""
STEP 7: Paid Modules Enhancement - Advanced License System

Features:
- Enhanced license validation with feature gates
- Usage analytics and telemetry
- Subscription management
- Feature flags system
- License tiers: FREE, PRO, ENTERPRISE
- Graceful degradation
- Informative upgrade prompts
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable


class LicenseTier(Enum):
    """License tiers"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    TRIAL = "trial"


class FeatureFlag(Enum):
    """Feature flags for different license tiers"""
    # FREE features
    CORE_ENGINE = "core_engine"
    LOCAL_DEVICES = "local_devices"
    BASIC_TEST_GEN = "basic_test_gen"
    SELF_HEALING = "self_healing"
    FLOW_DISCOVERY = "flow_discovery"
    ML_INFERENCE = "ml_inference"

    # PRO features
    CLOUD_DEVICES = "cloud_devices"
    PARALLEL_EXECUTION = "parallel_execution"
    ADVANCED_ML = "advanced_ml"
    API_MOCKING = "api_mocking"
    LOAD_TESTING = "load_testing"
    PRIORITY_SUPPORT = "priority_support"

    # ENTERPRISE features
    ML_TRAINING = "ml_training"
    CUSTOM_MODELS = "custom_models"
    DISTRIBUTED_EXECUTION = "distributed_execution"
    SSO_LDAP = "sso_ldap"
    ON_PREMISE = "on_premise"
    DEDICATED_SUPPORT = "dedicated_support"
    SECURITY_SCANNING = "security_scanning"
    PERFORMANCE_PROFILING = "performance_profiling"


@dataclass
class License:
    """License information"""
    tier: LicenseTier
    email: str
    organization: Optional[str] = None
    license_key: str = ""
    issued_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    max_users: int = 1
    max_devices: int = 5
    features: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if license is valid"""
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    def has_feature(self, feature: FeatureFlag) -> bool:
        """Check if license has specific feature"""
        return feature.value in self.features

    def days_until_expiry(self) -> Optional[int]:
        """Get days until license expires"""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.now()
        return max(0, delta.days)


@dataclass
class UsageMetrics:
    """Usage analytics metrics"""
    tests_run: int = 0
    devices_connected: int = 0
    screenshots_captured: int = 0
    api_calls_analyzed: int = 0
    ml_predictions: int = 0
    flow_discoveries: int = 0
    last_used: datetime = field(default_factory=datetime.now)
    session_count: int = 0
    total_runtime_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'tests_run': self.tests_run,
            'devices_connected': self.devices_connected,
            'screenshots_captured': self.screenshots_captured,
            'api_calls_analyzed': self.api_calls_analyzed,
            'ml_predictions': self.ml_predictions,
            'flow_discoveries': self.flow_discoveries,
            'last_used': self.last_used.isoformat(),
            'session_count': self.session_count,
            'total_runtime_hours': self.total_runtime_hours
        }


class LicenseManager:
    """
    Enhanced License Manager

    Manages license validation, feature gates, and usage tracking
    """

    def __init__(self, license_file: Optional[Path] = None):
        self.license_file = license_file or Path.home() / '.observe' / 'license.json'
        self.metrics_file = Path.home() / '.observe' / 'metrics.json'
        self.license: Optional[License] = None
        self.metrics = UsageMetrics()

        # Feature mapping per tier
        self.tier_features = {
            LicenseTier.FREE: [
                FeatureFlag.CORE_ENGINE,
                FeatureFlag.LOCAL_DEVICES,
                FeatureFlag.BASIC_TEST_GEN,
                FeatureFlag.SELF_HEALING,
                FeatureFlag.FLOW_DISCOVERY,
                FeatureFlag.ML_INFERENCE,
            ],
            LicenseTier.PRO: [
                # All FREE features +
                FeatureFlag.CLOUD_DEVICES,
                FeatureFlag.PARALLEL_EXECUTION,
                FeatureFlag.ADVANCED_ML,
                FeatureFlag.API_MOCKING,
                FeatureFlag.LOAD_TESTING,
                FeatureFlag.PRIORITY_SUPPORT,
            ],
            LicenseTier.ENTERPRISE: [
                # All PRO features +
                FeatureFlag.ML_TRAINING,
                FeatureFlag.CUSTOM_MODELS,
                FeatureFlag.DISTRIBUTED_EXECUTION,
                FeatureFlag.SSO_LDAP,
                FeatureFlag.ON_PREMISE,
                FeatureFlag.DEDICATED_SUPPORT,
                FeatureFlag.SECURITY_SCANNING,
                FeatureFlag.PERFORMANCE_PROFILING,
            ],
        }

        self._load_license()
        self._load_metrics()

    def _load_license(self):
        """Load license from file"""
        if not self.license_file.exists():
            # Create FREE tier license
            self.license = self._create_free_license()
            return

        try:
            with open(self.license_file, 'r') as f:
                data = json.load(f)

            self.license = License(
                tier=LicenseTier(data['tier']),
                email=data['email'],
                organization=data.get('organization'),
                license_key=data['license_key'],
                issued_at=datetime.fromisoformat(data['issued_at']),
                expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None,
                max_users=data.get('max_users', 1),
                max_devices=data.get('max_devices', 5),
                features=data.get('features', []),
                metadata=data.get('metadata', {})
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            self.license = self._create_free_license()

    def _load_metrics(self):
        """Load usage metrics"""
        if not self.metrics_file.exists():
            return

        try:
            with open(self.metrics_file, 'r') as f:
                data = json.load(f)

            self.metrics = UsageMetrics(
                tests_run=data.get('tests_run', 0),
                devices_connected=data.get('devices_connected', 0),
                screenshots_captured=data.get('screenshots_captured', 0),
                api_calls_analyzed=data.get('api_calls_analyzed', 0),
                ml_predictions=data.get('ml_predictions', 0),
                flow_discoveries=data.get('flow_discoveries', 0),
                last_used=datetime.fromisoformat(data['last_used']) if data.get('last_used') else datetime.now(),
                session_count=data.get('session_count', 0),
                total_runtime_hours=data.get('total_runtime_hours', 0.0)
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass

    def _create_free_license(self) -> License:
        """Create FREE tier license"""
        free_features = [f.value for f in self.tier_features[LicenseTier.FREE]]

        return License(
            tier=LicenseTier.FREE,
            email="",
            license_key="FREE",
            features=free_features,
            max_users=1,
            max_devices=5
        )

    def save_license(self):
        """Save license to file"""
        if not self.license:
            return

        self.license_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'tier': self.license.tier.value,
            'email': self.license.email,
            'organization': self.license.organization,
            'license_key': self.license.license_key,
            'issued_at': self.license.issued_at.isoformat(),
            'expires_at': self.license.expires_at.isoformat() if self.license.expires_at else None,
            'max_users': self.license.max_users,
            'max_devices': self.license.max_devices,
            'features': self.license.features,
            'metadata': self.license.metadata
        }

        with open(self.license_file, 'w') as f:
            json.dump(data, f, indent=2)

    def save_metrics(self):
        """Save usage metrics"""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.metrics_file, 'w') as f:
            json.dump(self.metrics.to_dict(), f, indent=2)

    def check_feature(self, feature: FeatureFlag) -> bool:
        """Check if feature is available in current license"""
        if not self.license or not self.license.is_valid():
            return feature in self.tier_features[LicenseTier.FREE]

        return self.license.has_feature(feature)

    def require_feature(self, feature: FeatureFlag, feature_name: str = ""):
        """Require feature or raise exception with upgrade prompt"""
        if self.check_feature(feature):
            return

        # Determine required tier
        required_tier = None
        for tier, features in self.tier_features.items():
            if feature in features:
                required_tier = tier
                break

        if not required_tier:
            raise PermissionError(f"Feature '{feature.value}' not available")

        # Show upgrade prompt
        self._show_upgrade_prompt(feature_name or feature.value, required_tier)

        raise PermissionError(f"{feature_name or feature.value} requires {required_tier.value.upper()} license")

    def _show_upgrade_prompt(self, feature_name: str, required_tier: LicenseTier):
        """Show informative upgrade prompt"""
        print()
        print(f"⚡ {feature_name.replace('_', ' ').title()} is a {required_tier.value.upper()} feature")
        print()

        if required_tier == LicenseTier.PRO:
            print("💎 Upgrade to PRO:")
            print("   • Cloud device integration")
            print("   • Parallel test execution")
            print("   • Advanced ML features")
            print("   • API mocking")
            print("   • Priority email support")
            print()
            print("   Price: $49/month or $499/year (save 15%)")
            print("   🎁 7-day free trial available!")
        elif required_tier == LicenseTier.ENTERPRISE:
            print("🏢 Upgrade to ENTERPRISE:")
            print("   • ML model training")
            print("   • Custom models")
            print("   • Distributed execution")
            print("   • SSO & LDAP integration")
            print("   • On-premise deployment")
            print("   • Dedicated support & SLA")
            print()
            print("   Contact sales for pricing")

        print()
        print("   Upgrade: observe upgrade --trial")
        print("   Or visit: https://yoursite.com/pricing")
        print()

    def track_usage(self, metric_name: str, increment: int = 1):
        """Track usage metric"""
        if metric_name == 'tests_run':
            self.metrics.tests_run += increment
        elif metric_name == 'devices_connected':
            self.metrics.devices_connected += increment
        elif metric_name == 'screenshots':
            self.metrics.screenshots_captured += increment
        elif metric_name == 'api_calls':
            self.metrics.api_calls_analyzed += increment
        elif metric_name == 'ml_predictions':
            self.metrics.ml_predictions += increment
        elif metric_name == 'flow_discoveries':
            self.metrics.flow_discoveries += increment
        elif metric_name == 'session':
            self.metrics.session_count += increment

        self.metrics.last_used = datetime.now()
        self.save_metrics()

    def get_license_info(self) -> Dict[str, Any]:
        """Get license information"""
        if not self.license:
            return {'tier': 'FREE', 'valid': False}

        return {
            'tier': self.license.tier.value,
            'valid': self.license.is_valid(),
            'email': self.license.email,
            'organization': self.license.organization,
            'expires_at': self.license.expires_at.isoformat() if self.license.expires_at else None,
            'days_until_expiry': self.license.days_until_expiry(),
            'max_users': self.license.max_users,
            'max_devices': self.license.max_devices,
            'features': self.license.features
        }

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics"""
        return self.metrics.to_dict()

    def activate_license(self, license_key: str, email: str) -> bool:
        """Activate license with key"""
        # In production, this would validate with license server
        # For now, simple validation

        if not license_key or not email:
            return False

        # Determine tier from key format
        tier = LicenseTier.FREE
        if license_key.startswith('PRO-'):
            tier = LicenseTier.PRO
        elif license_key.startswith('ENT-'):
            tier = LicenseTier.ENTERPRISE
        elif license_key.startswith('TRIAL-'):
            tier = LicenseTier.TRIAL

        # Create license - include features from all lower tiers
        features = []
        tier_hierarchy = [LicenseTier.FREE, LicenseTier.PRO, LicenseTier.ENTERPRISE]
        tier_index = tier_hierarchy.index(tier) if tier in tier_hierarchy else 0
        for t in tier_hierarchy[: tier_index + 1]:
            if t in self.tier_features:
                features.extend([f.value for f in self.tier_features[t]])

        self.license = License(
            tier=tier,
            email=email,
            license_key=license_key,
            features=list(set(features)),  # Remove duplicates
            expires_at=datetime.now() + timedelta(days=365) if tier != LicenseTier.FREE else None
        )

        self.save_license()
        return True


class FeatureGate:
    """
    Decorator for feature gating

    Usage:
        @FeatureGate(FeatureFlag.CLOUD_DEVICES, "Cloud Devices")
        def connect_cloud_device():
            pass
    """

    def __init__(self, feature: FeatureFlag, feature_name: str = ""):
        self.feature = feature
        self.feature_name = feature_name
        self._manager = LicenseManager()

    def __call__(self, func: Callable) -> Callable:
        """Decorator wrapper"""

        def wrapper(*args, **kwargs):
            self._manager.require_feature(self.feature, self.feature_name)
            return func(*args, **kwargs)

        return wrapper


# Global license manager instance
_license_manager = None


def get_license_manager() -> LicenseManager:
    """Get global license manager instance"""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager


def check_feature(feature_name: str) -> bool:
    """
    Check if feature is available

    Backward compatible with existing code
    """
    manager = get_license_manager()

    # Map string names to FeatureFlag enum
    feature_map = {
        'cloud_devices': FeatureFlag.CLOUD_DEVICES,
        'parallel_execution': FeatureFlag.PARALLEL_EXECUTION,
        'ml_healing': FeatureFlag.ADVANCED_ML,
        'ml_training': FeatureFlag.ML_TRAINING,
        'api_mocking': FeatureFlag.API_MOCKING,
        'security_scanning': FeatureFlag.SECURITY_SCANNING,
        'performance_profiling': FeatureFlag.PERFORMANCE_PROFILING,
    }

    feature_flag = feature_map.get(feature_name)
    if not feature_flag:
        return True  # Unknown features are allowed

    return manager.check_feature(feature_flag)


def track_usage(metric: str, increment: int = 1):
    """Track usage metric"""
    manager = get_license_manager()
    manager.track_usage(metric, increment)
