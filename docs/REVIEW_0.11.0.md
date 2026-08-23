# Review — 0.11.0 + remediation verification (2026-08-23)

Third evidence-based pass. [AUDIT_2026-08.md](AUDIT_2026-08.md) asked *does the project
do what it says?*; [REVIEW_2026-08-23.md](REVIEW_2026-08-23.md) dug into the engine hot
path and the plugin. This one does what neither could: **verifies that the 35-PR
remediation wave is real** (fast fixes are often shallow — these were checked at
`file:line`, not by reading the ✅ marks), and **reviews the 0.11.0 code that landed the
same day** (Maestro, MCP, cloud grid, coverage artifact, diff-aware regeneration, fuzz
emission, api-negative) — code no prior review has seen.

Every finding below was read first-hand or reproduced; repro/verification commands are
inline. Review-only: this pass changed nothing.

## Gates (measured on this tree)

| Gate | Result |
| --- | --- |
| `pytest tests/` | green (exit 0), coverage **88%** (floor 87) |
| `mypy framework` (2.3.1) | 0 errors |
| `black --check` (26.5.1) | clean |
| `interrogate framework` | **90.3%** — headroom over the 90 floor is down to 0.3% |

## Remediation verification — every ✅ checked against the code

All claimed fixes are **real**, none is cosmetic:

- **TEST_DATA** (#387) — the emitter builds a `(field, value)`-keyed list
  (`emitters/python_pytest.py:_build_test_data`); the template is a dumb renderer; the
  regression test covers a positive + negative case on one field.
- **Rust core** (#391) — wired as a genuine optional accelerator
  ([`analyzers/native.py`](../framework/analyzers/native.py), consumed by
  `analyzers/ast_analyzer.py`) with an honest pure-Python fallback; every fabricated
  benchmark figure is gone from `ARCHITECTURE.md` / `RUST_CORE.md` / `README.md`
  (verified by grep); `scripts/bench_native.py` exists to produce measured numbers.
- **CHANGELOG** (#389) — rewritten from git history; the fictional 2024–2025 timeline is
  gone; 0.9.0/0.9.1/0.10.0/0.11.0 are recorded.
- **Examples** (#387) — regenerated ("by Mobiscout", settle beats, negative cases);
  POM parity shipped (#395, `framework/tests/test_flows.py` in the showcase kit).
- **Dashboard** (#399) — binds `127.0.0.1`, mutating routes carry an Origin guard,
  `_confine_to_repo` resolves against a resolved repo root (absolute paths rejected,
  `..`/symlink escapes rejected).
- **JSON-RPC client** (#402) — a real single-reader rewrite: id-correlated
  `ConcurrentHashMap<id, CompletableFuture>`, serialized writes, pending calls failed
  fast when the stream closes. **P0.4b** (#403): start/download off the EDT.
- **Daemon service** (#402) — application-level `Disposable` (no orphaned engine),
  `@Synchronized` start, log in the IDE log dir.
- **Daemon caps** (#409) — default 600 s wall-clock budget on `kit/generate` and
  `generateMany`; 8 MB request-size cap before `json.loads`.
- **Engine binary** (#406) — cached copy re-verified against the stored digest on every
  launch; `.part` download + atomic publish. (In-jar digest pinning remains undone, as
  the ✅ text itself says.)
- **PRO gating** (#394) — all five lanes (`security`, `a11y`, `fuzz`, `load`, `grid`)
  route through `require_feature`; a no-op on the open-core UNLIMITED tier.
- **Kit execution** (#397) — [`tests/codegen/test_kit_execution.py`](../tests/codegen/test_kit_execution.py)
  runs an emitted kit against a device-free fake Appium **with a negative control**
  proving the harness has teeth. Exemplary work.

---

## New findings

### P0 — the 0.11.0 release does not reach the plugin user

**1. `ENGINE_VERSION` is still `v0.10.0`.**
[`EngineProvider.kt:22`](../jetbrains-plugin/src/main/kotlin/com/mobiletest/recorder/services/EngineProvider.kt)
pins the engine download to `v0.10.0` while the `v0.11.0` release is published with all
four platform binaries (verified via `gh release view v0.11.0`). Plugin 0.11.0 therefore
downloads and runs the 0.10.0 engine: no Maestro, no fuzz-in-kit, no diff/coverage
artifacts for any plugin user. The 0.9.0 release established "align `__version__` +
`ENGINE_VERSION`" as release ritual (#367); 0.11.0 missed it, and nothing enforces it.
**Fix:** bump the pin, and add a guard — a plugin unit test or CI step asserting
`ENGINE_VERSION == "v" + framework.__version__` (the version is greppable from
`framework/__init__.py`), so a release cannot ship misaligned again.

**2. Maestro is unreachable from the one path.**
[`GenerateKitDialog.kt:41`](../jetbrains-plugin/src/main/kotlin/com/mobiletest/recorder/ui/GenerateKitDialog.kt)
hardcodes `frameworksByLanguage` to the 8 pre-0.11.0 targets. Combined with finding 1,
the release's flagship feature is reachable only from the CLI. **Fix:** add the entry
(and consider sourcing the list from the engine's `backend/list`/target registry so the
dialog can't drift again).

### P1 — the F1/F2 remediation missed two case builders

**3. `fuzz_form_cases` and `negative_form_cases` navigate over raw transitions.**
The typed-`Transition` work (#398/#401) filtered probe/gate edges in
`_reachable_steps`, `multi_step_cases` and `_navigation_cases` — but not here:

- [`graph.py:643`](../framework/crawler/graph.py) and `:730`: both builders fill
  `by_pair` from `result.transitions` **with no `kind` filter**, so `candidates[0]` can
  be a probe element replayed as a navigation tap.
- Neither consults `result.gated` or trims the path at the gate the way
  `_reachable_steps` does (`graph.py:307–320`). A form behind login gets a nav prefix
  that taps *through* the gate screen without credentials — a guaranteed red test.

`fuzz_form_cases` is new 0.11.0 code that **copied the pre-fix pattern** — exactly the
regression class the typed `Transition` was meant to end. **Fix direction:** stop
copy-pasting the nav-prefix logic; both builders should obtain their path steps from the
one function that already handles gate/probe/auth (`_reachable_steps`), then append
their form/fuzz/submit steps.

**4. `handle_type` (Android): the comment promises more than the code does.**
[`daemon_commands.py:622`](../framework/cli/daemon_commands.py) escapes only `%` and
spaces, while the comment claims "metacharacters (& ; $ quotes) are typed literally".
They are not: adb `shell` joins argv into one string that the **device-side shell
re-parses** — typed text `a&b` backgrounds a job, `$VAR` expands, quotes break the
command. Typing `Tom & Jerry` from the plugin's inspector is broken today. **Fix:**
quote the token for the remote shell (wrap in single quotes, escape embedded quotes)
in addition to the `%s` space encoding; regression-test with `& ; $ " '` payloads.

**5. `api_negative` bakes captured request bodies into generated tests.**
[`api_negative.py`](../framework/codegen/api_negative.py)'s docstring promises
"captured credentials are never baked into the output … safe to commit", but the
missing-field test emits `json={partial!r}` — the captured JSON body **verbatim minus
one key**. If the body was `{"user": …, "password": …}` and `user` was dropped, the
real password is committed into the test file. Two more honesty gaps: the BOLA/IDOR
tests pass **vacuously** when `MOBISCOUT_API_TOKEN` is unset (empty auth header → 401 →
`!= 200` → green), and only the first body field is ever dropped. **Fix:** substitute
type-shaped sample values for body fields (never captured values); `pytest.skip` the
authz cases when the token is absent.

### P2 — correctness & friction

**6. `--only-changed` overwrites the full kit with the delta.**
Flat emitters write fixed filenames (`test_crawl_flow.py`) into the same `out` dir, so
after `filter_to_changed` the emitted file contains *only* the added+changed cases —
the unchanged tests **vanish from the kit**. Nothing warns, and the help text doesn't
say it. Also [`diff.py`](../framework/crawler/diff.py)'s module docstring shows
`write_manifest` *after* `filter_to_changed` — following that example corrupts the
baseline (the pipeline itself does it correctly at `crawl_service.py:386`). **Fix:**
either emit the delta into a subdirectory, or document the destructive semantics
loudly; and fix the docstring's operation order.

**7. Maestro `text:` selectors are regexes.**
Maestro matches text as a regular expression;
[`emitters/maestro.py`](../framework/codegen/emitters/maestro.py) emits label text
unescaped. A price label `4.99` matches `4X99`; `(1+)` breaks the matcher. **Fix:**
regex-escape TEXT selector values (and add a golden with a metachar label).

**8. Case names are not stable enough for diff-aware regeneration.**
`_unique` (`to_codegen.py:247`) assigns `_2/_3` suffixes in enumeration order, and
unlabeled screens fall back to `screen_{index+1}` — inserting one screen shifts
neighbours' names, producing spurious added/removed churn in `CHANGES.md`. For a
diff feature, names are identity. **Fix:** derive collision suffixes and fallbacks from
something crawl-stable (screen fingerprint prefix), not list position.

**9. `grid run` assumes a python kit.**
[`grid_commands.py`](../framework/cli/grid_commands.py) runs `python -m pytest KIT_DIR`
— a java/js/maestro kit fails confusingly, and neither help nor docs scope the command
to `python_pytest` kits. Also `platform.capitalize()` yields `platformName: "Ios"`
(most grids tolerate it; still sloppy — map to `iOS`/`Android` explicitly).

**10. `JsonRpcClient.call()` after daemon death waits the full timeout.**
A future registered after `readLoop` has exited is completed by nobody — the call
blocks for the whole 600 s backstop. **Fix:** a `closed` flag set in the reader's
`finally`; `call()` fails fast when it's up.

**11. Small items.**
- The MCP stdio server reads lines with no size cap — the daemon gained an 8 MB cap
  (#409); the new transport didn't get parity.
- `interrogate` headroom is 0.3% — the next few undocumented functions red the lint
  job for an unrelated reason. Ratchet or top up.
- [`AUDIT_2026-08.md`](AUDIT_2026-08.md) is still untracked in the working tree: its
  entire backlog is closed by commits that cite it (#387–#395), but the document those
  commits reference isn't in the repo. Commit it.

---

## What this pass confirms about the process

The remediation speed is impressive and — spot-checked — **not cardboard**: everything
marked ✅ in the prior review is genuinely in the code. But the speed has a visible
cost, in two places:

1. **The release process is manual exactly where it has now broken twice.** The engine
   pin drifted from the release *on the same day the release shipped*. Finding 1's
   guard turns the ritual into a gate.
2. **The F1/F2 fix patched three call sites of a five-site pattern, and same-day new
   code copied an unpatched one.** The nav-prefix logic lives as copy-paste instead of
   one function; finding 3's fix direction removes the pattern, not the instance.

## Backlog, in order

1. [ ] `ENGINE_VERSION` bump + version-alignment guard (finding 1) — minutes of work,
       blocks the entire point of the release.
2. [ ] Maestro in the dialog / registry-driven target list (finding 2).
3. [ ] Shared nav-prefix builder for fuzz/negative cases (finding 3).
4. [ ] `handle_type` remote-shell quoting + metachar regression test (finding 4).
5. [ ] `api_negative`: sample values instead of captured bodies; skip authz cases
       without a token (finding 5).
6. [ ] `--only-changed` semantics + `diff.py` docstring order (finding 6).
7. [ ] Maestro text-regex escaping (finding 7).
8. [ ] Fingerprint-stable case names (finding 8).
9. [ ] `grid run` scoping + platformName mapping (finding 9); `call()` fail-fast after
       close (finding 10); MCP line cap, interrogate headroom, commit the audit doc
       (finding 11).

## Calibration — what was and wasn't checked

**By execution:** the full suite + coverage, mypy, black, interrogate, the
`gh release view v0.11.0` asset listing.

**By reading at `file:line`:** every remediation ✅ above; every finding.

**Not checked, so not claimed either way:** live-device behaviour (no rig attached);
the plugin at runtime inside an IDE (incl. whether the EDT fixes hold under a real
window manager); Maestro flows against a real `maestro` CLI run; the grid commands
against a real provider account; concurrency of the daemon under parallel
`kit/generateMany` on real devices.
