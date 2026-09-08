import json
import os
import click

from pyapimaintenance.transform import apply_transform_to_file
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
    rules = load_all_rules(os.path.join(repo, "rules") if repo != "." else "rules")
    if not rules:
        click.echo("run pyapimaintenance config first.")
        return
    run_pipeline(repo, rules)



@cli.command()
@click.option("--repo", default=".")
@click.option("--library", default=None, help="Limit to one library's rules "
              "(defaults to every rule under rules/).")
def scan(repo, library):
    rules = load_all_rules() if library is None else _rules_for_one(library)
    click.echo(f"scanning {repo} ({'all libraries' if library is None else library})...")
    # ...call your existing scan loop, pass rules and repo...


@cli.command()
@click.option("--repo", default=".")
@click.option("--library", default=None)
def fix(repo, library):
    rules = load_all_rules() if library is None else _rules_for_one(library)
    changed = []
    all_review = []
    for dirpath, _, filenames in os.walk(repo):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                count, needs_review = apply_transform_to_file(filepath, rules)
                if count:
                    changed.append(filepath)
                all_review.extend(needs_review)

    manifest_path = os.path.join(repo, MANIFEST_PATH)
    with open(manifest_path, "w") as f:
        json.dump({"changed_files": changed}, f, indent=2)

    click.echo(f"Fixed {len(changed)} file(s). Manifest written to {manifest_path}")
    if all_review:
        click.echo(f"{len(all_review)} low-confidence match(es) skipped - review manually:")
        for item in all_review:
            click.echo(f"  {item['filepath']}: `{item['code']}` ({item['reason']})")


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


def _rules_for_one(library: str) -> dict:
    import yaml
    with open(os.path.join("rules", library, "rules.yaml")) as f:
        data = yaml.safe_load(f)
    return {rule["old_symbol"]: rule for rule in data["rules"]}


if __name__ == "__main__":
    cli()