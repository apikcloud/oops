# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: doc.py — src/oops/commands/project/presenters/doc.py

# The presenter receives the combined Result from `oops project doc` and turns
# it into the DocModel — a render-ready dict consumed by the Markdown site
# formatter. It is the ONLY place where the data is shaped; no rendering, no
# Rich, no formatter imports.

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import Presenter
from oops.output.docmodel import build_index, group_models_by_bare, resolve_ref


class ProjectDocPresenter(Presenter[Result]):
    """Stage C — build the DocModel from the combined IR + inventory Result."""

    def to_machine(self, result: Result) -> dict:
        data = result.unwrap

        ir = data.get("ir", {})
        inventory = data.get("inventory", {})
        modules = ir.get("modules", [])

        index = build_index(modules)

        for mod in modules:
            for f in mod.get("fields", []):
                f["model_ref"] = resolve_ref(f.get("model"), index)
                f["compute_ref"] = resolve_ref(f.get("compute"), index)
                f["comodel_ref"] = resolve_ref(f.get("comodel"), index)
            for m in mod.get("methods", []):
                m["model_ref"] = resolve_ref(m.get("model"), index)
            for v in mod.get("views", []):
                v["model_ref"] = resolve_ref(v.get("model"), index)
                v["inherit_ref"] = resolve_ref(v.get("inherit_id"), index)
            mod["inventory"] = inventory.get(mod["module"], {})

        models_by_bare = group_models_by_bare(modules)

        return {
            "metadata": ir.get("metadata", {}),
            "warnings": ir.get("warnings", []),
            "modules": modules,
            "models_by_bare": models_by_bare,
            "index": index,
        }
