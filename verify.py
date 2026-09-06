# verify.py
import os
import subprocess
import json
import py_compile


class VerificationRunner:
    def __init__(self, repo_path: str, changed_files: list[str]):
        self.repo_path = repo_path
        self.changed_files = changed_files
        self.confidence = None   # "high" or "low", set once run() completes
        self.result = {}         # tier-specific findings


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


    def _run_pytest(self) -> dict:
        subprocess.run(
            ["pytest", "--json-report", "--json-report-file=/tmp/report.json", "-q"],
            cwd=self.repo_path, capture_output=True,
        )
        with open("/tmp/report.json") as f:
            report = json.load(f)
        return {t["nodeid"]: t["outcome"] for t in report["tests"]}

    def _run_test_diff(self):
        subprocess.run(["git", "stash"], cwd=self.repo_path)
        before = self._run_pytest()

        subprocess.run(["git", "stash", "pop"], cwd=self.repo_path)
        after = self._run_pytest()

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
        if self.confidence == "high":
            lines.append(f"New failures: {self.result['new_failures']}")
            lines.append(f"Pre-existing failures (ignored): {self.result['pre_existing_failures']}")
        else:
            lines.append("WARNING: no test suite found, verified via syntax+import only.")
            lines.append(f"Syntax failures: {self.result['syntax_failures']}")
            lines.append(f"Import failures: {self.result['import_failures']}")
        lines.append(f"PASSED: {self.passed()}")
        return "\n".join(lines)


if __name__ == "__main__":
    changed_files = ["target_repos/some_repo/some_file.py"]  # pass real list from transform.py's output
    runner = VerificationRunner("target_repos/some_repo", changed_files)
    runner.run()
    print(runner.report())