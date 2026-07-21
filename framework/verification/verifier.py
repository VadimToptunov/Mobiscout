"""Backward-compatible aggregation of the verification package.

This module grew past 850 lines, so it was decomposed by responsibility into
cohesive submodules: :mod:`~framework.verification.base` (the verification
models and the ``LanguageVerifier`` ABC), one module per language
(``python_verifier``, ``kotlin_verifier``, …), and
:mod:`~framework.verification.multi_verifier` (the ``MultiLanguageVerifier``
orchestrator).

It re-exports the public names so existing imports
(``from framework.verification.verifier import ...``) keep working unchanged.
"""

from framework.verification.base import (
    LanguageVerifier,
    VerificationCategory,
    VerificationIssue,
    VerificationLevel,
    VerificationResult,
)
from framework.verification.go_verifier import GoVerifier
from framework.verification.javascript_verifier import JavaScriptVerifier
from framework.verification.kotlin_verifier import KotlinVerifier
from framework.verification.multi_verifier import MultiLanguageVerifier
from framework.verification.python_verifier import PythonVerifier
from framework.verification.ruby_verifier import RubyVerifier
from framework.verification.swift_verifier import SwiftVerifier

__all__ = [
    "MultiLanguageVerifier",
    "VerificationResult",
    "VerificationIssue",
    "VerificationLevel",
    "VerificationCategory",
    "LanguageVerifier",
    "PythonVerifier",
    "KotlinVerifier",
    "SwiftVerifier",
    "JavaScriptVerifier",
    "GoVerifier",
    "RubyVerifier",
]
