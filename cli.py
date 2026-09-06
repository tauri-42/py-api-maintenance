import click
from apitoolbox.scan import load_rules
from apitoolbox.transform import apply_transform_to_file
from apitoolbox.verify import VerificationRunner
from apitoolbox.extract_rules import extract_rules_from_changelog, save_proposed_rules
from apitoolbox.pipeline import run_pipeline
import os


@click.group()
def cli():
    """API migration toolbox - scan, fix, and verify breaking API changes."""
    pass


@cli.command()
@click.argument("repo")
@click.option("--library", required=True)
def scan(repo, library):
    rules = load_rules(f"rules/{library}/rules.yaml")
    # ...call your existing scan loop, pass rules and repo...
    click.echo(f"Scanning {repo} for {library} migrations...")


@cli.command()
@click.argument("repo")
@click.option("--library", required=True)
def fix(repo, library):
    rules = load_rules(f"rules/{library}/rules.yaml")
    changed = []
    for dirpath, _, filenames in os.walk(repo):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                if apply_transform_to_file(filepath, rules):
                    changed.append(filepath)
    click.echo(f"Fixed {len(changed)} file(s).")


@cli.command()
@click.argument("repo")
def verify(repo):
    changed_files = []  # TODO: needs wiring to fix's output - flagging, not solving now
    runner = VerificationRunner(repo, changed_files)
    runner.run()
    click.echo(runner.report())


@cli.command("extract-rules")
@click.option("--library", required=True)
@click.option("--changelog", required=True, type=click.Path(exists=True))
def extract_rules_cmd(library, changelog):
    with open(changelog) as f:
        text = f.read()
    raw_output = extract_rules_from_changelog(text)
    save_proposed_rules(library, raw_output)


@cli.command()
@click.argument("repo")
@click.option("--library", required=True)
def run(repo, library):
    run_pipeline(repo, library)


if __name__ == "__main__":
    cli()