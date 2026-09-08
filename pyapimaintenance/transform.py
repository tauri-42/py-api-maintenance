import os
import libcst as cst
import yaml


def load_rules(path: str) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f)
    return {rule["old_symbol"]: rule for rule in data["rules"]}


def apply_wrap_as_list_call(node: cst.Call, original_obj: cst.BaseExpression, rule: dict):
    if len(node.args) != 1:
        return node

    return cst.Call(
        func=cst.Attribute(
            value=cst.Name(rule["new_namespace"]),
            attr=cst.Name(rule["new_symbol"]),
        ),
        args=[
            cst.Arg(value=cst.List(elements=[
                cst.Element(value=original_obj),
                cst.Element(value=node.args[0].value),
            ]))
        ],
    )


def apply_rename_passthrough(node: cst.Call, original_obj: cst.BaseExpression, rule: dict):
    return node.with_changes(
        func=node.func.with_changes(attr=cst.Name(rule["new_symbol"]))
    )


SHAPE_REGISTRY = {
    "wrap_as_list_call": apply_wrap_as_list_call,
    "rename_passthrough": apply_rename_passthrough,
}


class CodemodTransformer(cst.CSTTransformer):
    
    def __init__(self, rules: dict, filepath: str = "<unknown>"):
        self.rules = rules
        self.filepath = filepath
        self.applied_count = 0
        self.needs_review = []  

        self.aliases = {}
        self.tainted = {}

        self.factories = {}
        for rule in rules.values():
            lib = rule.get("library_module")
            if lib:
                self.factories.setdefault(lib, set()).update(rule.get("factories", []))

    def visit_Import(self, node: cst.Import) -> None:
        for alias in node.names:
            module_name = self._dotted_name(alias.name)
            bound_name = alias.asname.name.value if alias.asname else module_name.split(".")[0]
            self.aliases[bound_name] = module_name

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if node.module is None:
            return
        module_name = self._dotted_name(node.module)
        for alias in node.names if isinstance(node.names, (list, tuple)) else []:
            bound_name = alias.asname.name.value if alias.asname else alias.name.value
        
            self.aliases[bound_name] = f"{module_name}.{alias.name.value}"

    def _dotted_name(self, node) -> str:
        if isinstance(node, cst.Name):
            return node.value
        if isinstance(node, cst.Attribute):
            return f"{self._dotted_name(node.value)}.{node.attr.value}"
        return ""


    def visit_Assign(self, node: cst.Assign) -> None:
        lib = self._resolve_call_library(node.value)
        if lib is None:
            return
        for target in node.targets:
            if isinstance(target.target, cst.Name):
                self.tainted[target.target.value] = lib

    def _resolve_call_library(self, node) -> str | None:
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


    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call):
        func = updated_node.func
        if not isinstance(func, cst.Attribute):
            return updated_node

        symbol = func.attr.value
        if symbol not in self.rules:
            return updated_node

        rule = self.rules[symbol]
        confidence, reason = self._confidence(func, rule)

        if confidence != "high":
            self.needs_review.append({
                "filepath": self.filepath,
                "symbol": symbol,
                "reason": reason,
                "code": cst.Module(body=[]).code_for_node(original_node),
            })
            return updated_node

        shape = rule["shape"]
        handler = SHAPE_REGISTRY.get(shape)
        if handler is None:
            return updated_node

        new_node = handler(updated_node, func.value, rule)
        if new_node is not updated_node:
            self.applied_count += 1
        return new_node

    def _confidence(self, func: cst.Attribute, rule: dict) -> tuple[str, str]:
        expected_lib = rule.get("library_module")
        if expected_lib is None:
            return "high", "no library_module declared on rule"

        obj = func.value
        if isinstance(obj, cst.Name):
            if self.aliases.get(obj.value) == expected_lib:
                return "high", "direct namespace call"
            if self.tainted.get(obj.value) == expected_lib:
                return "high", "call on variable tainted from known factory"
            return "low", f"'{obj.value}' is not a known {expected_lib} alias or tainted variable"

        return "low", "receiver is not a simple name (attribute chain / call result)"


def apply_transform_to_file(filepath: str, rules: dict) -> tuple[int, list]:
    with open(filepath) as f:
        source = f.read()

    tree = cst.parse_module(source)
    transformer = CodemodTransformer(rules, filepath=filepath)
    modified_tree = tree.visit(transformer)

    if transformer.applied_count > 0:
        with open(filepath, "w") as f:
            f.write(modified_tree.code)

    return transformer.applied_count, transformer.needs_review


if __name__ == "__main__":
    rules = load_rules("rules.yaml")
    root_dir = "target_repos/some_repo"

    total_applied = 0
    total_review = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                count, review = apply_transform_to_file(filepath, rules)
                if count:
                    print(f"{filepath}: applied {count} fix(es)")
                    total_applied += count
                total_review.extend(review)

    print(f"\nTotal fixes applied: {total_applied}")
    if total_review:
        print(f"{len(total_review)} low-confidence match(es) skipped — review manually:")
        for item in total_review:
            print(f"  {item['filepath']}: `{item['code']}` ({item['reason']})")