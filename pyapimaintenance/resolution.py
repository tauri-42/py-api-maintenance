"""Shared alias/taint tracking and confidence scoring.

scan.py (read-only reporting) and transform.py (rewriting) used to each carry
their own copy of "is this obj.method() call actually a call into the target
library" logic. That's the kind of thing that quietly drifts apart over one
or two edits until `scan` and `fix` disagree about what's high-confidence.
This module is the single source of truth for both.
"""

import libcst as cst


class AliasTaintResolver:
    """Tracks import aliases (`import pandas as pd`) and "tainted" variables
    (`df = pd.DataFrame(...)`) so callers can decide, for a given attribute
    call's receiver, which library (if any) it most likely belongs to.
    """

    def __init__(self, factories: dict[str, set[str]] | None = None):
        # factories: {library_module: {factory_name, ...}}
        self.factories = factories or {}
        self.aliases: dict[str, str] = {}
        self.tainted: dict[str, str] = {}

    @classmethod
    def factories_from_rules(cls, rules_by_symbol: dict[str, list[dict]]) -> dict[str, set[str]]:
        factories: dict[str, set[str]] = {}
        for rule_list in rules_by_symbol.values():
            for rule in rule_list:
                lib = rule.get("library_module")
                if lib:
                    factories.setdefault(lib, set()).update(rule.get("factories", []))
        return factories

    # --- CST visitor hooks: callers forward their own visit_* into these ---

    def visit_Import(self, node: cst.Import) -> None:
        for alias in node.names:
            module_name = self._dotted_name(alias.name)
            bound_name = alias.asname.name.value if alias.asname else module_name.split(".")[0]
            self.aliases[bound_name] = module_name

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if node.module is None:
            return
        module_name = self._dotted_name(node.module)
        for alias in (node.names if isinstance(node.names, (list, tuple)) else []):
            bound_name = alias.asname.name.value if alias.asname else alias.name.value
            self.aliases[bound_name] = f"{module_name}.{alias.name.value}"

    def visit_Assign(self, node: cst.Assign) -> None:
        lib = self.resolve_call_library(node.value)
        if lib is None:
            return
        for target in node.targets:
            if isinstance(target.target, cst.Name):
                self.tainted[target.target.value] = lib

    # --- resolution ---

    def resolve_call_library(self, node) -> str | None:
        """If `node` is a Call that either (a) calls straight into a known
        aliased module, or (b) calls a name bound to one of that library's
        declared factories, return the library module name."""
        if not isinstance(node, cst.Call):
            return None
        func = node.func
        if isinstance(func, cst.Attribute) and isinstance(func.value, cst.Name):
            alias = func.value.value
            module = self.aliases.get(alias)
            if module and module in self.factories:
                return module
        if isinstance(func, cst.Name):
            module = self.aliases.get(func.value)
            if module:
                base_module = module.split(".")[0]
                if base_module in self.factories:
                    return base_module
        return None

    def best_match(self, func: cst.Attribute, candidates: list[dict]) -> tuple[dict | None, str, str]:
        """`candidates` is every rule registered for this method name (there
        can be more than one if two different libraries both happen to
        define e.g. `reindex`). Pick whichever candidate's declared library
        actually matches what we know about the receiver.

        Returns (rule_or_None, confidence, reason). If nothing resolves with
        high confidence, `rule` is the first candidate (useful for the
        needs-review report) and confidence is "low".
        """
        obj = func.value
        wildcard = None

        for rule in candidates:
            expected_lib = rule.get("library_module")
            if expected_lib is None:
                wildcard = wildcard or rule
                continue
            if isinstance(obj, cst.Name):
                if self.aliases.get(obj.value) == expected_lib:
                    return rule, "high", "direct namespace call"
                if self.tainted.get(obj.value) == expected_lib:
                    return rule, "high", "call on variable tainted from known factory"

        if wildcard is not None:
            return wildcard, "high", "no library_module declared on rule"

        libs_tried = ", ".join(sorted({r.get("library_module") or "?" for r in candidates}))
        if isinstance(obj, cst.Name):
            reason = (
                f"'{obj.value}' is not a known alias or tainted variable for "
                f"any candidate rule's library ({libs_tried})"
            )
        else:
            reason = "receiver is not a simple name (attribute chain / call result)"
        return (candidates[0] if candidates else None), "low", reason

    def _dotted_name(self, node) -> str:
        if isinstance(node, cst.Name):
            return node.value
        if isinstance(node, cst.Attribute):
            return f"{self._dotted_name(node.value)}.{node.attr.value}"
        return ""