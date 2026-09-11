import os
from groq import Groq
import yaml

_client = None


def _get_client() -> Groq:
    # Built lazily, not at import time. `import pyapimaintenance.llm_connector`
    # happens transitively any time cli.py loads (e.g. for `scan` or `fix`,
    # which never touch the LLM at all) - eagerly constructing Groq() here
    # meant the whole CLI crashed with a GroqError if GROQ_API_KEY wasn't set,
    # regardless of which command you ran.
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


# Hardcoding one model here means every user is pinned to it until the next
# release, with no way to try a cheaper/newer/self-hosted-compatible model
# without editing source. Reading it from an env var (with this as fallback)
# costs nothing and unblocks that.
DEFAULT_MODEL = "llama-3.3-70b-versatile"
MODEL = os.getenv("PYAPIMAINTENANCE_GROQ_MODEL", DEFAULT_MODEL)

ALLOWED_SHAPES = {"rename_passthrough", "wrap_as_list_call"}

SCHEMA_PROMPT = """You extract API breaking-change rules from a changelog.
Output ONLY valid YAML matching this exact schema, nothing else:

rules:
  - old_symbol: <method/function name that changed>
    shape: <one of: rename_passthrough, wrap_as_list_call>
    new_symbol: <new method/function name>
    new_namespace: <only if shape is wrap_as_list_call, e.g. "pd">

If a change doesn't fit either shape, omit it entirely - do not guess.
"""


def extract_rules_from_changelog(changelog_text: str) -> str:
    response = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SCHEMA_PROMPT},
            {"role": "user", "content": changelog_text},
        ],
    )
    return response.choices[0].message.content


def validate_rules_yaml(raw_text: str) -> list[dict]:
    """Parse + schema-check the LLM's raw output before it ever touches disk.

    Without this, a bad completion (stray prose, wrong keys, hallucinated
    shape, missing new_namespace) gets written straight to
    rules/<lib>/rules.yaml and blows up the *next* `load_all_rules()` call
    with a confusing KeyError/YAMLError nowhere near the actual cause.
    Raises ValueError with a human-readable reason on any problem.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "yaml":
            text = text[4:]

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"LLM did not return valid YAML: {e}") from e

    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError("LLM output is missing the top-level 'rules' key")

    rules = data["rules"]
    if not isinstance(rules, list):
        raise ValueError("'rules' must be a list")

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"rule #{i} is not a mapping: {rule!r}")

        missing = [k for k in ("old_symbol", "shape", "new_symbol") if not rule.get(k)]
        if missing:
            raise ValueError(f"rule #{i} ({rule}) is missing required key(s): {missing}")

        if rule["shape"] not in ALLOWED_SHAPES:
            raise ValueError(
                f"rule #{i} has unknown shape '{rule['shape']}' "
                f"(expected one of {sorted(ALLOWED_SHAPES)})"
            )

        if rule["shape"] == "wrap_as_list_call" and not rule.get("new_namespace"):
            raise ValueError(f"rule #{i} uses wrap_as_list_call but is missing 'new_namespace'")

    return rules


if __name__ == "__main__":
    with open("raw_changelog.txt") as f:
        changelog_text = f.read()

    raw_output = extract_rules_from_changelog(changelog_text)
    validate_rules_yaml(raw_output)

    with open("proposed_rules.yaml", "w") as f:
        f.write(raw_output)