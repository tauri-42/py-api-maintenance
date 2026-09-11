import os
import libcst as cst
import libcst.metadata as metadata
import yaml

from pyapimaintenance.resolution import AliasTaintResolver


def load_rules(path: str) -> dict[str, list[dict]]:
    with open(path) as f:
        data = yaml.safe_load(f)
    rules: dict[str, list[dict]] = {}
    for rule in data["rules"]:
        rules.setdefault(rule["old_symbol"], []).append(rule)
    return rules


class ScanVisitor(cst.CSTVisitor):
    """Read-only version of CodemodTransformer.leave_Call: reports every
    match plus the SAME confidence verdict `fix` would produce, using the
    shared resolver, instead of a bare name match with no relation to what
    `fix` will actually touch.
    """

    METADATA_DEPENDENCIES = (metadata.PositionProvider,)

    def __init__(self, rules: dict[str, list[dict]], filepath: str):
        self.rules = rules
        self.filepath = filepath
        self.matches = []
        factories = AliasTaintResolver.factories_from_rules(rules)
        self.resolver = AliasTaintResolver(factories)

    def visit_Import(self, node: cst.Import) -> None:
        self.resolver.visit_Import(node)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        self.resolver.visit_ImportFrom(node)

    def visit_Assign(self, node: cst.Assign) -> None:
        self.resolver.visit_Assign(node)

    def visit_Call(self, node: cst.Call) -> None:
        if not isinstance(node.func, cst.Attribute):
            return

        symbol = node.func.attr.value
        candidates = self.rules.get(symbol)
        if not candidates:
            return

        rule, confidence, reason = self.resolver.best_match(node.func, candidates)
        pos = self.get_metadata(metadata.PositionProvider, node)
        self.matches.append({
            "node": node,
            "rule": rule,
            "confidence": confidence,
            "reason": reason,
            "filepath": self.filepath,
            "line": pos.start.line,
        })


def scan_file(filepath: str, rules: dict[str, list[dict]]) -> list[dict]:
    with open(filepath) as f:
        source = f.read()

    tree = cst.parse_module(source)
    wrapper = metadata.MetadataWrapper(tree)
    finder = ScanVisitor(rules, filepath)
    wrapper.visit(finder)
    return finder.matches


def scan_repo(root_dir: str, rules: dict[str, list[dict]]) -> list[dict]:
    all_matches = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if ".git" in dirpath.split(os.sep):
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, filename)
            try:
                all_matches.extend(scan_file(filepath, rules))
            except cst.ParserSyntaxError:
                continue
    return all_matches


if __name__ == "__main__":
    rules = load_rules("rules.yaml")
    for match in scan_repo("target_repos/some_repo", rules):
        print(
            f"{match['filepath']}:{match['line']} -> {match['rule']['old_symbol']} "
            f"[{match['confidence']}] {match['reason']}"
        )