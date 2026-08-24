# Review — CS verification + the over-block the safety fix introduced (2026-08-25)

Eighth evidence-based pass. Verifies the CS1/CS2 remediation
([REVIEW_2026-08-24_CRAWLSAFE.md](REVIEW_2026-08-24_CRAWLSAFE.md)) at `file:line`, and
then follows the thread the fix opened: a safety blocklist matched by **substring** over
**generic verbs** now blocks a broad class of benign controls — most sharply the OTP
"Send code" that the advertised gate-chaining crawl depends on. The finding is reproduced
by running the blocklist against realistic labels. Finding ID is CR1.

## Gates (measured on this tree)

| Gate | Result |
| --- | --- |
| `pytest tests/` | green (exit 0) — 2423 passing |

## CS1/CS2 remediation — verified, real, and well-structured

| ID | Verification |
| --- | --- |
| CS1 | ✓ #469 — money-moving verbs are single-sourced as `form_values._FINANCIAL_LABELS` (`pay/buy/purchase/checkout/confirm/transfer/exchange/send/wire`) and folded into `DESTRUCTIVE_BLOCKLIST` via concatenation, so the picker and the blocklist **cannot drift** again; `--allow-destructive` still lifts it; the help now reads "Pay/Buy/Transfer/Send/Delete/Confirm" — matching what's gated |
| CS2 | ✓ #469 — `graph._submit_element` now skips `_FINANCIAL_LABELS` before matching `_SUBMIT_LABELS`, mirroring the live crawler; two tests that used money labels incidentally were switched to non-financial ones; new regressions cover both findings |

The single-source-of-truth structure is the right shape — it closes the drift class, not
just the instance. Fifth consecutive real remediation round.

---

## New finding — the fix over-blocks, and it lands on a shipped feature

### CR1 — P1: substring-matched generic verbs now block OTP / messaging / confirm flows

`_blocked` matches by substring (`any(b in label for b in self.blocklist)`,
[`app_crawler.py:225`](../framework/crawler/app_crawler.py)) and gates **both** the
ordinary tap queue (`:748`) and the submit picker (`:654`). Folding the generic verbs
`send` and `confirm` into the default blocklist therefore blocks far more than money
actions. Reproduced by running `_FINANCIAL_LABELS` against realistic labels:

```
'Send code'         blocked=True  by=['send']     ← OTP / 2FA request
'Resend OTP'        blocked=True  by=['send']      ← OTP resend
'Send message'      blocked=True  by=['send']      ← messaging core action
'Send feedback'     blocked=True  by=['send']
'Confirm email'     blocked=True  by=['confirm']   ← benign, often required to progress
'Confirm'           blocked=True  by=['confirm']   ← generic dialog OK
'Transfer history'  blocked=True  by=['transfer']  ← read-only view
```

The sharpest regression is **OTP**: an autonomous crawl (no user waypoint) can no longer
tap "Send code" / "Resend code", so an OTP/2FA screen becomes a dead-end — directly
undercutting the gate-chaining (login/OTP/biometric) the ROADMAP lists as a selling
point. `send`/`confirm` are benign in the overwhelming majority of apps (messaging,
feedback, email confirmation, generic dialogs); their money sense is the exception, and
substring matching can't tell them apart. This is the "smart crawl, not random /
positive AND negative / reach the gate" tension — CS1 traded a safety hole for an
exploration hole.

Note two of these (`pay`→"PayPal"/"Payment methods", `buy`→"Buyer details") were
**pre-existing** substring over-blocks from the original `DESTRUCTIVE_BLOCKLIST`, not new
in #469 — but they share the root cause and are worth fixing in the same pass.

**Fix direction — two independent levers:**
1. **Match on word boundaries / whole tokens, not substrings** — "send" should not fire on
   "resend"/"sender", "pay" not on "PayPal"/"Payment", "buy" not on "Buyer". This alone
   removes most false positives and is a pure improvement to the existing blocklist.
2. **Make the financial block context-aware** — a "Send"/"Confirm" next to an amount /
   currency field is money; the same label on a chat composer or an email-confirmation
   screen is not. The crawler already detects inputs per screen (`_has_input`) and the
   settle code already knows currency symbols (`_VOLATILE = …[$€£¥]`), so "commit control
   on a screen with a money field" is a cheap, much narrower predicate than "any label
   containing 'send'". Keep `pay/buy/purchase/checkout/wire/transfer` as always-blocked
   (rarely benign); gate only the ambiguous `send`/`confirm`/`exchange` on money context.

A regression test should assert a default crawl **taps** "Send code" on an OTP screen
(input + code button, no money field) while still **not** tapping "Send" on a
transfer form (amount field present).

## Backlog, in order

1. [ ] CR1(a) — word-boundary matching in `_blocked` (fixes send→resend, pay→PayPal,
       buy→Buyer); cheapest, pure win.
2. [ ] CR1(b) — context-gate the ambiguous verbs (`send`/`confirm`/`exchange`) on a
       money-field predicate so OTP/messaging/confirm flows crawl again; regression test
       for the OTP-vs-transfer distinction.

## Calibration

**By execution:** the full pytest suite; the blocklist over-match table above.

**By reading at `file:line`:** the CS1/CS2 fix (`form_values._FINANCIAL_LABELS`,
`DESTRUCTIVE_BLOCKLIST` concatenation, `graph._submit_element`, the corrected help);
`_blocked`'s substring match and its two call sites (ordinary tap queue + submit picker).

**Not checked, so not claimed:** how often the owner's real test apps actually label an
OTP control "Send code" vs "Get code"/"Request code" (the finding is about the default
guarantee, not one app); whether a waypoint would paper over the OTP dead-end in a
configured run (it would — but the autonomous default is what regressed); the crawler
against a live device.
