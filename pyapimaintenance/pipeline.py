import subprocess

from pyapimaintenance.apply import walk_and_apply, print_review
from pyapimaintenance.verify import VerificationRunner

BRANCH_NAME = "auto-migration"


def _current_branch(repo_path: str) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path, capture_output=True, text=True,
    )
    branch = proc.stdout.strip()
    return branch if branch and branch != "HEAD" else "main"


def _branch_exists(repo_path: str, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=repo_path, capture_output=True,
    )
    return proc.returncode == 0


def _start_fresh_branch(repo_path: str, original_branch: str) -> None:
    """`auto-migration` can be left over from a previous run - e.g. one that
    errored out before cleanup ran. Without this, `git checkout -b` fails
    outright on every run after the first. Always start clean."""
    if _branch_exists(repo_path, BRANCH_NAME):
        subprocess.run(["git", "checkout", original_branch], cwd=repo_path)
        subprocess.run(["git", "branch", "-D", BRANCH_NAME], cwd=repo_path)
    subprocess.run(["git", "checkout", "-b", BRANCH_NAME], cwd=repo_path)


def _cleanup_branch(repo_path: str, original_branch: str) -> None:
    subprocess.run(["git", "checkout", original_branch], cwd=repo_path)
    subprocess.run(["git", "branch", "-D", BRANCH_NAME], cwd=repo_path)


def run_pipeline(repo_path: str, rules: dict):
    original_branch = _current_branch(repo_path)
    _start_fresh_branch(repo_path, original_branch)

    changed_files, needs_review = walk_and_apply(repo_path, rules)
    print_review(print, needs_review)

    if not changed_files:
        print("No matches found. Nothing to verify.")
        _cleanup_branch(repo_path, original_branch)
        return

    print(f"Transformed {len(changed_files)} file(s).")

    runner = VerificationRunner(repo_path, changed_files)
    runner.run()
    print(runner.report())

    if runner.passed():
        import os
        subprocess.run(
            ["git", "add", "--"] + [os.path.relpath(f, repo_path) for f in changed_files],
            cwd=repo_path,
        )
        subprocess.run(["git", "commit", "-m", "Automated API migration"], cwd=repo_path)
        print(f"PASSED: committed on branch '{BRANCH_NAME}'. Ready to push!!")
    else:
        subprocess.run(["git", "checkout", "--", "."], cwd=repo_path)
        _cleanup_branch(repo_path, original_branch)
        print("FAILED")