"""Tests for framework.security.decompile.native.NativeLibAnalyzer.

Drives ELF header parsing over synthetic .so bytes and the readelf-driven
protection detection with the external `readelf` binary stubbed via subprocess,
so only the module's own header/architecture logic and stdout parsing run.
Guards: ELF magic gating, 32/64-bit detection, RELRO/stack-canary/PIE parsing,
string counting, and the non-ELF and missing-file paths.
"""

import subprocess
from types import SimpleNamespace

from framework.security.decompile import native as native_mod
from framework.security.decompile.native import NativeLibAnalyzer


def _elf_bytes(arch_byte: int) -> bytes:
    # ELF magic + class byte + padding + a couple of ascii runs for string counting
    return b"\x7fELF" + bytes([arch_byte]) + b"\x00" * 20 + b"libcrypto\x00openssl_init"


def test_non_elf_file_returns_base_info(tmp_path):
    so = tmp_path / "fake.so"
    so.write_bytes(b"NOTELF" + b"\x00" * 40)
    info = NativeLibAnalyzer().analyze_so(so)
    assert info["type"] == "elf"
    assert info["protections"] == []
    # arch is only set once magic matches
    assert "arch" not in info


def test_missing_file_returns_base_info(tmp_path):
    info = NativeLibAnalyzer().analyze_so(tmp_path / "gone.so")
    assert info["protections"] == []
    assert "arch" not in info


def test_elf_arch_detection_64bit(tmp_path, monkeypatch):
    # readelf unavailable -> protections stay empty, but arch/string_count computed
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    so = tmp_path / "lib64.so"
    so.write_bytes(_elf_bytes(2))
    info = NativeLibAnalyzer().analyze_so(so)
    assert info["arch"] == "64-bit"
    assert info["string_count"] >= 1
    assert info["protections"] == []


def test_elf_arch_detection_32bit(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    so = tmp_path / "lib32.so"
    so.write_bytes(_elf_bytes(1))
    info = NativeLibAnalyzer().analyze_so(so)
    assert info["arch"] == "32-bit"


def test_protection_parsing_from_readelf(tmp_path, monkeypatch):
    """With readelf present, BIND_NOW and DF_1_PIE in the dynamic section and
    __stack_chk_fail in the symbol table must map to FULL_RELRO / PIE /
    STACK_CANARY. The dynamic section lists tags, not symbols, so the canary is
    only ever visible via `readelf -s`."""

    def fake_run(cmd, *args, **kwargs):
        if "-d" in cmd:
            return SimpleNamespace(returncode=0, stdout="FLAGS BIND_NOW\nFLAGS_1  Flags: PIE\n")
        if "-sW" in cmd:
            return SimpleNamespace(returncode=0, stdout="  12: 0000 FUNC GLOBAL DEFAULT UND __stack_chk_fail\n")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(native_mod.subprocess, "run", fake_run)

    so = tmp_path / "protected.so"
    so.write_bytes(_elf_bytes(2))
    info = NativeLibAnalyzer().analyze_so(so)
    assert "FULL_RELRO" in info["protections"]
    assert "STACK_CANARY" in info["protections"]
    assert "PIE" in info["protections"]


def test_partial_relro_without_bind_now(tmp_path, monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if "-d" in cmd:
            return SimpleNamespace(returncode=0, stdout="GNU_RELRO segment present\n")
        return SimpleNamespace(returncode=0, stdout="Type: EXEC\n")

    monkeypatch.setattr(native_mod.subprocess, "run", fake_run)
    so = tmp_path / "partial.so"
    so.write_bytes(_elf_bytes(2))
    info = NativeLibAnalyzer().analyze_so(so)
    assert "PARTIAL_RELRO" in info["protections"]
    assert "FULL_RELRO" not in info["protections"]
    assert "PIE" not in info["protections"]
