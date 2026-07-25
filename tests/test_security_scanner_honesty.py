"""The APK/IPA scanner used to fake binary analysis — _extract_manifest /
_extract_source_code returned "" and _is_code_obfuscated returned False, so a scan
produced no real findings and read as "secure". Now it (a) actually scans the
APK's embedded strings for secrets (stdlib zip, no apktool), and (b) emits an
explicit coverage finding whenever it could not inspect the manifest/bytecode, so
an empty result is never mistaken for a clean bill of health. These pin both.
"""

import zipfile

from framework.security.scanner import AndroidSecurityScanner, IOSSecurityScanner


def _make_apk(path, *, obfuscated=False):
    # A real zip (an APK is a zip). classes.dex carries a hardcoded AWS key plus
    # some class descriptors so obfuscation detection has something to sample.
    names = [f"L{'a' if obfuscated else 'com/example/RealClassName'}{i};" for i in range(30)]
    dex = b"\n".join([b"AKIAIOSFODNN7EXAMPLE"] + [n.encode() for n in names])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("classes.dex", dex)
        z.writestr("resources.arsc", b"\x00\x01binary")
    return path


def _titles(findings):
    return [f.title for f in findings]


def test_real_hardcoded_secret_is_found_in_the_apk(tmp_path):
    apk = _make_apk(tmp_path / "app.apk")
    findings = AndroidSecurityScanner().scan(apk)
    aws = [f for f in findings if "AWS Key" in f.title]
    assert aws, _titles(findings)  # the embedded AKIA... key is actually detected
    assert aws[0].severity.value == "critical"


def test_scan_is_honest_about_what_it_could_not_analyze(tmp_path):
    apk = _make_apk(tmp_path / "app.apk")
    findings = AndroidSecurityScanner().scan(apk)
    partial = [f for f in findings if "Partial analysis" in f.title]
    assert partial, _titles(findings)  # never a silent, falsely-clean result
    assert partial[0].severity.value == "info"
    assert "not mean the app is secure" in partial[0].description.lower()


def test_obfuscation_detected_from_real_class_names(tmp_path):
    clear = AndroidSecurityScanner().scan(_make_apk(tmp_path / "clear.apk", obfuscated=False))
    assert "Code Not Obfuscated" in _titles(clear)  # real: long names => not obfuscated
    obf = AndroidSecurityScanner().scan(_make_apk(tmp_path / "obf.apk", obfuscated=True))
    assert "Code Not Obfuscated" not in _titles(obf)  # real: a/b/c names => obfuscated


def test_non_apk_file_is_not_reported_as_secure(tmp_path):
    junk = tmp_path / "notreally.apk"
    junk.write_text("this is not a zip", encoding="utf-8")
    findings = AndroidSecurityScanner().scan(junk)
    # No fake findings, but the coverage note must still be present.
    assert any("Partial analysis" in f.title for f in findings)


def test_ios_scan_is_honest(tmp_path):
    ipa = tmp_path / "app.ipa"
    ipa.write_bytes(b"not analyzed")
    findings = IOSSecurityScanner().scan(ipa)
    assert any("Partial analysis" in f.title for f in findings)
