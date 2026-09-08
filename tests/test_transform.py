import textwrap
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyapimaintenance.transform import load_rules, apply_transform_to_file  # noqa: E402

RULES_PATH = os.path.join(os.path.dirname(__file__), "fixture_rules.yaml")


def run_on_source(tmp_path, source, filename="sample.py"):
    rules = load_rules(RULES_PATH)
    filepath = tmp_path / filename
    filepath.write_text(textwrap.dedent(source))
    count, needs_review = apply_transform_to_file(str(filepath), rules)
    return count, needs_review, filepath.read_text()


def test_rename_passthrough_applies_on_real_pandas_object(tmp_path):
    source = """
        import pandas as pd

        df = pd.read_csv("data.csv")
        result = df.reindex(["a", "b"])
    """
    count, review, out = run_on_source(tmp_path, source)
    assert count == 1
    assert not review
    assert "df.reindex_axis_safe(" in out


def test_rename_passthrough_skips_unrelated_object_with_same_method_name(tmp_path):
    # `cache.reindex(...)` is NOT a pandas object - just something with a
    # same-named method. The old name-only matcher would have rewritten this
    # (a false positive / broken commit). The new matcher should leave it
    # alone and flag it for manual review instead.
    source = """
        class SearchCache:
            def reindex(self, keys):
                pass

        cache = SearchCache()
        cache.reindex(["a", "b"])
    """
    count, review, out = run_on_source(tmp_path, source)
    assert count == 0
    assert len(review) == 1
    assert review[0]["symbol"] == "reindex"
    assert "cache.reindex(" in out  # left untouched


def test_wrap_as_list_call_applies_on_tainted_variable(tmp_path):
    source = """
        import pandas as pd

        df = pd.DataFrame({"a": [1]})
        other = pd.DataFrame({"a": [2]})
        combined = df.append(other)
    """
    count, review, out = run_on_source(tmp_path, source)
    assert count == 1
    assert not review
    assert "pd.concat([df, other])" in out


def test_direct_namespace_call_is_high_confidence_even_without_taint(tmp_path):
    # A rule could target a bare module-level function too, e.g. pd.reindex(...)
    # directly on the alias, with no intermediate variable.
    source = """
        import pandas as pd

        pd.reindex(["a", "b"])
    """
    count, review, out = run_on_source(tmp_path, source)
    assert count == 1
    assert not review


def test_untracked_alias_is_low_confidence(tmp_path):
    # `reindex` called through an import that isn't the pandas alias at all -
    # should not be auto-applied.
    source = """
        import search_index as pd  # unrelated library shadowing the alias name "pd"

        pd.reindex(["a", "b"])
    """
    count, review, out = run_on_source(tmp_path, source)
    assert count == 0
    assert len(review) == 1