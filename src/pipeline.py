import subprocess
import os
from src.transform import apply_transform_to_file
from src.verify import VerificationRunner


def run_pipeline(repo_path: str, rules: dict):
    subprocess.run(["git", "checkout", "-b", "auto-migration"], cwd=repo_path)

    changed_files = []
    needs_review = []
    for dirpath, _, filenames in os.walk(repo_path):
        if ".git" in dirpath.split(os.sep):
            continue
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                count, review = apply_transform_to_file(filepath, rules)
                if count:
                    changed_files.append(filepath)
                needs_review.extend(review)

    if needs_review:
        print(f"{len(needs_review)} low-confidence match(es) skipped - review manually:")
        for item in needs_review:
            print(f"  {item['filepath']}: `{item['code']}` ({item['reason']})")

    if not changed_files:
        print("No matches found. Nothing to verify.")
        subprocess.run(["git", "checkout", "-"], cwd=repo_path)
        return

    print(f"Transformed {len(changed_files)} file(s).")

    runner = VerificationRunner(repo_path, changed_files)
    runner.run()
    print(runner.report())

    if runner.passed():
        subprocess.run(["git", "add", "--"] + [os.path.relpath(f, repo_path) for f in changed_files],
                        cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Automated API migration"], cwd=repo_path)
        print("PASSED: committed on branch 'auto-migration'. Ready to push!!")
    else:
        subprocess.run(["git", "checkout", "."], cwd=repo_path)
        subprocess.run(["git", "checkout", "-"], cwd=repo_path)
        print("FAILED")