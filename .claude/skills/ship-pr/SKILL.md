---
name: ship-pr
description: Land a change in this repo with its exact review discipline — branch, full test + lint gates, golden regen, commit trailer, PR, CI wait, merge. Use whenever committing/PRing work here.
---

# ship-pr

The repo's landing ritual. Follow it exactly; the gotchas below have bitten before.

## Steps
1. **Never commit on `master`.** Start clean:
   ```
   git checkout master && git branch -f master origin/master && git checkout -b <type>/<slug>
   ```
   `<type>` ∈ feat | fix | chore | refactor | ci | docs.
2. Make the change. If you edited any Jinja template under `framework/codegen/templates/`, **regenerate goldens**:
   ```
   UPDATE_GOLDENS=1 python -m pytest tests/codegen/test_emitters.py
   ```
   then `git diff tests/codegen/golden/` and confirm the change is intentional.
3. **Gate locally (all must pass):**
   ```
   python -m pytest tests/ -p no:cacheprovider          # expect "N passed"
   black framework tests && black --check framework tests
   flake8 --select=E9,F63,F7,F82 framework tests         # blocking set; F82 catches undefined names (F821)
   ```
4. Commit with the repo trailer (end the message with):
   ```
   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
   ```
5. `git push -u origin <branch>` then `gh pr create --base master`. Verify `git log --oneline origin/master..HEAD` shows exactly your commit(s).
6. Wait for **all 14 CI checks** green, then `gh pr merge <#> --merge --delete-branch`.

## Gotchas (learned the hard way)
- **Branch-race:** do NOT run a background task that does `git checkout master` while you have uncommitted work on a feature branch — it yanks you onto master and your commit lands there. If it happens: `git branch -f <branch> <sha>; git checkout <branch>; git push -f; git branch -f master origin/master`.
- **"No commits between master and <branch>"** on `gh pr create` = your commit is on `master`, not the branch. Fix as above.
- Generated code must compile — see the `verify-codegen` skill before pushing emitter changes.
- Editing a template changes goldens for *every* affected target; regenerate all of them (step 2), don't hand-edit goldens.
