import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyapimaintenance.llm_connector import validate_rules_yaml  # noqa: E402


def test_accepts_well_formed_output():
    text = """
rules:
  - old_symbol: reindex
    shape: rename_passthrough
    new_symbol: reindex_axis_safe
"""
    rules = validate_rules_yaml(text)
    assert len(rules) == 1


def test_strips_markdown_fences():
    text = """```yaml
rules:
  - old_symbol: reindex
    shape: rename_passthrough
    new_symbol: reindex_axis_safe
```"""
    rules = validate_rules_yaml(text)
    assert len(rules) == 1


def test_rejects_missing_rules_key():
    with pytest.raises(ValueError, match="top-level 'rules' key"):
        validate_rules_yaml("foo: bar")


def test_rejects_garbage_non_yaml():
    with pytest.raises(ValueError):
        validate_rules_yaml("Sure! Here are the rules you asked for:\nreindex -> reindex_axis_safe")


def test_rejects_unknown_shape():
    text = """
rules:
  - old_symbol: reindex
    shape: totally_made_up_shape
    new_symbol: reindex_axis_safe
"""
    with pytest.raises(ValueError, match="unknown shape"):
        validate_rules_yaml(text)


def test_rejects_wrap_as_list_call_missing_namespace():
    text = """
rules:
  - old_symbol: append
    shape: wrap_as_list_call
    new_symbol: concat
"""
    with pytest.raises(ValueError, match="new_namespace"):
        validate_rules_yaml(text)


def test_rejects_missing_required_keys():
    text = """
rules:
  - old_symbol: reindex
    shape: rename_passthrough
"""
    with pytest.raises(ValueError, match="missing required"):
        validate_rules_yaml(text)