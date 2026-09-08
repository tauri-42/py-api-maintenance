import os
import libcst as cst
import libcst.metadata as metadata
import yaml


def load_rules(path: str) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f)
    return {rule["old_symbol"]: rule for rule in data["rules"]}


class scan(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (metadata.PositionProvider,)

    def __init__(self, rules: dict, filepath: str):
        self.rules = rules
        self.filepath = filepath
        self.matches = []

    def visit_Call(self, node: cst.Call) -> None:
        if isinstance(node.func, cst.Attribute):
            symbol = node.func.attr.value
            if symbol in self.rules:
                pos = self.get_metadata(metadata.PositionProvider, node)
                self.matches.append({
                    "node": node,
                    "rule": self.rules[symbol],
                    "filepath": self.filepath,
                    "line": pos.start.line,
                })


if __name__ == "__main__":
    rules = load_rules("rules.yaml")
    root_dir = "target_repos/some_repo"

    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)

                with open(filepath) as f:
                    source = f.read()

                tree = cst.parse_module(source)
                wrapper = metadata.MetadataWrapper(tree)
                finder = scan(rules, filepath)
                wrapper.visit(finder)

                for match in finder.matches:
                    print(f"{match['filepath']}:{match['line']} -> {match['rule']['old_symbol']}")