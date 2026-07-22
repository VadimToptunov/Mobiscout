"""Analyzer extracted from sast_analyzer (mechanical split; see sast/base.py)."""

import logging
from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET

from framework.security.sast.base import (
    VulnerabilityType,
    Severity,
    SASTFinding,
)

logger = logging.getLogger(__name__)


class AndroidManifestAnalyzer:
    """
    Android Manifest Security Analyzer

    Analyzes AndroidManifest.xml for security issues.
    """

    def analyze(self, manifest_path: Path) -> List[SASTFinding]:
        """Analyze AndroidManifest.xml"""
        findings = []

        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()

            # Check application attributes
            app = root.find(".//application")
            if app is not None:
                # Debuggable
                debuggable = app.get("{http://schemas.android.com/apk/res/android}debuggable")
                if debuggable == "true":
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.DEBUGGABLE,
                            severity=Severity.CRITICAL,
                            title="Application is debuggable",
                            description="android:debuggable='true' allows debugging in production",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Set android:debuggable='false' for production builds",
                            cwe_id="CWE-489",
                            owasp_category="M8: Security Misconfiguration",
                        )
                    )

                # Backup
                backup = app.get("{http://schemas.android.com/apk/res/android}allowBackup")
                if backup == "true" or backup is None:
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.BACKUP_ENABLED,
                            severity=Severity.MEDIUM,
                            title="Application backup enabled",
                            description="App data can be backed up and potentially extracted",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Set android:allowBackup='false' unless explicitly needed",
                            cwe_id="CWE-530",
                            owasp_category="M9: Insecure Data Storage",
                        )
                    )

                # Cleartext traffic
                cleartext = app.get("{http://schemas.android.com/apk/res/android}usesCleartextTraffic")
                if cleartext == "true":
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.CLEARTEXT_TRANSMISSION,
                            severity=Severity.HIGH,
                            title="Cleartext traffic allowed",
                            description="Application allows unencrypted HTTP traffic",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Set android:usesCleartextTraffic='false' and use HTTPS",
                            cwe_id="CWE-319",
                            owasp_category="M5: Insecure Communication",
                        )
                    )

            # Check exported components
            for component_type in ["activity", "service", "receiver", "provider"]:
                for component in root.findall(f".//{component_type}"):
                    exported = component.get("{http://schemas.android.com/apk/res/android}exported")
                    name = component.get("{http://schemas.android.com/apk/res/android}name", "unknown")

                    # Check intent filters (implicit export)
                    has_intent_filter = component.find("intent-filter") is not None

                    if exported == "true" or (has_intent_filter and exported != "false"):
                        # Check for permission protection
                        permission = component.get("{http://schemas.android.com/apk/res/android}permission")

                        if not permission:
                            findings.append(
                                SASTFinding(
                                    vulnerability_type=VulnerabilityType.INSECURE_DEEP_LINK,
                                    severity=Severity.MEDIUM,
                                    title=f"Exported {component_type} without permission",
                                    description=f"{name} is exported but not protected by permission",
                                    file_path=str(manifest_path),
                                    line_number=1,
                                    recommendation=f"Add android:permission to protect the {component_type}",
                                    cwe_id="CWE-926",
                                    owasp_category="M1: Improper Platform Usage",
                                )
                            )

            # Check dangerous permissions
            dangerous_permissions = [
                "android.permission.READ_SMS",
                "android.permission.RECEIVE_SMS",
                "android.permission.READ_CONTACTS",
                "android.permission.READ_CALL_LOG",
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.RECORD_AUDIO",
                "android.permission.CAMERA",
            ]

            for perm in root.findall(".//uses-permission"):
                perm_name = perm.get("{http://schemas.android.com/apk/res/android}name")
                if perm_name in dangerous_permissions:
                    findings.append(
                        SASTFinding(
                            vulnerability_type=VulnerabilityType.CLIPBOARD_DATA,
                            severity=Severity.INFO,
                            title=f"Dangerous permission: {perm_name}",
                            description=f"Application requests sensitive permission: {perm_name}",
                            file_path=str(manifest_path),
                            line_number=1,
                            recommendation="Ensure this permission is necessary and handle data securely",
                            cwe_id="CWE-250",
                        )
                    )

        except (ET.ParseError, OSError) as e:
            # A manifest we can't parse/read means its permissions go unaudited.
            logger.debug("SAST android-manifest: skipped %s: %s", manifest_path, e)

        return findings
