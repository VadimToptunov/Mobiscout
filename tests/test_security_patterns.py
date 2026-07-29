"""Tests for the canonical secret / PII pattern registry.

These lock in the item-1 de-duplication: the six historical pattern sets now
resolve through ``framework.security.patterns``. Coverage:

- the canonical union exposes every caller group with its exact category labels;
- the email class is fixed (``[A-Za-z]``, never the buggy ``[A-Z|a-z]``) and is
  shared verbatim by the two callers that carried the bug;
- the placeholder / false-positive helpers behave (word-boundary token match,
  structural placeholders, exact-value placeholders);
- each consumer module reads the shared constants rather than a private copy.
"""

import re

from framework.security import patterns
from framework.security.dast.traffic import NetworkTrafficAnalyzer
from framework.security.decompile.apk import APKDecompiler
from framework.security.advanced.secrets import HardcodedSecretsScanner


# --------------------------------------------------------------------------- #
# The email bug fix
# --------------------------------------------------------------------------- #
class TestEmailPattern:
    def test_canonical_email_uses_fixed_character_class(self):
        # The historical class ``[A-Z|a-z]`` also matched a literal '|'.
        assert "[A-Z|a-z]" not in patterns.EMAIL
        assert "[A-Za-z]{2,}" in patterns.EMAIL

    def test_matches_realistic_emails(self):
        for addr in ("jane.doe@example.co.uk", "user+tag@sub.domain.com", "a@b.io"):
            assert re.search(patterns.EMAIL, f"contact {addr} now"), addr

    def test_no_module_still_carries_the_buggy_class(self):
        # The two callers that had the bug now share the single fixed constant.
        assert patterns.DAST_SENSITIVE_PATTERNS["email"] is patterns.EMAIL
        assert patterns.EXTRACT_STRING_PATTERNS["email"] is patterns.EMAIL

    def test_formerly_missed_email_now_detected_by_dast(self):
        # A body containing only an email (the previously buggy-classed pattern)
        # is now uniformly detected via the canonical set.
        analyzer = NetworkTrafficAnalyzer()
        assert re.search(analyzer.SENSITIVE_PATTERNS["email"], "reach me at first.last@corp.example.org")


# --------------------------------------------------------------------------- #
# Union completeness — every caller group is present and correctly shaped
# --------------------------------------------------------------------------- #
class TestUnionGroups:
    def test_scanner_group_labels(self):
        assert set(patterns.SCANNER_SECRET_PATTERNS) == {"API Key", "AWS Key", "Private Key", "Password"}

    def test_config_group_labels(self):
        assert set(patterns.CONFIG_SECRET_PATTERNS) == {
            "Potential API Key",
            "Potential AWS Key",
            "Potential Private Key",
            "Hardcoded Password",
            "Potential Token",
        }

    def test_decompile_group_labels(self):
        assert set(patterns.DECOMPILE_SENSITIVE_PATTERNS) == {
            "url",
            "ip_address",
            "api_key",
            "aws_key",
            "google_api",
            "firebase",
            "password",
            "private_key",
            "jwt",
            "sql_query",
        }

    def test_extract_and_dast_groups_present(self):
        assert set(patterns.EXTRACT_STRING_PATTERNS) == {"url", "ip_address", "api_key", "email", "password", "token"}
        assert set(patterns.DAST_SENSITIVE_PATTERNS) == {
            "credit_card",
            "ssn",
            "email",
            "api_key",
            "jwt",
            "password_in_url",
            "bearer_token",
        }

    def test_shared_atoms_deduplicated(self):
        # The AWS AKIA key and the URL/IP atoms are the same object across groups.
        assert patterns.SCANNER_SECRET_PATTERNS["AWS Key"] is patterns.AWS_ACCESS_KEY_ID
        assert patterns.CONFIG_SECRET_PATTERNS["Potential AWS Key"] is patterns.AWS_ACCESS_KEY_ID
        assert patterns.DECOMPILE_SENSITIVE_PATTERNS["aws_key"] is patterns.AWS_ACCESS_KEY_ID
        assert patterns.DECOMPILE_SENSITIVE_PATTERNS["url"] is patterns.EXTRACT_STRING_PATTERNS["url"]
        assert patterns.DECOMPILE_SENSITIVE_PATTERNS["jwt"] is patterns.DAST_SENSITIVE_PATTERNS["jwt"]

    def test_advanced_specs_cover_expected_names(self):
        names = {spec[0] for spec in patterns.ADVANCED_SECRET_SPECS}
        assert {"AWS Access Key ID", "GitHub Token", "Stripe API Key", "JWT Token", "RSA Private Key"} <= names
        # Every spec severity name is one the RiskLevel enum can resolve.
        assert {spec[2] for spec in patterns.ADVANCED_SECRET_SPECS} <= {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


# --------------------------------------------------------------------------- #
# Detection still works over the union (a representative secret per group)
# --------------------------------------------------------------------------- #
class TestDetectionAcrossUnion:
    def test_aws_key_detected(self):
        assert re.search(patterns.AWS_ACCESS_KEY_ID, "AKIAIOSFODNN7EXAMPLE")

    def test_jwt_detected(self):
        assert re.search(patterns.JWT, "eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSMeKKF2QT4")

    def test_credit_card_and_ssn(self):
        assert re.search(patterns.CREDIT_CARD, "4111 1111 1111 1111")
        assert re.search(patterns.SSN, "123-45-6789")


# --------------------------------------------------------------------------- #
# Placeholder / false-positive helper
# --------------------------------------------------------------------------- #
class TestFalsePositiveHelper:
    def test_placeholder_value_exact_match(self):
        assert patterns.is_placeholder_value("changeme")
        assert patterns.is_placeholder_value("YOUR_PASSWORD".lower())
        assert not patterns.is_placeholder_value("aB3xYz9KpQ7mN2wL8vR4")

    def test_token_indicator_word_boundary(self):
        # "test" as a standalone token is a false positive...
        assert patterns.is_false_positive('api_key = "value"', "this is a test fixture")
        # ...but "latest"/"manifest"/"greatest" must NOT be treated as "test".
        assert not patterns.is_false_positive("secretvalue", "the latest greatest manifest")

    def test_structural_placeholders(self):
        assert patterns.is_false_positive("${SECRET}", "config = ${SECRET}")
        assert patterns.is_false_positive("<your-key>", "key: <your-key>")


# --------------------------------------------------------------------------- #
# Consumers read the shared constants (not a private copy)
# --------------------------------------------------------------------------- #
class TestConsumersWired:
    def test_apk_uses_canonical_group(self):
        assert APKDecompiler.SENSITIVE_PATTERNS is patterns.DECOMPILE_SENSITIVE_PATTERNS

    def test_dast_uses_canonical_group(self):
        assert NetworkTrafficAnalyzer.SENSITIVE_PATTERNS is patterns.DAST_SENSITIVE_PATTERNS

    def test_advanced_scanner_builds_from_specs(self):
        scanner = HardcodedSecretsScanner()
        built_names = {p.name for p in scanner.patterns}
        spec_names = {spec[0] for spec in patterns.ADVANCED_SECRET_SPECS}
        assert built_names == spec_names
        # FP method still delegates to the shared helper.
        assert scanner.is_false_positive('api_key = "x"', "test only")
        assert not scanner.is_false_positive("realsecret", "the latest manifest")
