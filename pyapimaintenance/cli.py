import json
import os
import click
import yaml

from pyapimaintenance.apply import walk_and_apply, print_review
from pyapimaintenance.scan import scan_repo
from pyapimaintenance.verify import VerificationRunner
from pyapimaintenance.extract import update_rules_for_repo, format_report
from pyapimaintenance.rules_store import load_all_rules
from pyapimaintenance.pipeline import run_pipeline

MANIFEST_PATH = ".pyapimaintenance_last_run.json"


@click.group()
def cli():
    pass


@cli.command()
@click.option("--repo", default=".", help="Defaults to the current directory - "
              "pyapimaintenance is meant to be run from inside the project it manages.")
@click.option("--requirements", default="requirements.txt")
def config(repo, requirements):
    report = update_rules_for_repo(repo, requirements_filename=requirements)
    click.echo(format_report(report))


@cli.command()
@click.option("--repo", default=".")
def startrun(repo):
    rules = _load_rules(repo, None)
    if not rules:
        click.echo("run pyapimaintenance config first.")
        return
    run_pipeline(repo, rules)


@cli.command()
@click.option("--repo", default=".")
@click.option("--library", default=None, help="Limit to one library's rules "
              "(defaults to every rule under rules/).")
def scan(repo, library):
    rules = _load_rules(repo, library)
    if not rules:
        click.echo("No rules found - run `pyapimaintenance config` first.")
        return

    click.echo(f"scanning {repo} ({'all libraries' if library is None else library})...")
    matches = scan_repo(repo, rules)

    if not matches:
        click.echo("No matches found.")
        return

    for match in matches:
        click.echo(
            f"{match['filepath']}:{match['line']} -> {match['rule']['old_symbol']} "
            f"[{match['confidence']}] {match['reason']}"
        )

    high = sum(1 for m in matches if m["confidence"] == "high")
    click.echo(
        f"\n{len(matches)} match(es) found "
        f"({high} high-confidence, {len(matches) - high} low-confidence)."
    )


@cli.command()
@click.option("--repo", default=".")
@click.option("--library", default=None)
def fix(repo, library):
    rules = _load_rules(repo, library)
    if not rules:
        click.echo("No rules found - run `pyapimaintenance config` first.")
        return

    changed, all_review = walk_and_apply(repo, rules)

    manifest_path = os.path.join(repo, MANIFEST_PATH)
    with open(manifest_path, "w") as f:
        json.dump({"changed_files": changed}, f, indent=2)

    click.echo(f"Fixed {len(changed)} file(s). Manifest written to {manifest_path}")
    print_review(click.echo, all_review)


@cli.command()
@click.option("--repo", default=".")
@click.option("--files", multiple=True)
def verify(repo, files):
    manifest_path = os.path.join(repo, MANIFEST_PATH)
    if files:
        changed_files = list(files)
    elif os.path.exists(manifest_path):
        with open(manifest_path) as f:
            changed_files = json.load(f)["changed_files"]
    else:
        raise click.UsageError(
            f"No changed files given and no manifest found at {manifest_path}. "
            "Run `fix` first, or pass files explicitly with --files."
        )

    if not changed_files:
        click.echo("No changed files to verify.")
        return

    runner = VerificationRunner(repo, changed_files)
    runner.run()
    click.echo(runner.report())


def _load_rules(repo: str, library: str | None) -> dict[str, list[dict]]:
    """Single place that resolves `--repo` -> rules dir for every command.

    fix/scan used to build this path themselves and get it wrong (looking in
    ./rules relative to the CWD instead of under --repo); startrun did it
    correctly. Now everyone goes through here.
    """
    rules_dir = os.path.join(repo, "rules") if repo != "." else "rules"

    if library is None:
        return load_all_rules(rules_dir)

    path = os.path.join(rules_dir, library, "rules.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)

    rules: dict[str, list[dict]] = {}
    for rule in data["rules"]:
        rules.setdefault(rule["old_symbol"], []).append(rule)
    return rules


if __name__ == "__main__":
    cli()