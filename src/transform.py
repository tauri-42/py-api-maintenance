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
    def __init__(self, rules: dict):
        self.rules = rules
        self.applied_count = 0

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call):
        func = updated_node.func
        if not isinstance(func, cst.Attribute):
            return updated_node

        symbol = func.attr.value
        if symbol not in self.rules:
            return updated_node

        rule = self.rules[symbol]
        shape = rule["shape"]
        if shape not in SHAPE_REGISTRY:
            return updated_node

        handler = SHAPE_REGISTRY[shape]
        new_node = handler(updated_node, func.value, rule)

        if new_node is not updated_node:
            self.applied_count += 1
        return new_node


def apply_transform_to_file(filepath: str, rules: dict) -> int:
    with open(filepath) as f:
        source = f.read()

    tree = cst.parse_module(source)
    transformer = CodemodTransformer(rules)
    modified_tree = tree.visit(transformer)

    if transformer.applied_count > 0:
        with open(filepath, "w") as f:
            f.write(modified_tree.code)

    return transformer.applied_count


if __name__ == "__main__":
    rules = load_rules("rules.yaml")
    root_dir = "target_repos/some_repo"

    total_applied = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                count = apply_transform_to_file(filepath, rules)
                if count:
                    print(f"{filepath}: applied {count} fix(es)")
                    total_applied += count

    print(f"\nTotal fixes applied: {total_applied}")