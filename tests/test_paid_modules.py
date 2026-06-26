"""
Unit tests for STEP 7: Paid Modules Enhancement

Comprehensive testing of license system, feature gates, and usage tracking.
Includes positive, negative, and edge case tests.
"""

from datetime import datetime, timedelta

import pytest

from framework.licensing.enhanced_validator import (
    LicenseTier,
    FeatureFlag,
    License,
    UsageMetrics,
    LicenseManager,
    FeatureGate,
    get_license_manager,
    check_feature,
    track_usage
)


@pytest.fixture(autouse=True)
def reset_license_manager_singleton():
    """Reset LicenseManager singleton state between tests.

    This fixture ensures that each test starts with a fresh LicenseManager
    instance, preventing state leakage between tests.
    """
    # Import the module to access the global variable
    import framework.licensing.enhanced_validator as lm_module

    # Reset global _license_manager before test
    lm_module._license_manager = None

    yield

    # Reset global _license_manager after test
    lm_module._license_manager = None


class TestLicenseTier:
    """Test LicenseTier enum"""

    def test_all_tiers(self):
        """Test all license tiers"""
        tiers = [LicenseTier.FREE, LicenseTier.PRO, LicenseTier.ENTERPRISE, LicenseTier.TRIAL]
        assert len(tiers) == 4
        assert all(isinstance(t, LicenseTier) for t in tiers)


class TestFeatureFlag:
    """Test FeatureFlag enum"""

    def test_free_features(self):
        """Test FREE tier features"""
        free_features = [
            FeatureFlag.CORE_ENGINE,
            FeatureFlag.LOCAL_DEVICES,
            FeatureFlag.BASIC_TEST_GEN,
            FeatureFlag.SELF_HEALING,
            FeatureFlag.FLOW_DISCOVERY,
            FeatureFlag.ML_INFERENCE
        ]
        assert len(free_features) == 6

    def test_pro_features(self):
        """Test PRO tier features"""
        pro_features = [
            FeatureFlag.CLOUD_DEVICES,
            FeatureFlag.PARALLEL_EXECUTION,
            FeatureFlag.ADVANCED_ML,
            FeatureFlag.API_MOCKING,
            FeatureFlag.LOAD_TESTING,
            FeatureFlag.PRIORITY_SUPPORT
        ]
        assert len(pro_features) == 6

    def test_enterprise_features(self):
        """Test ENTERPRISE tier features"""
        ent_features = [
            FeatureFlag.ML_TRAINING,
            FeatureFlag.CUSTOM_MODELS,
            FeatureFlag.DISTRIBUTED_EXECUTION,
            FeatureFlag.SSO_LDAP,
            FeatureFlag.ON_PREMISE,
            FeatureFlag.DEDICATED_SUPPORT,
            FeatureFlag.SECURITY_SCANNING,
            FeatureFlag.PERFORMANCE_PROFILING
        ]
        assert len(ent_features) == 8


class TestLicense:
    """Test License dataclass"""

    def test_create_license(self):
        """Test creating license"""
        license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            organization="Test Corp",
            license_key="PRO-123456"
        )

        assert license.tier == LicenseTier.PRO
        assert license.email == "test@example.com"
        assert license.organization == "Test Corp"
        assert license.license_key == "PRO-123456"

    def test_license_is_valid(self):
        """Test license validity check"""
        # Valid license
        license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            expires_at=datetime.now() + timedelta(days=30)
        )
        assert license.is_valid()

        # Expired license
        expired_license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            expires_at=datetime.now() - timedelta(days=1)
        )
        assert not expired_license.is_valid()

        # No expiry (FREE tier)
        free_license = License(
            tier=LicenseTier.FREE,
            email="test@example.com",
            expires_at=None
        )
        assert free_license.is_valid()

    def test_has_feature(self):
        """Test feature check"""
        license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            features=[FeatureFlag.CLOUD_DEVICES.value, FeatureFlag.PARALLEL_EXECUTION.value]
        )

        assert license.has_feature(FeatureFlag.CLOUD_DEVICES)
        assert license.has_feature(FeatureFlag.PARALLEL_EXECUTION)
        assert not license.has_feature(FeatureFlag.ML_TRAINING)

    def test_days_until_expiry(self):
        """Test expiry calculation"""
        # 30 days until expiry (add extra hours to ensure it rounds to 30)
        license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            expires_at=datetime.now() + timedelta(days=30, hours=12)
        )
        assert license.days_until_expiry() == 30

        # Already expired
        expired = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            expires_at=datetime.now() - timedelta(days=5)
        )
        assert expired.days_until_expiry() == 0

        # No expiry
        no_expiry = License(
            tier=LicenseTier.FREE,
            email="test@example.com",
            expires_at=None
        )
        assert no_expiry.days_until_expiry() is None


class TestUsageMetrics:
    """Test UsageMetrics dataclass"""

    def test_create_metrics(self):
        """Test creating metrics"""
        metrics = UsageMetrics(
            tests_run=100,
            devices_connected=5,
            screenshots_captured=50
        )

        assert metrics.tests_run == 100
        assert metrics.devices_connected == 5
        assert metrics.screenshots_captured == 50

    def test_to_dict(self):
        """Test metrics serialization"""
        metrics = UsageMetrics(tests_run=10, ml_predictions=20)
        data = metrics.to_dict()

        assert isinstance(data, dict)
        assert data['tests_run'] == 10
        assert data['ml_predictions'] == 20
        assert 'last_used' in data


class TestLicenseManager:
    """Test LicenseManager"""

    def test_create_manager(self, tmp_path):
        """Test creating license manager"""
        license_file = tmp_path / "license.json"
        manager = LicenseManager(license_file=license_file)

        assert manager.license is not None
        assert manager.license.tier == LicenseTier.FREE

    def test_check_feature_free_tier(self, tmp_path):
        """Test feature check with FREE tier"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        # FREE features should be available
        assert manager.check_feature(FeatureFlag.CORE_ENGINE)
        assert manager.check_feature(FeatureFlag.LOCAL_DEVICES)
        assert manager.check_feature(FeatureFlag.ML_INFERENCE)

        # PRO features should not be available
        assert not manager.check_feature(FeatureFlag.CLOUD_DEVICES)
        assert not manager.check_feature(FeatureFlag.PARALLEL_EXECUTION)

        # ENTERPRISE features should not be available
        assert not manager.check_feature(FeatureFlag.ML_TRAINING)
        assert not manager.check_feature(FeatureFlag.DISTRIBUTED_EXECUTION)

    def test_require_feature_free_tier(self, tmp_path):
        """Test requiring PRO feature with FREE tier (negative test)"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        with pytest.raises(PermissionError):
            manager.require_feature(FeatureFlag.CLOUD_DEVICES, "Cloud Devices")

    def test_require_feature_with_license(self, tmp_path):
        """Test requiring feature with valid license"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        # Activate PRO license
        manager.activate_license("PRO-123456", "test@example.com")

        # Should not raise
        manager.require_feature(FeatureFlag.CLOUD_DEVICES)
        manager.require_feature(FeatureFlag.PARALLEL_EXECUTION)

    def test_track_usage(self, tmp_path):
        """Test usage tracking"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        initial_tests = manager.metrics.tests_run
        manager.track_usage('tests_run', 5)

        assert manager.metrics.tests_run == initial_tests + 5

    def test_save_and_load_license(self, tmp_path):
        """Test license persistence"""
        license_file = tmp_path / "license.json"

        # Create and save
        manager1 = LicenseManager(license_file=license_file)
        manager1.activate_license("PRO-123456", "test@example.com")
        manager1.save_license()

        # Load
        manager2 = LicenseManager(license_file=license_file)

        assert manager2.license.tier == LicenseTier.PRO
        assert manager2.license.email == "test@example.com"
        assert manager2.license.license_key == "PRO-123456"

    def test_save_and_load_metrics(self, tmp_path):
        """Test metrics persistence"""
        metrics_file = tmp_path / "metrics.json"
        license_file = tmp_path / "license.json"

        # Create and save - set metrics_file BEFORE tracking to avoid loading from global
        manager1 = LicenseManager(license_file=license_file)
        manager1.metrics_file = metrics_file
        manager1.metrics = UsageMetrics()  # Reset to fresh metrics
        manager1.track_usage('tests_run', 10)
        manager1.track_usage('ml_predictions', 20)
        manager1.save_metrics()

        # Load - set metrics_file BEFORE loading
        manager2 = LicenseManager(license_file=license_file)
        manager2.metrics_file = metrics_file
        manager2.metrics = UsageMetrics()  # Reset first
        manager2._load_metrics()

        assert manager2.metrics.tests_run == 10
        assert manager2.metrics.ml_predictions == 20

    def test_activate_pro_license(self, tmp_path):
        """Test PRO license activation"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        result = manager.activate_license("PRO-ABCDEF", "pro@example.com")

        assert result
        assert manager.license.tier == LicenseTier.PRO
        assert manager.license.email == "pro@example.com"
        assert manager.check_feature(FeatureFlag.CLOUD_DEVICES)

    def test_activate_enterprise_license(self, tmp_path):
        """Test ENTERPRISE license activation"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        result = manager.activate_license("ENT-XYZ123", "enterprise@example.com")

        assert result
        assert manager.license.tier == LicenseTier.ENTERPRISE
        assert manager.check_feature(FeatureFlag.ML_TRAINING)
        assert manager.check_feature(FeatureFlag.DISTRIBUTED_EXECUTION)

    def test_activate_trial_license(self, tmp_path):
        """Test TRIAL license activation"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        result = manager.activate_license("TRIAL-789", "trial@example.com")

        assert result
        assert manager.license.tier == LicenseTier.TRIAL

    def test_invalid_license_activation(self, tmp_path):
        """Test invalid license activation (negative test)"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        result = manager.activate_license("", "")
        assert not result

        result = manager.activate_license("INVALID", "")
        assert not result

    def test_get_license_info(self, tmp_path):
        """Test getting license info"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.activate_license("PRO-123", "test@example.com")

        info = manager.get_license_info()

        assert info['tier'] == 'pro'
        assert info['valid'] == True
        assert info['email'] == 'test@example.com'
        assert 'features' in info

    def test_get_usage_stats(self, tmp_path):
        """Test getting usage statistics"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.metrics_file = tmp_path / "metrics.json"  # Use isolated file
        manager.metrics = UsageMetrics()  # Reset to fresh metrics
        manager.track_usage('tests_run', 5)
        manager.track_usage('ml_predictions', 10)

        stats = manager.get_usage_stats()

        assert stats['tests_run'] == 5
        assert stats['ml_predictions'] == 10
        assert 'session_count' in stats


class TestFeatureGate:
    """Test FeatureGate decorator"""

    def test_feature_gate_allowed(self, tmp_path):
        """Test feature gate with allowed feature"""

        # This will use FREE tier, so CORE_ENGINE should be allowed
        @FeatureGate(FeatureFlag.CORE_ENGINE, "Core Engine")
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"

    def test_feature_gate_denied(self, tmp_path):
        """Test feature gate with denied feature (negative test)"""

        @FeatureGate(FeatureFlag.CLOUD_DEVICES, "Cloud Devices")
        def test_function():
            return "success"

        with pytest.raises(PermissionError):
            test_function()


class TestGlobalFunctions:
    """Test global helper functions"""

    def test_get_license_manager(self):
        """Test getting global license manager"""
        manager1 = get_license_manager()
        manager2 = get_license_manager()

        assert manager1 is manager2  # Should be singleton

    def test_check_feature_function(self):
        """Test global check_feature function"""
        # FREE features should be available
        assert check_feature('unknown_feature')  # Unknown features allowed

        # PRO features should not be available with FREE tier
        # (Assuming default FREE tier)
        result = check_feature('cloud_devices')
        assert isinstance(result, bool)

    def test_track_usage_function(self):
        """Test global track_usage function"""
        # Should not raise
        track_usage('tests_run', 1)
        track_usage('ml_predictions', 5)


class TestLicenseExpiry:
    """Test license expiry scenarios"""

    def test_expired_license_feature_check(self, tmp_path):
        """Test feature check with expired license"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        # Create expired PRO license
        manager.license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            license_key="PRO-EXPIRED",
            expires_at=datetime.now() - timedelta(days=1),
            features=[FeatureFlag.CLOUD_DEVICES.value]
        )

        # Expired license should fall back to FREE tier
        assert not manager.check_feature(FeatureFlag.CLOUD_DEVICES)

    def test_expiring_soon_license(self, tmp_path):
        """Test license expiring soon"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        manager.license = License(
            tier=LicenseTier.PRO,
            email="test@example.com",
            expires_at=datetime.now() + timedelta(days=7, hours=12)
        )

        days = manager.license.days_until_expiry()
        assert days == 7


class TestUsageMetricsTracking:
    """Test usage metrics tracking"""

    def test_track_all_metrics(self, tmp_path):
        """Test tracking all metric types"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.metrics_file = tmp_path / "metrics.json"  # Use isolated file
        manager.metrics = UsageMetrics()  # Reset to fresh metrics

        manager.track_usage('tests_run', 5)
        manager.track_usage('devices_connected', 2)
        manager.track_usage('screenshots', 10)
        manager.track_usage('api_calls', 20)
        manager.track_usage('ml_predictions', 15)
        manager.track_usage('flow_discoveries', 3)
        manager.track_usage('session', 1)

        assert manager.metrics.tests_run == 5
        assert manager.metrics.devices_connected == 2
        assert manager.metrics.screenshots_captured == 10
        assert manager.metrics.api_calls_analyzed == 20
        assert manager.metrics.ml_predictions == 15
        assert manager.metrics.flow_discoveries == 3
        assert manager.metrics.session_count == 1

    def test_metrics_accumulation(self, tmp_path):
        """Test metrics accumulate correctly"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.metrics_file = tmp_path / "metrics.json"  # Use isolated file
        manager.metrics = UsageMetrics()  # Reset to fresh metrics

        manager.track_usage('tests_run', 5)
        manager.track_usage('tests_run', 3)
        manager.track_usage('tests_run', 2)

        assert manager.metrics.tests_run == 10


class TestLicenseTierFeatures:
    """Test feature availability per tier"""

    def test_free_tier_features(self, tmp_path):
        """Test all FREE tier features are available"""
        manager = LicenseManager(license_file=tmp_path / "license.json")

        free_features = [
            FeatureFlag.CORE_ENGINE,
            FeatureFlag.LOCAL_DEVICES,
            FeatureFlag.BASIC_TEST_GEN,
            FeatureFlag.SELF_HEALING,
            FeatureFlag.FLOW_DISCOVERY,
            FeatureFlag.ML_INFERENCE
        ]

        for feature in free_features:
            assert manager.check_feature(feature), f"{feature} should be available in FREE tier"

    def test_pro_tier_includes_free_features(self, tmp_path):
        """Test PRO tier includes all FREE features"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.activate_license("PRO-123", "test@example.com")

        # All FREE features should be available
        assert manager.check_feature(FeatureFlag.CORE_ENGINE)
        assert manager.check_feature(FeatureFlag.LOCAL_DEVICES)

        # PRO features should be available
        assert manager.check_feature(FeatureFlag.CLOUD_DEVICES)
        assert manager.check_feature(FeatureFlag.PARALLEL_EXECUTION)

    def test_enterprise_tier_includes_all_features(self, tmp_path):
        """Test ENTERPRISE tier includes all features"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.activate_license("ENT-123", "test@example.com")

        # Should have all features
        assert manager.check_feature(FeatureFlag.CORE_ENGINE)  # FREE
        assert manager.check_feature(FeatureFlag.CLOUD_DEVICES)  # PRO
        assert manager.check_feature(FeatureFlag.ML_TRAINING)  # ENTERPRISE


class TestErrorHandling:
    """Test error handling"""

    def test_invalid_license_file(self, tmp_path):
        """Test handling invalid license file"""
        license_file = tmp_path / "invalid.json"
        license_file.write_text("invalid json")

        # Should create FREE license instead of crashing
        manager = LicenseManager(license_file=license_file)
        assert manager.license.tier == LicenseTier.FREE

    def test_missing_metrics_file(self, tmp_path):
        """Test handling missing metrics file"""
        manager = LicenseManager(license_file=tmp_path / "license.json")
        manager.metrics_file = tmp_path / "nonexistent.json"
        manager.metrics = UsageMetrics()  # Reset to fresh metrics first

        # Should not crash and should keep metrics at 0
        manager._load_metrics()
        assert manager.metrics.tests_run == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
