# Review — V-backlog verification + crawl-safety of the submit/blocklist vocabulary (2026-08-24, late)

Seventh evidence-based pass. Verifies the V1–V3 remediation
([REVIEW_2026-08-24_SEAM.md](REVIEW_2026-08-24_SEAM.md)) at `file:line`, then reviews a
part of the engine the earlier passes only skimmed: the **crawler's action vocabularies**
— the submit-label list that decides what a negative probe *taps*, and the
destructive/session blocklists that decide what a crawl must *never* tap. Both headline
findings are documentation-vs-code mismatches verified by reading the constants against
their own help text. Finding IDs are CS1–CS2.

## Gates (measured on this tree)

| Gate | Result |
| --- | --- |
| `pytest tests/` | green (exit 0) |
| native backend | `rust` — the local wheel was rebuilt, so V1's version gate now reports the core, not the fallback |

## V1–V3 remediation — verified, all real

| ID | Verification |
| --- | --- |
| V1 | ✓ #465 — `_native_core()` version-gates on `mobiscout_core.__version__` against `_MIN_NATIVE_VERSION = (0, 2, 0)` (matches `Cargo.toml` `version = "0.2.0"`); a stale wheel is treated as absent with a warn-once. The parity test now calls `core.scan_lines` directly ("the core, not the seam") so a signature skew fails it loudly instead of passing vacuously. `backend_name()` reports `rust` here now |
| V2 | ✓ #466 — `HealSelectorAction`, `SecurityScanAction`, `GenerateTestAction`, `FuzzTestAction` deleted; the `actions/` dir is down to the five real ones; plugin.xml action registrations dropped (incl. the ctrl+alt+H shortcut) |
| V3 | ✓ #467 — `rust_core/src/dialogue.txt` removed; `src/` is now `ast_analyzer.rs`, `lib.rs`, `sast_scan.rs`, `utils.rs` |

Fourth consecutive fully-real remediation round.

---

## New findings — crawl-safety of the action vocabularies

The safety contract is stated plainly in the code and the CLI help: *"a crawl of a real
app never deletes data or completes a purchase"*
([`app_crawler.py:59`](../framework/crawler/app_crawler.py)), and the `--allow-destructive`
help lists "Pay/Buy/Delete/**Confirm**" as gated by default. Two vocabularies enforce
that: `DESTRUCTIVE_BLOCKLIST` (never tapped unless opted in) and `_SUBMIT_LABELS` (the
control a negative probe taps after typing invalid data). Reading them against each other
surfaces two gaps.

### CS1 — P1: financial submit verbs are tapped by default; `--allow-destructive`'s "Confirm" claim is false

`_SUBMIT_LABELS` ([`form_values.py`](../framework/crawler/form_values.py)) contains
**`transfer`, `exchange`, `send`, and bare `confirm`**. `DESTRUCTIVE_BLOCKLIST`
([`app_crawler.py:63`](../framework/crawler/app_crawler.py)) contains `pay`, `buy`,
`purchase`, `checkout`, and `confirm order` — **but not** `transfer`, `exchange`, `send`,
or bare `confirm`.

`_submit_control` skips blocked controls, so `pay`/`buy` are safe — but a button labelled
**"Transfer"**, **"Send"**, **"Exchange"**, or just **"Confirm"** is a submit label,
*not* blocked, so `_probe_negative_form` types invalid data and **taps it**, by default,
with no `--allow-destructive`. On a banking/wallet screen (an amount field + a "Send"
button) the probe fills the amount with `-1` and taps Send — safe *only if the app
rejects it*. Relying on the app-under-test's own validation is exactly the assumption the
default blocklist exists to not make.

Two concrete defects:

1. **The `--allow-destructive` help overclaims.** It lists "Confirm" as gated, but the
   blocklist only holds `confirm order` (`"confirm order" in "confirm"` is `False`), so a
   button labelled "Confirm" is tapped in the *default* crawl — both as an ordinary tap
   and as a negative-probe submit.
2. **`transfer`/`exchange`/`send` are money-moving verbs promoted to submit labels but
   never added to the destructive set.** They were added to `_SUBMIT_LABELS` to reach
   forms behind them; the safety list wasn't updated to match.

**Fix direction:** the two vocabularies must be reconciled in one place. Either move the
financial verbs (`transfer`, `exchange`, `send`, `wire`, bare `confirm`) into
`DESTRUCTIVE_BLOCKLIST` so a probe never commits them by default, or — since a probe
*needs* a submit control — split "submit for login/continue" from "submit that moves
money", and let the probe use only the former unless `--allow-destructive`. Then make the
help text match whatever the code actually gates.

### CS2 — P2: the codegen submit picker ignores the blocklist entirely

`graph._submit_element` ([`graph.py:581`](../framework/crawler/graph.py)) selects a submit
control by `_SUBMIT_LABELS` alone and **never consults any blocklist** — the live
crawler's `_submit_control` at least checks `_blocked`. Codegen only *emits* code (it
doesn't execute), so this isn't a live-safety bug, but it means a generated negative/fuzz
case can be built around a "Transfer"/"Confirm" button and, when the user runs that kit
against a real device, taps it. The generated kit inherits CS1's exposure without even
CS1's partial `_blocked` guard. Fold the same reconciled vocabulary through both submit
pickers.

## Backlog, in order

1. [ ] CS1 — reconcile `_SUBMIT_LABELS` and `DESTRUCTIVE_BLOCKLIST` (financial verbs +
       bare "confirm"); make the negative probe never commit a money-moving control by
       default; correct the `--allow-destructive` help.
2. [ ] CS2 — route `graph._submit_element` through the same blocklist-aware selection, so
       generated negative/fuzz cases don't target destructive controls.

## Calibration

**By execution:** the full pytest suite; the native-backend check (`rust` after the
rebuild).

**By reading at `file:line`:** the three V-verifications; both submit pickers
(`app_crawler._submit_control`, `graph._submit_element`) against `_SUBMIT_LABELS`,
`DESTRUCTIVE_BLOCKLIST`, `SESSION_BLOCKLIST`, and the `--allow-destructive` help text.

**Not checked, so not claimed:** whether any real app in the owner's test set actually
labels a money action "Send"/"Transfer" (the finding is about the vocabulary's default
guarantee, not a specific app); the crawler against a live device; whether the negative
probe's invalid values (`-1` for an amount) are always rejected by a well-behaved app
(the point is precisely not to depend on that).
