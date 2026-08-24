# Review — RC verification, the Python↔Rust seam, and the dead Tools-menu actions (2026-08-24, night)

Sixth evidence-based pass. Verifies the RC1–RC4 remediation
([REVIEW_2026-08-24_RUST.md](REVIEW_2026-08-24_RUST.md)) at `file:line`, and covers two
surfaces no earlier review had read: the **ABI seam between `framework` and the installed
`mobiscout_core` wheel** (where a live failure was reproduced on this machine), and the
four **"STEP 11"-era Tools-menu actions** in the plugin. Finding IDs are V1–V3 for commit
references.

## Gates (measured on this tree)

| Gate | Result |
| --- | --- |
| `pytest tests/` | green (exit 0) — but see V1: one regression test currently passes vacuously |

## RC1–RC4 remediation — verified, all real

| ID | Verification |
| --- | --- |
| RC1(a) | ✓ #462 — lines are split **once in Python** (`str.splitlines()`) and passed as `Vec<Vec<String>>`; the Rust side no longer splits; regression test targets the exact form-feed/U+2028 case; the silent-fallback warn-once was added as proposed |
| RC1(b) | ✓ #462 — resolved by **de-claiming**: the docstring now states the complexity backends are NOT identical and why that's acceptable (the shipped engine always carries the wheel, so users get the Rust numbers; the divergence is dev-checkout-only). A legitimate choice from the align-or-de-claim pair |
| RC2 | ✓ #464 — `correlator.rs` / `business_logic.rs` / `io.rs` deleted; `src/` now holds only the live modules |
| RC3 | ✓ #463 — the screenshot RPC moved to `Task.Backgroundable`, **and the class was fixed**: every daemon RPC now routes through one `rpc()` wrapper with `ThreadingAssertions.assertBackgroundThread()` |
| RC4 | ✓ #462 — the tuple is `(file, line, rule)`; the dead line-text payload is gone |

Third consecutive fully-real remediation round.

---

## New findings

### V1 — P1: the local wheel is stale — SAST silently runs the Python fallback, and the parity test passes vacuously

Reproduced on this tree:

```
Rust scan_lines unavailable, using the Python fallback:
argument 'contents': 'list' object cannot be converted to 'PyString'
```

The venv's `mobiscout_core` still has the **pre-#462 signature**. Every `scan_lines`
call hits the ABI skew → warn-once → Python path. Three linked consequences:

1. **The ~35x is silently gone on this machine.** The warn-once from #462 is the only
   thing that makes this visible at all — the mitigation proved its worth on day one.
2. **The RC1(a) regression test is currently vacuous.**
   `test_rust_and_python_agree_on_unicode_line_boundaries` calls `native.scan_lines` —
   the *seam*, not the core. With a stale wheel the seam falls back, so the test compares
   Python with Python and passes. Its `assert backend_name() == "rust"` only proves the
   wheel is *importable*, not that the Rust path *ran*. The test must call
   `core.scan_lines` directly (a stale signature then fails it loudly) or assert that no
   fallback occurred.
3. **There is no version handshake across the seam.** `lib.rs` already exports
   `__version__`; `_native_core()` checks only `hasattr`. The bundled engine is immune
   (CI installs the wheel at build time), but every dev checkout and pip user with a
   previously built wheel silently loses the acceleration after any ABI change.

**Fix:** version-gate `_native_core()` (incompatible → treat as absent + warn); make the
parity test exercise the core directly; `maturin develop` locally as the immediate step;
add a `mobiscout doctor` line — "native core: rust x.y.z / python fallback (reason)".

### V2 — P1: three of the four Tools-menu actions are dead on arrival; the fourth works only for a pip developer

First read of the "STEP 11"-era actions. All four spawn **`mobiscout` from PATH** via
`ProcessBuilder`, bypassing the daemon and `EngineProvider` entirely. Checked against the
real CLI:

| Action | Invokes | Exists? |
| --- | --- | --- |
| `HealSelectorAction` (ships a **ctrl+alt+H** shortcut) | `mobiscout heal suggest` | **no** — `heal` has analyze/auto/history/revert/stats |
| `SecurityScanAction` | `mobiscout security secrets` | **no** — audit/comprehensive/full/… |
| `GenerateTestAction` | `mobiscout generate test` | **no** — the command is `generate tests` |
| `FuzzTestAction` | `mobiscout fuzz ui <id>` | yes — but only with the CLI on PATH |

For the zero-setup user (standalone binary under `~/.mobiscout`, nothing on PATH)
**none of the four works**, including FuzzTest. This is the "dead-on-arrival command"
class the July review purged from the CLI — surviving in the plugin because the CLI
smoke net never checks the action→command mapping. Consistent with the one-path
philosophy: **remove them from the menu until they're real** (daemon RPCs), or resolve
the binary via `EngineProvider` *and* fix the command names — fixing only the names
still leaves them broken on the flagship install path.

### V3 — P2: `rust_core/src/dialogue.txt` — a 2,787-line ChatGPT transcript in the public repo

92 KB of git-tracked chat transcript ("Skip to content / Chat history / You said: Изучи
проект и скажи, какие недостатки…") has been sitting **inside `src/`** of the public MIT
repository since January. Cruft by the project's own principle; a potentially awkward
public artifact (a dialogue analyzing the project's weaknesses); and `cargo package`
would ship it. RC2 deleted the dead `.rs` neighbours — the transcript survived.
**Fix:** `git rm`.

### Closed: the July concurrency thread

The last open item of [CODE_REVIEW.md §6](CODE_REVIEW.md) (concurrency audit of
daemon / dashboard / proxy / storage) is done: `event_store` opens a connection per call
via a contextmanager (thread-safe by construction); `mocking/proxy` uses
`ThreadingHTTPServer` + a `threading.Lock` as previously noted; the daemon and dashboard
were hardened in the earlier rounds (#402/#409, #399).

## Backlog, in order

1. [ ] V1 — version-gate the seam; de-vacuous the parity test; rebuild the local wheel;
       doctor line for the active backend.
2. [ ] V2 — remove or properly wire the four Tools-menu actions (and their plugin.xml
       registrations + the ctrl+alt+H shortcut).
3. [ ] V3 — delete `rust_core/src/dialogue.txt`.

## Calibration

**By execution:** the full pytest suite; the V1 stale-wheel repro (the warn line above);
the V2 command-existence checks against `mobiscout heal/security/generate/fuzz --help`.

**By reading at `file:line`:** every RC verification; the four action classes; the
parity test's call path (seam vs core); `event_store` / `proxy` concurrency patterns.

**Not checked:** the actions at runtime inside an IDE (their DOA status is proven by the
command tables, not by clicking); whether `dialogue.txt` needs history rewriting or just
removal (owner's call — it has been public since January, so removal alone changes
little retroactively); the rebuilt-wheel state (this pass changed nothing, per its
review-only scope).
