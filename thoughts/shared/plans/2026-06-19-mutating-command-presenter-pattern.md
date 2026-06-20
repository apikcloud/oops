# Migrate `pr manage`, `submodules rename`, `submodules rewrite` onto the lightweight mutating-command presenter pattern

**Status: ✓ Implemented** — all phases complete, 1312 tests pass, termination regression passes.

## Overview

Three interactive mutating commands — `pr manage`, `submodules rename`, `submodules rewrite` — all
follow the same shape: discover candidates, display a plan, get user approval, execute, show
outcomes. The pattern is standardised as:

```
prompt_choices (selection)  →  render_plan (plan table)  →  prompt_confirm
→  execute (per-row outcomes into result)  →  commit_v2 (merged into outer)
→  render(result, outer)  [embedded ConclusionBlock]
→  if not outer.ok: raise OopsError(...)
```

Work proceeds in three phases:

**Phase 0** — Extract `render_plan()` to `output/helper.py` and complete `manage` (the existing
implementation lacks per-row execution tracking and uses a bare `conclude()` instead of
`render(result, outer)` for the final step).

**Phases 1 & 2** — Migrate `rename` and `rewrite` onto the same flow, using `render_plan()` in
place of their current ad-hoc `click.echo`/`click.prompt` output.

Output stays text-only (no `--format`/JSON, per the standing Tier-C rule). `render_and_exit` does
not apply — it exits, so it cannot be used mid-flow.

## Current State Analysis

### `pr manage` (`commands/pr/manage.py`) — partial
Uses `_show_summary()` → `render(result, Result())` for the intermediate plan table, then
`prompt_confirm`. **Execution pass is incomplete**: no `result: Result[Rows]` for outcome rows, no
per-row try/except, just bare `submodule.rename()` calls into a `renames` dict.
Final step calls `conclude(outer.ok, "Renames committed." …)` — not `render(result, outer)`.
This produces no execution summary table and bypasses `ConclusionBlock`.

### `submodules prune` (`commands/submodules/prune.py`) — de-facto template (no changes)
Two-channel `result: Result[Rows]` + `outer: Result[None]`, `live_progress`, per-row outcome
accumulation, ends with `render(result, outer)` then `OopsError`. **Not touched by this plan.**

### `submodules rename` (`commands/submodules/rename.py`) — ad-hoc
Per-item `click.echo` + `click.prompt("…? [Y/n/e]")`, errors via `click.UsageError`, final plain
`click.echo`, legacy `commit(...)`. No `Result`, no table, no `conclude`.

### `submodules rewrite` (`commands/submodules/rewrite.py`) — ad-hoc, most complex
`[plan]` echoes, per-item `[Y/n/e]` prompt, `submodule.move()`, `os.walk` symlink rewrite,
`shutil.rmtree` of old base dir, raw `repo.index.commit(...)`. `EarlyExit` for no-op/dry-run.

### Key Discoveries

- `helper.render(result, outer)` (`output/helper.py:63-74`) returns `None` — usable both as
  intermediate display (pass `outer=Result()` so the embedded `ConclusionBlock` reads no errors)
  and as the final display (pass real `outer`).
- `commit_v2(...)` returns `Result[list]` (`git.py:242-319`); `already_staged=True` commits a
  pre-staged index without re-staging — needed by `rewrite` which stages moved paths + symlinks
  during execution.
- Commit message keys exist: `submodules_rename`, `submodules_rewrite` (`core/messages.py:23,25`).
- `Rows` metric keys are `.capitalize()`-d into panel labels (`helper.py:45`): use single-word keys.
- Exits: `EarlyExit()` (0), `AppAbort()` (1, "Aborted!"), `OopsError(msg)` (1, red "✗ msg").

## Desired End State

`manage.py`, `rename.py`, and `rewrite.py` all follow the standardised flow. A shared
`render_plan(title, columns, rows, metrics)` lives in `output/helper.py` and replaces each
command's local `_show_summary`. `make test` and `make lint` pass. The termination-pattern
regression passes. No `click.echo`/`click.prompt`/`click.UsageError`/legacy `commit`/raw
`repo.index.commit` remain in any of the three files.

## What We're NOT Doing

- Not touching `prune` or `clean`.
- Not adding `--format`/JSON output.
- Not adding a shared base class or a non-exiting `render_and_exit` variant.
- Not preserving the per-item `[Y/n/e]` custom-value edit in `rename`/`rewrite`. **Intentional
  UX change:** all three commands use `prompt_choices` (multi-select, preselect all) + one
  `prompt_confirm`. Custom-name / custom-target entry is dropped.
- Not changing `desired_path`, `rewrite_symlink`, or any business logic — only I/O and control
  flow.

## Implementation Approach

`render_plan(title, columns, rows, metrics)` added to `output/helper.py` is a thin wrapper:
builds `Result[Rows]`, calls `render(result, Result())`. All three commands replace their local
`_show_summary` (or equivalent) with a `render_plan(...)` call. `conclude()` is retained only
for no-op / dry-run early exits.

---

## Phase 0: Extract `render_plan` + complete `manage`

### Overview
Add the shared plan-display helper; bring `manage` to the full pattern (per-row execution
tracking, `render(result, outer)` for the final step, removal of `_show_summary`).

### Changes Required

#### `src/oops/output/helper.py`
**Add** `render_plan` after the existing `render` function:

```python
def render_plan(
    title: str,
    columns: list,
    rows: list,
    metrics: dict | None = None,
) -> None:
    """Render a plan table before user confirmation.

    Uses an empty outer so the embedded ConclusionBlock reflects
    no errors (the plan has not executed yet).
    """
    result: Result[Rows] = Result()
    result.data = Rows(title=title, columns=columns, rows=rows, metrics=metrics or {})
    render(result, Result())
```

Export it from `__init__` / import surface as needed.

#### `src/oops/commands/pr/manage.py`
**Changes**: add imports, replace `_show_summary` + execution pass + conclusion.

Imports change:
```python
# add
from oops.output.helper import render, render_plan
# remove _show_summary local function
```

Replace `_show_summary(actions)` call with:
```python
render_plan(
    "Planned renames",
    [("From", "dim", "left"), ("To", "brand.primary", "left"), ("Direction", "dim", "right")],
    [
        [old, new, colorize("→ PR", "green") if as_pr else colorize("→ regular", "yellow")]
        for old, new, as_pr in actions
    ],
    {"renames": len(actions), "promoted": promoted, "demoted": len(actions) - promoted},
)
```

Replace the execution pass + conclusion (from `outer: Result = Result()` to end of function) with:

```python
result: Result[Rows] = Result()
result.data = Rows(
    title="Renames",
    columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
    rows=[],
    metrics={"total": len(actions), "success": 0, "failed": 0},
)
outer: Result[None] = Result()

renames = {old: new for old, new, _ in actions}
for _, submodule in browse_submodules(submodules, tuple(renames.keys())):
    try:
        submodule.rename(renames[submodule.name])
        result.data.rows.append([submodule.name, colorize("renamed", "green")])
        result.data.metrics["success"] += 1
    except Exception as err:
        outer.add_error(f"{submodule.name}: {err}")
        result.data.rows.append([submodule.name, colorize("failed", "red")])
        result.data.metrics["failed"] += 1

outer.merge(commit_v2(repo, repo_path, [".gitmodules"], "submodules_rename", skip_hooks=True))

render(result, outer)
if not outer.ok:
    raise OopsError("; ".join(outer.errors))
```

Remove: `_show_summary` function definition, its import of `render` from `output.helper` (now
imports `render_plan` too), and the old `conclude` import (no longer needed in `manage`).

Note on `promoted`: keep the pre-computation before the `render_plan` call (it was in
`_show_summary`, move it to the caller):
```python
promoted = sum(1 for *_, as_pr in actions if as_pr)
render_plan(...)
```

### Success Criteria

#### Automated Verification
- [x] Lint: `make lint`
- [x] Tests: `make test`
- [x] Termination regression: `uv run pytest -vv tests/test_core_and_utils.py::test_termination_patterns_in_commands`
- [x] No `_show_summary`, `conclude` in `manage.py`: `! grep -n '_show_summary\|conclude' src/oops/commands/pr/manage.py`
- [x] `render_plan` exported from `output/helper.py`: `grep -n 'def render_plan' src/oops/output/helper.py`

#### Manual Verification
- [x] `oops pr manage` shows plan table, then Proceed, then execution summary table with ✓/✗
- [x] A rename failure within execution produces a ✗ row and ✗ ConclusionBlock

**Implementation Note**: Pause for manual confirmation before Phase 1.

---

## Phase 1: Migrate `submodules rename`

### Overview
Replace per-item loop with the standardised flow. Options: `--no-commit`, `-f/--force`, `names`.
(`--dry-run` and `--pull-request/--pr` intentionally dropped; `--prompt/--no-prompt` replaced by
`-f/--force` for consistency with `rewrite`.)

### Changes Required

#### `src/oops/commands/submodules/rename.py`
**Full rewrite** of imports + body:

```python
import click
from oops.commands.base import command
from oops.core.exceptions import AppAbort, EarlyExit, OopsError
from oops.core.models import Result, Rows
from oops.io.file import desired_path, get_symlink_map
from oops.output.helper import render, render_plan
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, conclude, prompt_choices, prompt_confirm


@command("rename", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--prompt/--no-prompt", is_flag=True, default=True, help="Prompt before renaming")
@click.option("--pull-request", "--pr", "force_pr", is_flag=True, help="Mark submodules as pull request")
@click.argument("names", nargs=-1, required=False)
def main(dry_run, no_commit, prompt, force_pr, names):
    repo, repo_path = require_repository()
    require_submodules(repo)
    mapping = get_symlink_map(repo_path)

    # Planning pass (no mutation): list of (old_name, new_name, pull_request)
    plan = []
    for submodule in repo.submodules:
        if names and submodule.name not in names:
            continue
        pull_request = force_pr or is_pull_request(submodule)
        first_symlink = mapping.get(submodule.path) if pull_request else None
        new_name = desired_path(submodule.url, pull_request=pull_request, suffix=first_symlink)
        if submodule.name != new_name:
            plan.append((submodule.name, new_name, pull_request))

    if not plan:
        conclude(True, "Nothing to rename.")
        raise EarlyExit()

    # Selection. --no-prompt selects all non-interactively.
    available = {old for old, *_ in plan}
    if prompt:
        selected = prompt_choices("Select submodule(s) to rename: ", available, available)
        if not selected:
            raise AppAbort()
    else:
        selected = available

    plan = [p for p in plan if p[0] in selected]
    if not plan:
        conclude(True, "Nothing to rename.")
        raise EarlyExit()

    render_plan(
        "Planned renames",
        [("From", "dim", "left"), ("To", "brand.primary", "left"), ("Kind", "dim", "right")],
        [[old, new, colorize("PR", "green") if pr else colorize("regular", "yellow")]
         for old, new, pr in plan],
        {"renames": len(plan)},
    )

    if dry_run:
        conclude(True, "Dry run complete — no changes applied.")
        raise EarlyExit()

    if prompt and not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    result: Result[Rows] = Result()
    result.data = Rows(
        title="Renames",
        columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": len(plan), "success": 0, "failed": 0},
    )
    outer: Result[None] = Result()

    for old, new, _ in plan:
        sub = next(s for s in repo.submodules if s.name == old)
        try:
            sub.rename(new)
            result.data.rows.append([old, colorize("renamed", "green")])
            result.data.metrics["success"] += 1
        except Exception as err:
            outer.add_error(f"{old}: {err}")
            result.data.rows.append([old, colorize("failed", "red")])
            result.data.metrics["failed"] += 1

    if not no_commit:
        outer.merge(commit_v2(repo, repo_path, [".gitmodules"], "submodules_rename", skip_hooks=True))
    else:
        outer.add_warning("Don't forget to commit .gitmodules to share changes with the team.")

    render(result, outer)
    if not outer.ok:
        raise OopsError("; ".join(outer.errors))
```

Notes:
- `--no-prompt` bypasses both `prompt_choices` and `prompt_confirm` (CI/scripted path).
- `click` import kept only for option decorators; no `click.echo`/`prompt`/`UsageError`.
- `conclude()` only on no-op / dry-run early exits.

### Success Criteria

#### Automated Verification
- [x] Lint: `make lint`
- [x] Tests: `make test`
- [x] Termination regression: `uv run pytest -vv tests/test_core_and_utils.py::test_termination_patterns_in_commands`
- [x] No legacy patterns: `! grep -nE 'click\.(echo|prompt|UsageError)|[^_]commit\(' src/oops/commands/submodules/rename.py`

#### Manual Verification
- [x] `oops submodules rename` shows checkbox → plan table → Proceed → execution summary + ✓
- [x] `-f/--force` runs without any prompt
- [x] `--no-commit` renames, skips commit, shows reminder warning in conclusion
- [x] Rename failure → ✗ row + ✗ conclusion + non-zero exit

**Implementation Note**: Pause for manual confirmation before Phase 2.

---

## Phase 2: Migrate `submodules rewrite`

### Overview
Same flow, adapted for move-and-relink mechanics. Keep `--base-dir`, `-f/--force`, `--no-commit`,
`names`. (`--dry-run` intentionally dropped.) Commit via `commit_v2(..., already_staged=True)` — symlinks and moved
paths are staged during execution. Submodules without URL / symlink become `skipped` rows.

### Changes Required

#### `src/oops/commands/submodules/rewrite.py`
**Full rewrite** of imports + body:

```python
from __future__ import annotations
import os
import shutil
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort, EarlyExit, OopsError
from oops.core.logger import live_progress
from oops.core.models import Result, Rows
from oops.io.file import desired_path, get_symlink_map, rewrite_symlink
from oops.output.helper import render, render_plan
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, conclude, prompt_choices, prompt_confirm


@command(name="rewrite", help=__doc__)
@click.option("--base-dir", default=lambda: config.submodules.current_path,
              help="Base directory for rewritten paths (default: .third-party)")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end")
@click.argument("names", nargs=-1, required=False)
def main(base_dir, force, dry_run, no_commit, names):  # noqa: C901, PLR0912
    repo, repo_path = require_repository()
    require_submodules(repo)
    mapping = get_symlink_map(repo_path)

    result: Result[Rows] = Result()
    result.data = Rows(
        title="Rewrites",
        columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": 0, "success": 0, "failed": 0, "skipped": 0},
    )
    outer: Result[None] = Result()

    # Planning pass. Non-actionable submodules become skipped rows now (not [warn] echoes).
    plan = []
    for submodule in repo.submodules:
        if names and submodule.name not in names:
            continue
        if not submodule.url or submodule.path not in mapping:
            result.data.rows.append([submodule.name, colorize("skipped", "yellow")])
            result.data.metrics["skipped"] += 1
            continue
        pull_request = is_pull_request(submodule)
        first_symlink = mapping[submodule.path] if pull_request else None
        target = desired_path(
            submodule.url, prefix=base_dir, pull_request=pull_request, suffix=first_symlink
        )
        if submodule.path != target:
            plan.append((submodule, target))

    if not plan:
        conclude(True, "No submodule needs rewriting.")
        raise EarlyExit()

    # Selection. --force selects all non-interactively.
    available = {s.name for s, _ in plan}
    if force:
        selected = available
    else:
        selected = prompt_choices("Select submodule(s) to rewrite: ", available, available)
        if not selected:
            raise AppAbort()
    plan = [(s, t) for s, t in plan if s.name in selected]
    if not plan:
        conclude(True, "Nothing accepted.")
        raise EarlyExit()

    render_plan(
        "Planned rewrites",
        [("Name", "brand.primary", "left"), ("From", "dim", "left"), ("To", "dim", "left")],
        [[s.name, s.path, str(t)] for s, t in plan],
        {"planned": len(plan)},
    )

    if dry_run:
        conclude(True, "Dry run mode, no changes applied.")
        raise EarlyExit()

    if not force and not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    # Execution: move submodules and record which paths moved.
    moved = []
    for submodule, target in plan:
        old_path = str(submodule.path)
        try:
            submodule.move(target)
            moved.append((old_path, str(target)))
            result.data.rows.append([submodule.name, colorize("moved", "green")])
            result.data.metrics["success"] += 1
        except Exception as err:
            outer.add_error(f"{submodule.name}: {err}")
            result.data.rows.append([submodule.name, colorize("failed", "red")])
            result.data.metrics["failed"] += 1

    # Rewrite symlinks that referenced moved paths.
    rewrites = 0
    with live_progress("Rewriting symlinks..."):
        for root, dirs, files in os.walk(repo.working_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for name in dirs + files:
                p = Path(root) / name
                if p.is_symlink():
                    for oldp, newp in moved:
                        if rewrite_symlink(p, oldp, newp):
                            rewrites += 1
                            repo.index.add([str(p)])
                            break
    outer.add_message(f"Symlinks rewritten: {rewrites}")

    # Remove old base dir if it still exists.
    if config.submodules.old_paths[0].exists():
        shutil.rmtree(config.submodules.old_paths[0])
        repo.index.remove([str(config.submodules.old_paths[0])], r=True, f=True)
        outer.add_message(f"Removed old submodule base dir: {config.submodules.old_paths[0]}")

    result.data.metrics["total"] = len(result.data.rows)

    if not no_commit and repo.index.diff(repo.head.commit):
        outer.merge(
            commit_v2(repo, repo_path, [], "submodules_rewrite", skip_hooks=True, already_staged=True)
        )
    elif no_commit:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render(result, outer)
    if not outer.ok:
        raise OopsError("; ".join(outer.errors))
```

Notes:
- `--force` bypasses both `prompt_choices` and `prompt_confirm`.
- `commit_v2(..., already_staged=True)` commits the index already staged by `submodule.move()`,
  `repo.index.add([symlink])`, and `repo.index.remove([old_base_dir])` — equivalent to the
  original raw `repo.index.commit`, but routing success/failure through `Result`.
- `log` import dropped (no `log.debug` calls remain in the new body).
- `noqa` reduced from `C901, PLR0912, PLR0915` to `C901, PLR0912` (statement count eases once
  echoes collapse into the table); keep whichever ruff still flags.

### Success Criteria

#### Automated Verification
- [x] Lint: `make lint`
- [x] Tests: `make test`
- [x] Termination regression: `uv run pytest -vv tests/test_core_and_utils.py::test_termination_patterns_in_commands`
- [x] No legacy patterns: `! grep -nE 'click\.(echo|prompt)|index\.commit\(' src/oops/commands/submodules/rewrite.py`

#### Manual Verification
- [x] `oops submodules rewrite` shows checkbox → plan table → Proceed → execution summary + ✓
- [x] Symlinks repoint to new paths; old base dir removed; commit created
- [x] `--force` runs without any prompt
- [x] `--no-commit` stages but does not commit, reminder warning visible in conclusion
- [x] Submodules without URL / symlink appear as `skipped` rows

---

## Testing Strategy

### Unit Tests
- If any existing tests for `rename`/`rewrite` exist, adjust them for the new flow: mock
  `prompt_choices`/`prompt_confirm`, assert `EarlyExit` on no-op, assert `OopsError` on
  execution failure.
- Add non-interactive case (`--no-prompt` / `--force`): assert no prompt is called.

### Manual Testing Steps
1. Sandbox repo with mis-named submodules → `oops submodules rename`; deselect one; confirm
   only selected ones rename and `.gitmodules` committed.
2. Sandbox repo with submodules outside `.third-party` → `oops submodules rewrite`; confirm
   move + symlink repoint + old-dir cleanup + commit.
3. Re-run each with `--dry-run`, `--no-commit`, non-interactive flag.
4. `oops pr manage` — toggle PR status; confirm execution summary table appears with ✓/✗ per row.

## Migration Notes

Pure I/O/control-flow refactor — no data migration. Single behavioral change: the per-item
`[Y/n/e]` custom-value edit is dropped in `rename` and `rewrite`. Document in changelog if
user-facing release notes are produced.

## References

- Research: `thoughts/shared/research/2026-06-19-mutating-command-presenter-pattern.md`
- Template: `src/oops/commands/submodules/prune.py:52-124`
- Targets: `src/oops/commands/pr/manage.py`, `src/oops/commands/submodules/rename.py`,
  `src/oops/commands/submodules/rewrite.py`
- New helper: `src/oops/output/helper.py` (`render_plan` + existing `render`)
- Primitives: `src/oops/services/git.py:242-319` (`commit_v2`, `already_staged`),
  `src/oops/utils/render.py:469-532` (`conclude`, `prompt_choices`, `prompt_confirm`),
  `src/oops/core/models.py:304-401` (`Result`, `Rows`)
- Prior plan: `thoughts/shared/plans/2026-06-19-pr-manage-presenter-refactor.md`
