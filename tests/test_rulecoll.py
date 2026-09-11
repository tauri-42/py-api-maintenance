import os
import sys
import textwrap
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyapimaintenance.rules_store import load_all_rules  # noqa: E402
from pyapimaintenance.transform import apply_transform_to_file  # noqa: E402


def _write_rules(rules_dir, library, rule):
    lib_dir = rules_dir / library
    lib_dir.mkdir(parents=True)
    (lib_dir / "rules.yaml").write_text(yaml.dump({"rules": [rule]}))


def test_two_libraries_sharing_a_symbol_name_dont_clobber_each_other(tmp_path):
    # pandas.reindex and some other library's unrelated .reindex(...) method,
    # both named "reindex". The old dict-keyed-by-symbol merge would let the
    # second one silently overwrite the first in load_all_rules().
    rules_dir = tmp_path / "rules"
    _write_rules(rules_dir, "pandas", {
        "old_symbol": "reindex", "shape": "rename_passthrough",
        "new_symbol": "reindex_axis_safe", "library_module": "pandas",
        "factories": ["DataFrame", "read_csv"],
    })
    _write_rules(rules_dir, "otherlib", {
        "old_symbol": "reindex", "shape": "rename_passthrough",
        "new_symbol": "rebuild_index", "library_module": "otherlib",
        "factories": ["Client"],
    })

    merged = load_all_rules(str(rules_dir))
    assert len(merged["reindex"]) == 2  # both kept, not one overwriting the other

    source = textwrap.dedent("""
        import otherlib

        client = otherlib.Client()
        client.reindex(["a", "b"])
    """)
    f = tmp_path / "sample.py"
    f.write_text(source)

    count, review = apply_transform_to_file(str(f), merged)
    assert count == 1
    assert not review
    assert "client.rebuild_index(" in f.read_text()
    # and it did NOT get pandas's rename applied instead
    assert "reindex_axis_safe" not in f.read_text()


def test_ambiguous_symbol_with_unresolvable_receiver_is_low_confidence(tmp_path):
    rules_dir = tmp_path / "rules"
    _write_rules(rules_dir, "pandas", {
        "old_symbol": "reindex", "shape": "rename_passthrough",
        "new_symbol": "reindex_axis_safe", "library_module": "pandas",
        "factories": ["DataFrame"],
    })
    _write_rules(rules_dir, "otherlib", {
        "old_symbol": "reindex", "shape": "rename_passthrough",
        "new_symbol": "rebuild_index", "library_module": "otherlib",
        "factories": ["Client"],
    })
    merged = load_all_rules(str(rules_dir))

    source = textwrap.dedent("""
        thing = get_thing_from_somewhere()
        thing.reindex(["a", "b"])
    """)
    f = tmp_path / "sample.py"
    f.write_text(source)

    count, review = apply_transform_to_file(str(f), merged)
    assert count == 0
    assert len(review) == 1
    assert "thing.reindex(" in f.read_text()