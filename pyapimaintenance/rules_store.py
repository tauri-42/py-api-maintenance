import os
import json
import glob
import yaml

STATE_FILENAME = ".pyapimaintenance_state.json"
RULES_DIRNAME = "rules"


def load_state(repo_path: str) -> dict:
    path = os.path.join(repo_path, STATE_FILENAME)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_state(repo_path: str, state: dict) -> None:
    path = os.path.join(repo_path, STATE_FILENAME)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def rules_path_for(library: str, rules_dir: str = RULES_DIRNAME) -> str:
    return os.path.join(rules_dir, library, "rules.yaml")


def write_rules(library: str, raw_yaml_text: str, rules_dir: str = RULES_DIRNAME) -> str:

    out_path = rules_path_for(library, rules_dir)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(raw_yaml_text)
    return out_path


def load_all_rules(rules_dir: str = RULES_DIRNAME) -> dict[str, list[dict]]:
    """Rules are keyed by old_symbol -> LIST of rules, not a single rule.

    Two libraries can both happen to define a method called the same thing
    (`reindex`, `append`, whatever) - keying by symbol alone used to mean the
    second library's rule silently clobbered the first's in the merged dict.
    Keeping every candidate here lets the resolver (pyapimaintenance.resolution)
    pick the one whose library actually matches the call site.
    """
    merged: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(os.path.join(rules_dir, "*", "rules.yaml"))):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        for rule in data.get("rules", []) or []:
            merged.setdefault(rule["old_symbol"], []).append(rule)
    return merged