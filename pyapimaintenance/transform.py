import os
import libcst as cst
import yaml

from pyapimaintenance.resolution import AliasTaintResolver


def load_rules(path: str) -> dict[str, list[dict]]:
    with open(path) as f:
        data = yaml.safe_load(f)
    rules: dict[str, list[dict]] = {}
    for rule in data["rules"]:
        rules.setdefault(rule["old_symbol"], []).append(rule)
    return rules


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

    def __init__(self, rules: dict[str, list[dict]], filepath: str = "<unknown>"):
        self.rules = rules
        self.filepath = filepath
        self.applied_count = 0
        self.needs_review = []

        factories = AliasTaintResolver.factories_from_rules(rules)
        self.resolver = AliasTaintResolver(factories)

    def visit_Import(self, node: cst.Import) -> None:
        self.resolver.visit_Import(node)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        self.resolver.visit_ImportFrom(node)

    def visit_Assign(self, node: cst.Assign) -> None:
        self.resolver.visit_Assign(node)

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call):
        func = updated_node.func
        if not isinstance(func, cst.Attribute):
            return updated_node

        symbol = func.attr.value
        candidates = self.rules.get(symbol)
        if not candidates:
            return updated_node

        rule, confidence, reason = self.resolver.best_match(func, candidates)

        if confidence != "high" or rule is None:
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


def apply_transform_to_file(filepath: str, rules: dict[str, list[dict]]) -> tuple[int, list]:
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
        print(f"{len(total_review)} low-confidence match(es) skipped - review manually:")
        for item in total_review:
            print(f"  {item['filepath']}: `{item['code']}` ({item['reason']})")