import os

from pyapimaintenance.transform import apply_transform_to_file


def walk_and_apply(repo_path: str, rules: dict) -> tuple[list[str], list[dict]]:
    """Walk `repo_path`, applying `rules` to every .py file found.

    Shared by `cli.fix` and `pipeline.run_pipeline` - they used to each carry
    their own copy of this loop, which is exactly the kind of duplication
    that drifts (e.g. only one of them skipped `.git/`).
    """
    changed_files = []
    needs_review = []
    for dirpath, _, filenames in os.walk(repo_path):
        if ".git" in dirpath.split(os.sep):
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, filename)
            count, review = apply_transform_to_file(filepath, rules)
            if count:
                changed_files.append(filepath)
            needs_review.extend(review)
    return changed_files, needs_review


def print_review(echo, needs_review: list[dict]) -> None:
    """`echo` is either `print` or `click.echo` - both take a single string."""
    if not needs_review:
        return
    echo(f"{len(needs_review)} low-confidence match(es) skipped - review manually:")
    for item in needs_review:
        echo(f"  {item['filepath']}: `{item['code']}` ({item['reason']})")