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
- [x] CI matrix (`build-engine.yml`): build on macOS (x86_64 + arm64), Windows, Linux;
      smoke-test each; upload artifacts; attach to a Release. Proven green on
      Linux / Windows / macOS-arm64.
- [x] Plugin: `EngineProvider` downloads the matching binary for the user's OS on
      first run (cached under `~/.mobile-observe/engine/<version>/`), falls back to a
      PATH `observe` CLI for development, and launches it.
- [ ] macOS codesign + notarize (else Gatekeeper blocks the downloaded binary) —
      needs an Apple Developer identity.
- [ ] Publish a release tagged to match `EngineProvider.ENGINE_VERSION` so the
      download resolves (until then the plugin falls back to a PATH `observe`).
- [x] Integrity: the workflow publishes a `<asset>.sha256` and the plugin verifies
      the download against it (fail-closed — mismatch/missing hash falls back to PATH).
- [ ] Version pinning: fetch the engine build matching the plugin version (today
      `EngineProvider.ENGINE_VERSION` is a constant).
