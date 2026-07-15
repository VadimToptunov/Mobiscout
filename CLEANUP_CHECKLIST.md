# Cleanup checklist — mobile_test_recorder

Goal of this session: fix the factual inconsistencies found in review. Only bring the project
to internal consistency and honest numbers. Do **not** refactor architecture, do **not** add
features, do **not** touch module logic unless explicitly stated below.

## Session rules (follow strictly)

- Work **one item at a time**. After each one, show the diff and **wait for my "ok"** before the next.
- For any value replacement: first `grep` across the whole repo, show me **every** occurrence, then change. Don't rely on memory of where things live.
- **Do not align numbers "so they match."** Where a number can be measured (coverage, ML accuracy), run the measurement first, give me the real value, and only then write it into the text. Fitting the text to a convenient value is forbidden.
- Two items are marked `⚠️ MY DECISION` — for these you present options and **stop**; you do not choose.
- Do not commit or push without my command. Each logical block is a separate commit with a conventional message (`fix:` / `docs:` / `chore:`).

---

## Block 1 — package name (one everywhere)

- [ ] Canonical name: `mobile-observe-test-framework` (as in `pyproject.toml`).
- [ ] `grep -rn "mobile-observe-test\|mobile-test-recorder\|mobile_observe" README.md docs/ QUICKSTART.md USER_GUIDE.md` — show all.
- [ ] Replace every `pip install ...` with the canonical name (in README at least lines ~159 and ~353).
- [ ] If the package is **not** published on PyPI — remove `pip install <name>` from the primary install path and keep only `pip install -e .`, with a "PyPI release TBD" note. Don't promise what doesn't exist.
- **Done when:** one name across the whole repo, and no install instruction points to a nonexistent package.

## Block 2 — single source of version

- [ ] Find all version declarations: `pyproject.toml` (`0.1.0`), release tag (`v0.5.0`), mentions in README/CHANGELOG/badges.
- [ ] Pick the source of truth — `pyproject.toml`. Ask me which version is correct (0.1.0 or 0.5.0) before aligning the rest to it.
- [ ] Bring all mentions to the chosen version.
- **Done when:** `grep -rn "0\.[0-9]\.0\|v0\." --include=*.md --include=*.toml` yields one consistent number.

## Block 3 — Rust line count

- [ ] Measure for real: `find rust_core -name "*.rs" -exec cat {} + | wc -l` (expected ~1830).
- [ ] In README "Project Stats", replace "8,000 lines" with the measured number.
- [ ] Check whether the same figure appears elsewhere (docs/ARCHITECTURE.md, etc.).
- **Done when:** the Rust number in the text equals the actual one.

## Block 4 — test coverage (MEASURE FIRST)

- [ ] Run for real: `pytest --cov=framework --cov-report=term` and give me the final percentage.
- [ ] Show me the current number, **do not write it into the README yet.**
- [ ] After I confirm the number — update "Test Coverage" in README to the actual value (currently "85%+", while CI gate is `--cov-fail-under=31`).
- [ ] ⚠️ **MY DECISION:** how high to raise `--cov-fail-under` in `ci.yml`. Propose a value (e.g. current actual minus a small margin), but don't change it without my word.
- **Done when:** the README number equals a real run, and the CI gate is agreed with me.

## Block 5 — ML accuracy (MEASURE FIRST)

- [ ] Find where classifier accuracy is computed (`framework/ml/`) and whether a reproducible eval script exists.
- [ ] If the script exists — run it, give me the real number. If not — tell me, **do not invent** one.
- [ ] Resolve the "88%" (ML section) vs "90%+" ("What's Actually Working") discrepancy — keep **one** measured number in both places.
- [ ] Explicitly note the accuracy is on **synthetic** data (already stated in one place — make it consistent).
- **Done when:** one accuracy figure across the whole README, confirmed by a run or honestly labeled as an estimate.

## Block 6 — "AI-powered"

- [ ] Confirm the facts: `grep -rin "openai\|anthropic\|gpt\|llm" framework/` (expected empty — there is no LLM integration).
- [ ] Reword the repo description and README title: drop "AI-powered", replace with something honest (e.g. "ML-assisted" — a RandomForest element classifier).
- [ ] Check that "AI-powered test generation" stays in the Planned section and doesn't contradict the title.
- **Done when:** neither the title nor the description promises LLM/AI that isn't in the code.

## Block 7 — licensing ⚠️ MY DECISION

- [ ] Gather the facts: show me what `framework/licensing/` does (FREE/PRO/ENTERPRISE tiers, feature flags, `PRO-` key checks) and where those checks are invoked across the code.
- [ ] Lay out two options with consequences:
  - **A. Fully OSS:** remove `framework/licensing/`, `license_commands.py`, `test_paid_modules.py`, drop the feature gates. (Under MIT the paywall is bypassable by a fork anyway — it's dead code.)
  - **B. Open-core:** the core stays MIT, paid modules move to a separate private repo; no trace of them remains in this repo.
- [ ] **Stop and wait for my choice.** Delete nothing before the decision.
- **Done when:** I've picked a model and you've implemented exactly that one.

---

## Final check (after all blocks)

- [ ] A `grep` pass over each fixed value — confirm the old one is gone everywhere.
- [ ] Run `pre-commit run --all-files` and `pytest` — nothing broken by the text/config edits.
- [ ] Give me a summary: what changed, which real numbers were obtained, which two decisions were made.

## What NOT to do this session

- Don't narrow/rewrite the README wholesale (separate task, we'll discuss later).
- Don't refactor modules, rename classes, or "improve" code along the way.
- Don't add tests to bump coverage — the goal now is honest numbers, not raising them.
