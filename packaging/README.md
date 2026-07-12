# Standalone engine (variant C) — no Python required by the user

The JetBrains plugin is a thin frontend; the logic lives in the Python engine
(`framework` + the `observe daemon` JSON-RPC server). Variant C ships that engine
as a **self-contained per-platform binary** so an end user installs only the
plugin — no Python, no `pip`.

## Build

```bash
pip install pyinstaller
packaging/build_engine.sh        # -> dist/observe-engine  (this OS/arch)
```

The binary speaks the same JSON-RPC over stdio as `observe daemon`:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"health/check","params":{}}' | dist/observe-engine
```

Proven to run with **no interpreter on PATH** (`env -i`), including the ML/lxml
paths (`selector/generate`) and the codegen templates (bundled as data).

## Status / remaining work

- [x] Freeze feasibility spike — standalone binary, heavy deps, ~122 MB (macOS arm64).
- [ ] CI matrix: build on macOS (x86_64 + arm64), Windows, Linux → attach to a GitHub Release.
- [ ] macOS codesign + notarize (else Gatekeeper blocks it).
- [ ] Plugin: download the matching binary for the user's OS on first run (the
      400 MB Marketplace limit rules out bundling every platform in the plugin zip),
      cache it, and launch it instead of a PATH `observe`.
- [ ] Version pinning: plugin fetches the engine build matching its own version.
