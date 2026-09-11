import os
import subprocess
import json
import py_compile


class VerificationRunner:
    def __init__(self, repo_path: str, changed_files: list[str]):
        self.repo_path = repo_path
        self.changed_files = changed_files
        self.confidence = None
        self.result = {}

    def has_test_suite(self) -> bool:
        tests_dir = os.path.join(self.repo_path, "tests")
        if os.path.isdir(tests_dir):
            return True
        return any(
            f.startswith("test_") and f.endswith(".py")
            for f in os.listdir(self.repo_path)
        )

    def run(self):
        if self.has_test_suite():
            self.confidence = "high"
            self._run_test_diff()
        else:
            self.confidence = "low"
            self._run_syntax_and_import_checks()
        return self.result

    def _run_pytest(self) -> dict | None:
        report_path = os.path.join(self.repo_path, ".pyapimaintenance_pytest_report.json")
        proc = subprocess.run(
            ["pytest", "--json-report", f"--json-report-file={report_path}", "-q"],
            cwd=self.repo_path, capture_output=True, text=True,
        )
        if not os.path.exists(report_path):
            self.result.setdefault("warnings", []).append(
                f"pytest did not produce a report (returncode={proc.returncode}): "
                f"{proc.stderr.strip()[-500:]}"
            )
            return None
        with open(report_path) as f:
            report = json.load(f)
        os.remove(report_path)
        return {t["nodeid"]: t["outcome"] for t in report["tests"]}

    def _run_test_diff(self):
        stash = subprocess.run(
            ["git", "stash", "--include-untracked"],
            cwd=self.repo_path, capture_output=True, text=True,
        )
        if stash.returncode != 0:
            self.result.setdefault("warnings", []).append(
                f"git stash failed, falling back to syntax+import checks only: "
                f"{stash.stderr.strip()}"
            )
            self.confidence = "low"
            self._run_syntax_and_import_checks()
            return

        # git prints this exact message when there was nothing to stash -
        # in that case there's no matching pop to do.
        stashed_something = "No local changes to save" not in stash.stdout

        before = self._run_pytest()

        if stashed_something:
            pop = subprocess.run(
                ["git", "stash", "pop"],
                cwd=self.repo_path, capture_output=True, text=True,
            )
            if pop.returncode != 0:
                # Do NOT silently keep going here - the working tree is now
                # in an unknown state (still stashed, or a conflicted pop).
                # Running "after" tests against that would be meaningless.
                self.result.setdefault("warnings", []).append(
                    "git stash pop failed after running the 'before' tests - the "
                    f"working tree may still be stashed. Run `git stash list` / "
                    f"`git stash pop` manually in {self.repo_path}. "
                    f"stderr: {pop.stderr.strip()}"
                )
                self.confidence = "low"
                self.result["syntax_failures"] = []
                self.result["import_failures"] = []
                return

        after = self._run_pytest()

        if before is None or after is None:
            self.confidence = "low"
            self._run_syntax_and_import_checks()
            return

        self.result["new_failures"] = [
            t for t, o in after.items()
            if o == "failed" and before.get(t) != "failed"
        ]
        self.result["pre_existing_failures"] = [
            t for t, o in before.items() if o == "failed"
        ]

    def _run_syntax_and_import_checks(self):
        syntax_failures = []
        for fp in self.changed_files:
            try:
                py_compile.compile(fp, doraise=True)
            except py_compile.PyCompileError:
                syntax_failures.append(fp)

        import_failures = []
        for fp in self.changed_files:
            module = self._filepath_to_module(fp)
            proc = subprocess.run(
                ["python", "-c", f"import {module}"],
                cwd=self.repo_path, capture_output=True,
            )
            if proc.returncode != 0:
                import_failures.append(module)

        self.result["syntax_failures"] = syntax_failures
        self.result["import_failures"] = import_failures

    def _filepath_to_module(self, filepath: str) -> str:
        rel = os.path.relpath(filepath, self.repo_path)
        return rel.replace(os.sep, ".").removesuffix(".py")

    def passed(self) -> bool:
        if self.confidence == "high":
            return len(self.result.get("new_failures", [])) == 0
        return not self.result.get("syntax_failures") and not self.result.get("import_failures")

    def report(self) -> str:
        lines = [f"Verification confidence: {self.confidence.upper()}"]
        for w in self.result.get("warnings", []):
            lines.append(f"WARNING: {w}")
        if self.confidence == "high":
            lines.append(f"New failures: {self.result.get('new_failures', [])}")
            lines.append(f"Pre-existing failures (ignored): {self.result.get('pre_existing_failures', [])}")
        else:
            lines.append("WARNING: no test suite found, verified via syntax+import only.")
            lines.append(f"Syntax failures: {self.result.get('syntax_failures', [])}")
            lines.append(f"Import failures: {self.result.get('import_failures', [])}")
        lines.append(f"PASSED: {self.passed()}")
        return "\n".join(lines)