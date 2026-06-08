# Resolve

::: oops.kb.resolve

---

## `resolve_symbol_root`

`resolve_symbol_root` finds the **original definer** of a symbol — the module
where it was first introduced — rather than the closest re-inheritor.

**Problem it solves:** when multiple modules all inherit a method (e.g.
`project.task.create` exists in `project`, `project_role`, and `hr_timesheet`),
`resolve_symbol` returns the closest dependency, which is often an intermediate
module that merely re-inherits without being the true origin.
`resolve_symbol_root` filters the candidates down to the one with no other
known upstream definition among them.

**Algorithm:**

1. Drop the custom module's own entry from the candidate list.
2. For each remaining candidate, check whether any other candidate appears in
   its depends chain. A candidate with no upstream in the set is a root.
3. If exactly one root exists, return it. On ties, prefer the most-core tier
   (`odoo > enterprise > apik > third-party`).
4. Fallback (all have upstreams / missing data): return the most-core tier
   entry.

Used by `io/refactor.py` to populate `kb_root_entry` on `SymbolInfo`, which
the `AnalyzePresenter` uses to resolve `inherited_from` references.
