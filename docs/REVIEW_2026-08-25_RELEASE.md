# Review — CR1 verification, the 0.12.0 release, and a residual money-context hole (2026-08-25)

Ninth evidence-based pass. Verifies the CR1 remediation
([REVIEW_2026-08-25_CRAWLREACH.md](REVIEW_2026-08-25_CRAWLREACH.md)) at `file:line`, then
reviews the **0.12.0 release** that landed this round — including the version-alignment
invariant that broke twice before — and follows the CR1 fix one step further to a
**residual money-detection gap** it leaves open. Findings are reproduced by execution.
IDs are RL1 and MC1.

## Gates (measured on this tree)

| Gate | Result |
| --- | --- |
| `pytest tests/` | green (exit 0) — 2426 passing |
| engine-version alignment | ✓ `ENGINE_VERSION = "v0.12.0"` == `"v" + __version__` (0.12.0), enforced by `EngineProviderTest` |

## CR1 remediation — verified, and the best-shaped fix of the series

| ID | Verification |
| --- | --- |
| CR1(a) | ✓ #471 — `_label_has_token` matches blocklist tokens on **word boundaries** (`\b…\b`), so "send" no longer fires on "resend"/"sender", "pay" not on "PayPal"/"Payment", "buy" not on "Buyer" — fixing the pre-existing substring false positives too |
| CR1(b) | ✓ #471 — the financial verbs are split into `_ALWAYS_FINANCIAL_LABELS` (pay/buy/purchase/checkout/wire/transfer — always blocked) and `_CONTEXT_FINANCIAL_LABELS` (send/confirm/exchange — blocked **only** on a money screen, via `_is_money_screen`); `_blocked` takes `money_context`, each `_Frame` carries the flag computed once per screen, and `graph._submit_element` applies identical logic (CS2 mirror). Context-gating is default-profile only; `--allow-destructive` drops the tier |

Reproduced — the two-tier + word-boundary + context gate behaves correctly across the
CR1 table and the money/no-money split:

```
'Send code'      money=False  blocked=False   ← OTP crawls again
'Resend OTP'     money=False  blocked=False
'Send message'   money=False  blocked=False
'Confirm email'  money=False  blocked=False
'PayPal'         money=False  blocked=False
'Send'           money=True   blocked=True    ← transfer-form commit still blocked
'Pay now'        money=False  blocked=True    ← always-financial, no context needed
```

Single-sourced, mirrored into codegen, with regressions for the OTP-vs-transfer split.
Sixth consecutive real remediation round, and the cleanest — it closes the drift class
*and* the over-block class at once.

## The version-alignment invariant is now enforced (the standout)

The V1 review proposed a guard so a release can't ship a plugin that downloads a stale
engine (the bug that shipped at 0.11.0, pin lagging at v0.10.0). It exists and holds:
`EngineProviderTest.'engine version pin is aligned with the framework version'` parses
`framework/__init__.py` and asserts `ENGINE_VERSION == "v" + __version__`, failing the
build on drift. At 0.12.0 all three (`__init__.py`, `build.gradle.kts`, `EngineProvider`)
are aligned. The invariant that broke twice is now a build gate — the right outcome.

---

## New findings

### RL1 — P2: the 0.12.0 release updated the plugin change-notes but not `CHANGELOG.md`

`CHANGELOG.md` — which opens by declaring Keep-a-Changelog + SemVer discipline — stops at
**`## [0.11.0] — 2026-08-23`**. The released version is **0.12.0** (`__version__`,
`build.gradle.kts`, the git tag). The release commit (0e74089, message: "version bump +
change notes") touched `framework/__init__.py`, `build.gradle.kts`, `EngineProvider.kt`,
and `plugin.xml`'s `<change-notes>` — but **not** `CHANGELOG.md`. So the Marketplace
change-notes have 0.12.0 while the repo's canonical changelog doesn't; "change notes" in
the commit meant only the plugin.xml block. This is the AUDIT §2.2 doc-drift class
recurring one release later. **Fix:** add the 0.12.0 section to `CHANGELOG.md` (the
plugin.xml block is a ready source), and fold "update CHANGELOG.md" into the release
ritual — ideally the same alignment test family, or a release-checklist item, so the two
change-note homes can't diverge again.

### MC1 — P2: money-context detection is label-text-only, so a plain transfer form still evades the block

CR1(b) gates the ambiguous verbs on `_is_money_screen`, which inspects **visible label
text** for a currency symbol (`$ € £ ¥ ₽`) or one of seven hint words
(`amount/currency/iban/sort code/account number/recipient/balance`). Reproduced: a
minimal transfer form — an amount `EditText` whose id is `…/amount_field`, recipient
shown as "To", note field, and a "Send" button — is **not** detected as a money screen,
so "Send" is not blocked and the default negative probe fills invalid data and taps it:

```
labels ['To', 'Note', 'Send']            -> _is_money_screen = False   (Send not blocked)
CrawlElement(id='…/amount_field')        -> _sample_value = '10'       (known to BE an amount)
'quantity' in _MONEY_HINTS               -> False                      (vocab drift)
```

Two problems, both the familiar two-vocabularies-should-agree class:

1. **The money signal is computed elsewhere but not reused here.** `_sample_value`
   already classifies a field as an amount from its id/label
   (`amount/qty/quantity/number/count`), and the crawler inspects every input field — but
   `_is_money_screen` re-derives money-ness from labels only, ignoring field-level
   evidence. A form whose amount input carries no visible currency symbol or hint *word*
   slips through.
2. **The two hint vocabularies don't match.** `_MONEY_HINTS` lacks `qty`/`quantity`/
   `number`/`count` that `_sample_value` treats as amount fields.

This is materially narrower than the original CS1 hole (which was *every* money form) —
now only a money form whose visible text trips no symbol/hint — but it is real and
copy-dependent, which the tool can't control. **Fix:** feed `_is_money_screen` the
input-field amount signal (reuse `_sample_value`'s amount vocabulary against field
ids/types, not just visible labels), single-sourcing the "is this a money field" test the
way CS1 single-sourced the labels.

## Backlog, in order

1. [ ] RL1 — add 0.12.0 to `CHANGELOG.md`; make "update CHANGELOG.md" part of the release
       gate so it can't drift from plugin.xml again.
2. [ ] MC1 — make `_is_money_screen` consult field-level amount evidence (reuse
       `_sample_value`'s vocabulary); align the hint word lists; regression test for a
       transfer form with an amount input but no visible currency symbol.

## Calibration

**By execution:** the full pytest suite; the CR1 two-tier/word-boundary/context table;
the MC1 transfer-form-evasion and vocab-drift repro; the version-alignment check across
`__init__.py` / `build.gradle.kts` / `EngineProvider.kt`.

**By reading at `file:line`:** the CR1 fix (`_label_has_token`, the two label tiers,
`_is_money_screen`, `_blocked(money_context)`, `_Frame.money`, `graph._submit_element`);
`EngineProviderTest`; the 0.12.0 release commit's file list vs `CHANGELOG.md`.

**Not checked, so not claimed:** how the owner's real apps label amount fields (MC1 is
about the default heuristic, not one app); the plugin at runtime inside an IDE; whether a
tag/release for v0.12.0 has actually published the engine binaries yet (the alignment is
verified in-repo, not against the live GitHub release assets).
