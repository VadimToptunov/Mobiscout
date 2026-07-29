"""
Runtime Protection Analyzer

Analyzes runtime security protections and detection mechanisms.

Features:
- Anti-tampering detection analysis
- Anti-debugging protection analysis
- Root/Jailbreak detection analysis
- Emulator detection analysis
- Code integrity verification
- Memory protection analysis
- Hooking detection analysis
- Frida/Xposed detection analysis
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar, Dict, Any, List, Tuple


class ProtectionCategory(Enum):
    """Protection categories"""

    ROOT_DETECTION = "root_detection"
    JAILBREAK_DETECTION = "jailbreak_detection"
    EMULATOR_DETECTION = "emulator_detection"
    DEBUG_DETECTION = "debug_detection"
    TAMPER_DETECTION = "tamper_detection"
    HOOK_DETECTION = "hook_detection"
    FRIDA_DETECTION = "frida_detection"
    MEMORY_PROTECTION = "memory_protection"
    CODE_INTEGRITY = "code_integrity"
    SSL_PINNING = "ssl_pinning"
    OBFUSCATION = "obfuscation"


class ImplementationQuality(Enum):
    """Protection implementation quality"""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


@dataclass
class ProtectionIndicator:
    """A protection indicator found in code"""

    category: ProtectionCategory
    indicator: str
    location: str
    line_number: int
    description: str
    bypass_difficulty: str  # easy, moderate, hard


@dataclass
class ProtectionAnalysis:
    """Protection analysis result"""

    category: ProtectionCategory
    implemented: bool
    quality: ImplementationQuality
    indicators: List[ProtectionIndicator]
    recommendations: List[str]
    score: float  # 0-100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "implemented": self.implemented,
            "quality": self.quality.value,
            "indicators": [
                {
                    "indicator": i.indicator,
                    "location": i.location,
                    "line": i.line_number,
                    "description": i.description,
                    "bypass_difficulty": i.bypass_difficulty,
                }
                for i in self.indicators
            ],
            "recommendations": self.recommendations,
            "score": self.score,
        }


@dataclass
class ProtectionStatus:
    """Status of a specific protection mechanism - for CLI compatibility"""

    detected: bool = False
    strength: str = "none"  # strong, medium, weak, none
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "strength": self.strength,
            "details": self.details,
        }


@dataclass
class BypassMethod:
    """Potential bypass method"""

    method: str
    description: str
    difficulty: str  # easy, moderate, hard

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "description": self.description,
            "difficulty": self.difficulty,
        }


@dataclass
class RuntimeProtectionResult:
    """Complete runtime protection analysis result - for CLI compatibility"""

    root_detection: ProtectionStatus = field(default_factory=ProtectionStatus)
    emulator_detection: ProtectionStatus = field(default_factory=ProtectionStatus)
    debug_detection: ProtectionStatus = field(default_factory=ProtectionStatus)
    tamper_detection: ProtectionStatus = field(default_factory=ProtectionStatus)
    hook_detection: ProtectionStatus = field(default_factory=ProtectionStatus)
    ssl_pinning: ProtectionStatus = field(default_factory=ProtectionStatus)
    obfuscation: ProtectionStatus = field(default_factory=ProtectionStatus)
    recommendations: List[str] = field(default_factory=list)
    bypass_methods: List[BypassMethod] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_detection": self.root_detection.to_dict(),
            "emulator_detection": self.emulator_detection.to_dict(),
            "debug_detection": self.debug_detection.to_dict(),
            "tamper_detection": self.tamper_detection.to_dict(),
            "hook_detection": self.hook_detection.to_dict(),
            "ssl_pinning": self.ssl_pinning.to_dict(),
            "obfuscation": self.obfuscation.to_dict(),
            "recommendations": self.recommendations,
            "bypass_methods": [b.to_dict() for b in self.bypass_methods],
            "score": self.score,
        }


@dataclass
class QuickCheckResult:
    """Quick protection check result - for CLI compatibility"""

    has_root_detection: bool = False
    has_emulator_detection: bool = False
    has_debug_detection: bool = False
    has_tamper_detection: bool = False
    has_ssl_pinning: bool = False
    has_obfuscation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_root_detection": self.has_root_detection,
            "has_emulator_detection": self.has_emulator_detection,
            "has_debug_detection": self.has_debug_detection,
            "has_tamper_detection": self.has_tamper_detection,
            "has_ssl_pinning": self.has_ssl_pinning,
            "has_obfuscation": self.has_obfuscation,
        }


class BaseProtectionAnalyzer:
    """Shared source-scanning logic for the platform protection analyzers.

    ``_find_patterns`` and ``_analyze_category`` were byte-identical in the
    Android and iOS analyzers; they live here now. Subclasses only declare the
    source file ``EXTENSIONS`` they scan plus their own pattern dicts and
    recommendations, and implement ``analyze_source``.
    """

    # File extensions a subclass scans; overridden per platform.
    EXTENSIONS: ClassVar[List[str]] = []

    def _find_patterns(
        self, source_dir: Path, patterns: Dict[str, Tuple[str, str]], category: ProtectionCategory
    ) -> List[ProtectionIndicator]:
        """Find protection patterns in source code."""
        indicators = []

        for ext in self.EXTENSIONS:
            for file_path in source_dir.rglob(f"*{ext}"):
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()

                    for pattern, (desc, difficulty) in patterns.items():
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                indicators.append(
                                    ProtectionIndicator(
                                        category=category,
                                        indicator=pattern,
                                        location=str(file_path),
                                        line_number=i,
                                        description=desc,
                                        bypass_difficulty=difficulty,
                                    )
                                )
                except (OSError, UnicodeDecodeError):
                    pass

        return indicators

    def _analyze_category(
        self, category: ProtectionCategory, indicators: List[ProtectionIndicator], recommendations: List[str]
    ) -> ProtectionAnalysis:
        """Analyze a protection category."""
        if not indicators:
            return ProtectionAnalysis(
                category=category,
                implemented=False,
                quality=ImplementationQuality.NONE,
                indicators=[],
                recommendations=recommendations,
                score=0.0,
            )

        # Calculate quality based on bypass difficulty
        hard_count = len([i for i in indicators if i.bypass_difficulty == "hard"])
        moderate_count = len([i for i in indicators if i.bypass_difficulty == "moderate"])
        easy_count = len([i for i in indicators if i.bypass_difficulty == "easy"])

        total = len(indicators)
        weighted_score = (hard_count * 3 + moderate_count * 2 + easy_count) / (total * 3) * 100

        if weighted_score >= 70:
            quality = ImplementationQuality.STRONG
        elif weighted_score >= 40:
            quality = ImplementationQuality.MODERATE
        else:
            quality = ImplementationQuality.WEAK

        # Filter recommendations to what's not implemented
        remaining_recommendations = recommendations[:3] if quality == ImplementationQuality.WEAK else []

        return ProtectionAnalysis(
            category=category,
            implemented=True,
            quality=quality,
            indicators=indicators,
            recommendations=remaining_recommendations,
            score=weighted_score,
        )
