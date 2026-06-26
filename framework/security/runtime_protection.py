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

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set


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


class AndroidProtectionAnalyzer:
    """
    Android Runtime Protection Analyzer

    Analyzes Android apps for runtime protection mechanisms.
    """

    # Root detection patterns
    ROOT_DETECTION_PATTERNS = {
        # Binary checks
        r'/system/bin/su': ("su binary check", "easy"),
        r'/system/xbin/su': ("su binary check", "easy"),
        r'/sbin/su': ("su binary check", "easy"),
        r'which su': ("su path check", "easy"),

        # Package checks
        r'com\.noshufou\.android\.su': ("SuperSU package", "moderate"),
        r'com\.thirdparty\.superuser': ("Superuser package", "moderate"),
        r'eu\.chainfire\.supersu': ("SuperSU package", "moderate"),
        r'com\.koushikdutta\.superuser': ("Superuser package", "moderate"),
        r'com\.topjohnwu\.magisk': ("Magisk package", "moderate"),

        # Method patterns
        r'isRooted|checkRoot|detectRoot': ("Root detection method", "moderate"),
        r'RootBeer|RootChecker': ("Root detection library", "hard"),
        r'SafetyNet': ("SafetyNet attestation", "hard"),

        # File checks
        r'/system/app/Superuser': ("Superuser app check", "easy"),
        r'/data/local/bin/su': ("Local su check", "easy"),
    }

    # Emulator detection patterns
    EMULATOR_DETECTION_PATTERNS = {
        r'generic': ("Generic device check", "easy"),
        r'goldfish': ("Goldfish check", "easy"),
        r'vbox86': ("VirtualBox check", "moderate"),
        r'genymotion': ("Genymotion check", "moderate"),
        r'sdk_google': ("SDK image check", "easy"),
        r'Andy|BlueStacks|Nox': ("Known emulator check", "moderate"),
        r'isEmulator|detectEmulator': ("Emulator detection method", "moderate"),
        r'Build\.FINGERPRINT': ("Fingerprint analysis", "moderate"),
        r'Build\.HARDWARE': ("Hardware analysis", "moderate"),
        r'/dev/qemu_pipe': ("QEMU pipe check", "hard"),
        r'/dev/socket/qemud': ("QEMU socket check", "hard"),
    }

    # Debug detection patterns
    DEBUG_DETECTION_PATTERNS = {
        r'Debug\.isDebuggerConnected': ("Debugger check", "easy"),
        r'isDebuggerConnected': ("Debugger check", "easy"),
        r'waitForDebugger': ("Debugger wait", "easy"),
        r'android:debuggable': ("Debuggable flag", "easy"),
        r'JDWP': ("JDWP detection", "moderate"),
        r'/proc/self/status.*TracerPid': ("TracerPid check", "hard"),
        r'ptrace': ("Ptrace detection", "hard"),
    }

    # Frida/Hook detection patterns
    FRIDA_DETECTION_PATTERNS = {
        r'frida': ("Frida string", "easy"),
        r'libfrida': ("Frida library", "moderate"),
        r'27042': ("Frida default port", "moderate"),
        r'/data/local/tmp': ("Frida injection path", "moderate"),
        r'xposed': ("Xposed detection", "moderate"),
        r'de\.robv\.android\.xposed': ("Xposed package", "moderate"),
        r'substrate': ("Substrate detection", "moderate"),
        r'cydia\.substrate': ("Substrate package", "moderate"),
    }

    # Tamper detection patterns
    TAMPER_DETECTION_PATTERNS = {
        r'PackageManager\.GET_SIGNATURES': ("Signature check", "moderate"),
        r'getSigningInfo': ("Signing info check", "moderate"),
        r'checkSignature': ("Signature verification", "moderate"),
        r'CRC32|checksum': ("Checksum verification", "hard"),
        r'dexFile\.loadDex': ("DEX loading check", "hard"),
        r'classes\.dex': ("DEX file check", "moderate"),
    }

    # SSL Pinning patterns
    SSL_PINNING_PATTERNS = {
        r'CertificatePinner': ("OkHttp pinning", "hard"),
        r'TrustManagerFactory': ("Custom TrustManager", "moderate"),
        r'X509TrustManager': ("Custom X509TrustManager", "moderate"),
        r'checkServerTrusted': ("Server cert check", "moderate"),
        r'network_security_config': ("Network security config", "hard"),
        r'<pin-set': ("Pin set configuration", "hard"),
    }

    def analyze_source(self, source_dir: Path) -> List[ProtectionAnalysis]:
        """Analyze Android source code for protection mechanisms"""
        analyses = []

        # Collect all indicators
        root_indicators = self._find_patterns(source_dir, self.ROOT_DETECTION_PATTERNS, ProtectionCategory.ROOT_DETECTION)
        emulator_indicators = self._find_patterns(source_dir, self.EMULATOR_DETECTION_PATTERNS, ProtectionCategory.EMULATOR_DETECTION)
        debug_indicators = self._find_patterns(source_dir, self.DEBUG_DETECTION_PATTERNS, ProtectionCategory.DEBUG_DETECTION)
        frida_indicators = self._find_patterns(source_dir, self.FRIDA_DETECTION_PATTERNS, ProtectionCategory.FRIDA_DETECTION)
        tamper_indicators = self._find_patterns(source_dir, self.TAMPER_DETECTION_PATTERNS, ProtectionCategory.TAMPER_DETECTION)
        ssl_indicators = self._find_patterns(source_dir, self.SSL_PINNING_PATTERNS, ProtectionCategory.SSL_PINNING)

        # Analyze each category
        analyses.append(self._analyze_category(
            ProtectionCategory.ROOT_DETECTION,
            root_indicators,
            [
                "Implement multiple root detection methods",
                "Use SafetyNet attestation for strong verification",
                "Combine binary, package, and property checks",
                "Check for Magisk hide and similar bypass tools",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.EMULATOR_DETECTION,
            emulator_indicators,
            [
                "Check multiple device properties",
                "Analyze build fingerprint and hardware",
                "Check for emulator-specific files",
                "Monitor performance characteristics",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.DEBUG_DETECTION,
            debug_indicators,
            [
                "Check debugger connection status",
                "Monitor TracerPid in /proc/self/status",
                "Use timing-based anti-debug",
                "Implement multi-threaded debug detection",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.FRIDA_DETECTION,
            frida_indicators,
            [
                "Scan for Frida artifacts and libraries",
                "Monitor for Frida's default port (27042)",
                "Check for Xposed framework",
                "Implement memory scanning for hooks",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.TAMPER_DETECTION,
            tamper_indicators,
            [
                "Verify APK signature at runtime",
                "Check DEX file integrity",
                "Implement checksum verification",
                "Use code obfuscation to hinder analysis",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.SSL_PINNING,
            ssl_indicators,
            [
                "Implement certificate pinning with OkHttp",
                "Use network_security_config.xml",
                "Pin multiple certificates for redundancy",
                "Implement backup pins for certificate rotation",
            ]
        ))

        return analyses

    def _find_patterns(
        self,
        source_dir: Path,
        patterns: Dict[str, tuple],
        category: ProtectionCategory
    ) -> List[ProtectionIndicator]:
        """Find protection patterns in source code"""
        indicators = []

        extensions = ['.java', '.kt', '.xml', '.smali']

        for ext in extensions:
            for file_path in source_dir.rglob(f'*{ext}'):
                try:
                    content = file_path.read_text(errors='ignore')
                    lines = content.splitlines()

                    for pattern, (desc, difficulty) in patterns.items():
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                indicators.append(ProtectionIndicator(
                                    category=category,
                                    indicator=pattern,
                                    location=str(file_path),
                                    line_number=i,
                                    description=desc,
                                    bypass_difficulty=difficulty,
                                ))
                except (OSError, UnicodeDecodeError):
                    pass

        return indicators

    def _analyze_category(
        self,
        category: ProtectionCategory,
        indicators: List[ProtectionIndicator],
        recommendations: List[str]
    ) -> ProtectionAnalysis:
        """Analyze a protection category"""
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


class IOSProtectionAnalyzer:
    """
    iOS Runtime Protection Analyzer

    Analyzes iOS apps for runtime protection mechanisms.
    """

    # Jailbreak detection patterns
    JAILBREAK_DETECTION_PATTERNS = {
        r'/Applications/Cydia\.app': ("Cydia app check", "easy"),
        r'/Library/MobileSubstrate': ("Substrate check", "easy"),
        r'/bin/bash': ("Bash shell check", "easy"),
        r'/usr/sbin/sshd': ("SSH daemon check", "easy"),
        r'/etc/apt': ("APT check", "easy"),
        r'/private/var/lib/apt': ("APT lib check", "easy"),
        r'cydia://': ("Cydia URL scheme", "moderate"),
        r'isJailbroken': ("Jailbreak method", "moderate"),
        r'canOpenURL.*cydia': ("Cydia URL check", "moderate"),
        r'fileExistsAtPath.*cydia': ("Cydia file check", "moderate"),
        r'fork\(\)': ("Fork check", "hard"),
        r'sysctl.*P_TRACED': ("Sysctl trace check", "hard"),
    }

    # Debug detection patterns
    IOS_DEBUG_DETECTION_PATTERNS = {
        r'sysctl.*P_TRACED': ("Sysctl trace check", "hard"),
        r'ptrace': ("Ptrace detection", "hard"),
        r'getppid': ("Parent PID check", "moderate"),
        r'isBeingDebugged': ("Debug check method", "moderate"),
        r'SIGSTOP': ("Signal handling", "hard"),
    }

    # Frida detection patterns
    IOS_FRIDA_DETECTION_PATTERNS = {
        r'frida': ("Frida string", "easy"),
        r'27042': ("Frida default port", "moderate"),
        r'_frida': ("Frida symbol", "moderate"),
        r'gum-js-loop': ("Frida gadget", "hard"),
        r'/usr/lib/frida': ("Frida library", "moderate"),
    }

    # SSL Pinning patterns
    IOS_SSL_PINNING_PATTERNS = {
        r'TrustKit': ("TrustKit library", "hard"),
        r'Alamofire.*ServerTrustManager': ("Alamofire pinning", "hard"),
        r'SecTrustEvaluate': ("SecTrust evaluation", "moderate"),
        r'URLSession.*delegate': ("URLSession delegate", "moderate"),
        r'NSAppTransportSecurity': ("ATS configuration", "moderate"),
    }

    def analyze_source(self, source_dir: Path) -> List[ProtectionAnalysis]:
        """Analyze iOS source code for protection mechanisms"""
        analyses = []

        # Collect indicators
        jb_indicators = self._find_patterns(source_dir, self.JAILBREAK_DETECTION_PATTERNS, ProtectionCategory.JAILBREAK_DETECTION)
        debug_indicators = self._find_patterns(source_dir, self.IOS_DEBUG_DETECTION_PATTERNS, ProtectionCategory.DEBUG_DETECTION)
        frida_indicators = self._find_patterns(source_dir, self.IOS_FRIDA_DETECTION_PATTERNS, ProtectionCategory.FRIDA_DETECTION)
        ssl_indicators = self._find_patterns(source_dir, self.IOS_SSL_PINNING_PATTERNS, ProtectionCategory.SSL_PINNING)

        # Analyze each category
        analyses.append(self._analyze_category(
            ProtectionCategory.JAILBREAK_DETECTION,
            jb_indicators,
            [
                "Check for jailbreak-related files and directories",
                "Verify URL scheme availability (cydia://)",
                "Use fork() to detect jailbreak bypass",
                "Implement sysctl checks",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.DEBUG_DETECTION,
            debug_indicators,
            [
                "Use sysctl to check P_TRACED flag",
                "Implement ptrace(PT_DENY_ATTACH)",
                "Monitor for debug exceptions",
                "Check parent process ID",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.FRIDA_DETECTION,
            frida_indicators,
            [
                "Scan for Frida artifacts",
                "Monitor network connections for Frida ports",
                "Check for Frida libraries in memory",
                "Implement anti-instrumentation checks",
            ]
        ))

        analyses.append(self._analyze_category(
            ProtectionCategory.SSL_PINNING,
            ssl_indicators,
            [
                "Use TrustKit for certificate pinning",
                "Implement custom URLSession delegate",
                "Configure ATS properly in Info.plist",
                "Pin both leaf and intermediate certificates",
            ]
        ))

        return analyses

    def _find_patterns(
        self,
        source_dir: Path,
        patterns: Dict[str, tuple],
        category: ProtectionCategory
    ) -> List[ProtectionIndicator]:
        """Find protection patterns in iOS source"""
        indicators = []

        extensions = ['.swift', '.m', '.h', '.plist']

        for ext in extensions:
            for file_path in source_dir.rglob(f'*{ext}'):
                try:
                    content = file_path.read_text(errors='ignore')
                    lines = content.splitlines()

                    for pattern, (desc, difficulty) in patterns.items():
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                indicators.append(ProtectionIndicator(
                                    category=category,
                                    indicator=pattern,
                                    location=str(file_path),
                                    line_number=i,
                                    description=desc,
                                    bypass_difficulty=difficulty,
                                ))
                except (OSError, UnicodeDecodeError):
                    pass

        return indicators

    def _analyze_category(
        self,
        category: ProtectionCategory,
        indicators: List[ProtectionIndicator],
        recommendations: List[str]
    ) -> ProtectionAnalysis:
        """Analyze a protection category"""
        if not indicators:
            return ProtectionAnalysis(
                category=category,
                implemented=False,
                quality=ImplementationQuality.NONE,
                indicators=[],
                recommendations=recommendations,
                score=0.0,
            )

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

        remaining_recommendations = recommendations[:3] if quality == ImplementationQuality.WEAK else []

        return ProtectionAnalysis(
            category=category,
            implemented=True,
            quality=quality,
            indicators=indicators,
            recommendations=remaining_recommendations,
            score=weighted_score,
        )


class RuntimeProtectionAnalyzer:
    """
    Comprehensive Runtime Protection Analyzer

    Analyzes mobile apps for runtime protection implementations.
    """

    def __init__(self):
        self.android_analyzer = AndroidProtectionAnalyzer()
        self.ios_analyzer = IOSProtectionAnalyzer()

    def analyze(self, source_dir: Path, platform: str = "all") -> Dict[str, List[ProtectionAnalysis]]:
        """Analyze source for runtime protections"""
        results = {}

        if platform in ["android", "all"]:
            results["android"] = self.android_analyzer.analyze_source(source_dir)

        if platform in ["ios", "all"]:
            results["ios"] = self.ios_analyzer.analyze_source(source_dir)

        return results

    def get_summary(self, results: Dict[str, List[ProtectionAnalysis]]) -> Dict[str, Any]:
        """Get analysis summary"""
        summary = {
            "platforms": {},
            "overall_score": 0.0,
            "recommendations": [],
        }

        total_score = 0
        total_categories = 0

        for platform, analyses in results.items():
            platform_score = 0
            platform_summary = {
                "implemented": 0,
                "strong": 0,
                "moderate": 0,
                "weak": 0,
                "none": 0,
            }

            for analysis in analyses:
                if analysis.implemented:
                    platform_summary["implemented"] += 1
                    platform_score += analysis.score

                    if analysis.quality == ImplementationQuality.STRONG:
                        platform_summary["strong"] += 1
                    elif analysis.quality == ImplementationQuality.MODERATE:
                        platform_summary["moderate"] += 1
                    elif analysis.quality == ImplementationQuality.WEAK:
                        platform_summary["weak"] += 1
                else:
                    platform_summary["none"] += 1

                # Collect recommendations
                for rec in analysis.recommendations:
                    if rec not in summary["recommendations"]:
                        summary["recommendations"].append(rec)

                total_categories += 1

            if len(analyses) > 0:
                platform_summary["average_score"] = platform_score / len(analyses)
                total_score += platform_score

            summary["platforms"][platform] = platform_summary

        if total_categories > 0:
            summary["overall_score"] = total_score / total_categories

        return summary

    def export_report(
        self,
        results: Dict[str, List[ProtectionAnalysis]],
        output_path: Path
    ) -> None:
        """Export protection analysis report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "summary": self.get_summary(results),
            "details": {
                platform: [a.to_dict() for a in analyses]
                for platform, analyses in results.items()
            },
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

    def generate_html_report(
        self,
        results: Dict[str, List[ProtectionAnalysis]],
        output_path: Path
    ) -> None:
        """Generate HTML report"""
        summary = self.get_summary(results)

        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Runtime Protection Analysis</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; }
        .score { font-size: 48px; font-weight: bold; color: #007bff; }
        .category { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 4px; }
        .implemented { border-left: 4px solid #28a745; }
        .not-implemented { border-left: 4px solid #dc3545; }
        .quality-strong { color: #28a745; }
        .quality-moderate { color: #ffc107; }
        .quality-weak { color: #dc3545; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #007bff; color: white; }
        .indicator { background: #f8f9fa; padding: 8px; margin: 5px 0; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Runtime Protection Analysis Report</h1>
        <div class="score">Score: """ + f"{summary['overall_score']:.1f}" + """/100</div>
"""

        for platform, analyses in results.items():
            html += f"<h2>{platform.upper()} Platform</h2>"

            for analysis in analyses:
                impl_class = "implemented" if analysis.implemented else "not-implemented"
                quality_class = f"quality-{analysis.quality.value}"

                html += f"""
                <div class="category {impl_class}">
                    <h3>{analysis.category.value.replace('_', ' ').title()}</h3>
                    <p>Status: <span class="{quality_class}">{analysis.quality.value.upper()}</span>
                    | Score: {analysis.score:.1f}/100</p>
"""

                if analysis.indicators:
                    html += "<h4>Indicators Found:</h4>"
                    for ind in analysis.indicators[:5]:
                        html += f"""
                        <div class="indicator">
                            <strong>{ind.description}</strong> ({ind.bypass_difficulty} bypass)
                            <br><small>{ind.location}:{ind.line_number}</small>
                        </div>
"""

                if analysis.recommendations:
                    html += "<h4>Recommendations:</h4><ul>"
                    for rec in analysis.recommendations:
                        html += f"<li>{rec}</li>"
                    html += "</ul>"

                html += "</div>"

        html += """
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(html)

    def analyze(self, app_path: Path, platform: str) -> RuntimeProtectionResult:
        """
        Analyze app binary for runtime protections.

        This method returns a RuntimeProtectionResult for CLI compatibility.
        """
        # Use the source analysis and convert to CLI-compatible result
        analyses = []
        if platform == "android":
            analyses = self.android_analyzer.analyze_source(app_path.parent if app_path.is_file() else app_path)
        else:
            analyses = self.ios_analyzer.analyze_source(app_path.parent if app_path.is_file() else app_path)

        result = RuntimeProtectionResult()
        all_recommendations = []

        # Map analyses to result attributes
        for analysis in analyses:
            status = ProtectionStatus(
                detected=analysis.implemented,
                strength=analysis.quality.value if analysis.implemented else "none",
                details=f"Score: {analysis.score:.0f}%, {len(analysis.indicators)} indicators found"
            )

            if analysis.category == ProtectionCategory.ROOT_DETECTION:
                result.root_detection = status
            elif analysis.category == ProtectionCategory.JAILBREAK_DETECTION:
                result.root_detection = status  # Map jailbreak to root for unified interface
            elif analysis.category == ProtectionCategory.EMULATOR_DETECTION:
                result.emulator_detection = status
            elif analysis.category == ProtectionCategory.DEBUG_DETECTION:
                result.debug_detection = status
            elif analysis.category == ProtectionCategory.TAMPER_DETECTION:
                result.tamper_detection = status
            elif analysis.category in [ProtectionCategory.HOOK_DETECTION, ProtectionCategory.FRIDA_DETECTION]:
                result.hook_detection = status
            elif analysis.category == ProtectionCategory.SSL_PINNING:
                result.ssl_pinning = status
            elif analysis.category == ProtectionCategory.OBFUSCATION:
                result.obfuscation = status

            all_recommendations.extend(analysis.recommendations)

        result.recommendations = list(set(all_recommendations))[:10]

        # Calculate overall score
        protections = [
            result.root_detection,
            result.emulator_detection,
            result.debug_detection,
            result.tamper_detection,
            result.hook_detection,
            result.ssl_pinning,
            result.obfuscation,
        ]
        detected_count = sum(1 for p in protections if p.detected)
        result.score = (detected_count / len(protections)) * 100

        # Add potential bypass methods for missing protections
        if not result.root_detection.detected:
            result.bypass_methods.append(BypassMethod(
                method="Root/Jailbreak bypass",
                description="App can run on rooted/jailbroken devices without detection",
                difficulty="easy"
            ))
        if not result.hook_detection.detected:
            result.bypass_methods.append(BypassMethod(
                method="Frida/Xposed hooking",
                description="App vulnerable to runtime instrumentation frameworks",
                difficulty="easy"
            ))
        if not result.debug_detection.detected:
            result.bypass_methods.append(BypassMethod(
                method="Debugger attachment",
                description="App can be debugged to analyze runtime behavior",
                difficulty="easy"
            ))

        return result

    def quick_check(self, app_path: Path, platform: str) -> QuickCheckResult:
        """
        Quick check for protection mechanisms.

        Returns a simple result with boolean flags.
        """
        full_result = self.analyze(app_path, platform)

        return QuickCheckResult(
            has_root_detection=full_result.root_detection.detected,
            has_emulator_detection=full_result.emulator_detection.detected,
            has_debug_detection=full_result.debug_detection.detected,
            has_tamper_detection=full_result.tamper_detection.detected,
            has_ssl_pinning=full_result.ssl_pinning.detected,
            has_obfuscation=full_result.obfuscation.detected,
        )

    def export_html(self, result: RuntimeProtectionResult, output_path: Path) -> None:
        """Export RuntimeProtectionResult to HTML report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Runtime Protection Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        .score {{ font-size: 48px; font-weight: bold; text-align: center; padding: 20px; }}
        .score.excellent {{ color: #28a745; }}
        .score.good {{ color: #17a2b8; }}
        .score.moderate {{ color: #ffc107; }}
        .score.weak {{ color: #dc3545; }}
        .protection {{ display: flex; justify-content: space-between; padding: 15px; border: 1px solid #ddd; margin: 10px 0; border-radius: 4px; }}
        .protection.detected {{ border-left: 4px solid #28a745; }}
        .protection.missing {{ border-left: 4px solid #dc3545; background: #fff5f5; }}
        .status {{ font-weight: bold; }}
        .status.detected {{ color: #28a745; }}
        .status.missing {{ color: #dc3545; }}
        .strength {{ color: #666; font-size: 14px; }}
        .recommendations {{ background: #e7f3ff; padding: 15px; border-radius: 4px; margin-top: 20px; }}
        .bypass {{ background: #fff3cd; padding: 10px; margin: 5px 0; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Runtime Protection Analysis</h1>
        <div class="score {'excellent' if result.score >= 80 else 'good' if result.score >= 60 else 'moderate' if result.score >= 40 else 'weak'}">
            {result.score:.0f}%
        </div>

        <h2>Protection Mechanisms</h2>
"""

        protections = [
            ("Root/Jailbreak Detection", result.root_detection),
            ("Emulator Detection", result.emulator_detection),
            ("Debug Detection", result.debug_detection),
            ("Tamper Detection", result.tamper_detection),
            ("Hook Detection", result.hook_detection),
            ("SSL Pinning", result.ssl_pinning),
            ("Code Obfuscation", result.obfuscation),
        ]

        for name, prot in protections:
            status_class = "detected" if prot.detected else "missing"
            status_text = "✓ Detected" if prot.detected else "✗ Missing"
            html += f"""
        <div class="protection {status_class}">
            <div>
                <strong>{name}</strong>
                <div class="strength">Strength: {prot.strength.upper()}</div>
            </div>
            <div class="status {status_class}">{status_text}</div>
        </div>
"""

        if result.recommendations:
            html += """
        <div class="recommendations">
            <h3>Recommendations</h3>
            <ul>
"""
            for rec in result.recommendations:
                html += f"            <li>{rec}</li>\n"
            html += """
            </ul>
        </div>
"""

        if result.bypass_methods:
            html += """
        <h3>Potential Bypass Methods</h3>
"""
            for bypass in result.bypass_methods:
                html += f"""
        <div class="bypass">
            <strong>{bypass.method}</strong> ({bypass.difficulty})
            <p>{bypass.description}</p>
        </div>
"""

        html += """
    </div>
</body>
</html>
"""

        with open(output_path, 'w') as f:
            f.write(html)
