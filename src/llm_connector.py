import os
from groq import Groq
import yaml

client = Groq(api_key=os.environ["GROQ_API_KEY"])

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
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  
        messages=[
            {"role": "system", "content": SCHEMA_PROMPT},
            {"role": "user", "content": changelog_text},
        ],
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    with open("raw_changelog.txt") as f:
        changelog_text = f.read()

    raw_output = extract_rules_from_changelog(changelog_text)

    with open("proposed_rules.yaml", "w") as f:
        f.write(raw_output)

