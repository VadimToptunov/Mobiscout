---
name: triage-deps
description: Triage open Dependabot PRs — auto-merge safe (patch/minor, actions) after CI, hold major/risky bumps for review. Use when Dependabot PRs pile up.
---

# triage-deps

Dependabot opens weekly update PRs (config in `.github/dependabot.yml`). Sort them
into *safe to merge when green* vs *needs a human*.

## Procedure
1. List them:
   ```
   gh pr list --state open --search "author:app/dependabot" --json number,title
   ```
2. Classify each by the version jump in the title (`from X to Y`):
   - **SAFE** (merge when CI green): GitHub Actions bumps, patch bumps (x.y.Z), minor bumps (x.Y.z) of libraries NOT central to runtime behavior.
   - **REVIEW** (do NOT auto-merge): **major** bumps (X.y.z) and anything touching the app's core deps — `appium-python-client`, `selenium`, `scikit-learn`/`pandas`/`joblib` (ML pickle + APIs), `pydantic`, `click`. A major here can break the emitters or the ML model.
3. For SAFE ones, confirm CI is green then merge:
   ```
   gh pr checks <#> ; gh pr merge <#> --merge --delete-branch
   ```
4. For REVIEW ones: leave open, and if warranted comment why (e.g. "pandas 2→3 — verify ML training/pickle first"). Optionally check out the branch and run the full suite before deciding.

## Notes
- The opt-in workflow `.github/workflows/dependabot-auto-merge.yml` auto-merges patch/minor after CI when repo var `AUTO_MERGE_DEPENDABOT=true`; majors are labelled `major-update`. This skill is the manual counterpart / for when the setting is off.
- CI is the safety net: a bump that breaks codegen fails the codegen gate, so a green check on a dependency PR is meaningful.
- Grouped PRs (e.g. "bump the dev-tooling group") are usually safe; still read the members.
