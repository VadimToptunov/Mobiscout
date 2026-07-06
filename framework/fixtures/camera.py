"""
Camera fixture — feed the app's scanner a known image so QR-code and document
(KYC) scans can be tested without a physical code/document in front of a lens.

    Provider.BROWSERSTACK  camera image injection (browserstack_executor)
    Provider.LOCAL         push an image the emulator camera serves (best effort)
    Provider.REAL          needs an in-app image-input hook — can't inject a lens

``media`` is a BrowserStack ``media://…`` id (from uploadMedia) for BrowserStack,
or a local image path for a local emulator.
"""

from __future__ import annotations

import json
from typing import Any

from framework.fixtures.provider import Provider, RealDeviceGateError


def _bs_executor(driver, action: str, arguments: dict) -> Any:
    payload = json.dumps({"action": action, "arguments": arguments})
    return driver.execute_script(f"browserstack_executor: {payload}")


def inject_scan(driver, media: str, provider: Provider = Provider.LOCAL) -> Any:
    """Make the camera 'see' ``media`` — for a QR scan or a document scan.

    BrowserStack: injects the uploaded media into the camera feed. Local: relies
    on the emulator's virtual-scene/webcam image (set it to ``media`` first).
    Real device: not injectable — the app needs an image-input test hook.
    """
    if provider is Provider.BROWSERSTACK:
        return _bs_executor(driver, "cameraImageInjection", {"imageUrl": media})
    if provider is Provider.REAL:
        raise RealDeviceGateError(
            "Camera injection is not possible on a real device — build a test hook "
            "that lets the app read the document/QR from a file, or use BrowserStack."
        )
    # LOCAL: the Android emulator serves a still/virtual-scene image; the caller
    # points the emulated camera at `media`. We surface the intent for the runner.
    return {"provider": "local", "action": "camera_image", "image": media}


def scan_qr(driver, payload_image: str, provider: Provider = Provider.LOCAL) -> Any:
    """Emulate scanning a QR code whose contents are encoded in ``payload_image``
    (generate the QR for the value the app expects, then inject it)."""
    return inject_scan(driver, payload_image, provider)


def scan_document(driver, document_image: str, provider: Provider = Provider.LOCAL) -> Any:
    """Emulate scanning an ID/passport by feeding a test document image to the
    scanner (Regula and similar accept image input as well as a live camera)."""
    return inject_scan(driver, document_image, provider)
