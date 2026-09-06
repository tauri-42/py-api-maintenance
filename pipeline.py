import subprocess
import os
from scan import load_rules
from transform import apply_transform_to_file
from verify import VerificationRunner


def run_pipeline(repo_path: str, rules_path: str):
    rules = load_rules(rules_path)

    subprocess.run(["git", "checkout", "-b", "auto-migration"], cwd=repo_path)

    changed_files = []
    for dirpath, _, filenames in os.walk(repo_path):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                count = apply_transform_to_file(filepath, rules)
                if count:
                    changed_files.append(filepath)

    if not changed_files:
        print("No matches found. Nothing to verify.")
        subprocess.run(["git", "checkout", "-"], cwd=repo_path)  # back to original branch
        return

    print(f"Transformed {len(changed_files)} file(s). Running verification...")

    runner = VerificationRunner(repo_path, changed_files)
    runner.run()
    print(runner.report())

    if runner.passed():
        subprocess.run(["git", "add", "-A"], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Automated API migration"], cwd=repo_path)
        print("PASSED — committed on branch 'auto-migration'. Ready to push/open a PR.")
    else:
        subprocess.run(["git", "checkout", "."], cwd=repo_path)   # discard broken changes
        subprocess.run(["git", "checkout", "-"], cwd=repo_path)
        print("FAILED — changes discarded, branch abandoned.")


if __name__ == "__main__":
    run_pipeline("target_repos/some_repo", "rules.yaml")