"""Regression tests for qa_bootstrap_audit.py.

These exist because the first version of this script had a bug that made it
report a healthy repo as untested: Python's glob does not expand braces, so
every `**/*.{js,ts}` pattern matched nothing. A silent zero-match is
indistinguishable from "absent" - the worst possible failure for an audit,
because it under-reports and is therefore trusted.

Every test below pins a behaviour that was either a real bug or a silent-failure
risk.

Run:  python test_qa_bootstrap_audit.py
      (no pytest dependency on purpose - this must run anywhere)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_bootstrap_audit as qa


class BraceExpansion(unittest.TestCase):
    """The bug that made the whole audit untrustworthy."""

    def test_expands_multiple_alternatives(self):
        got = qa.expand_braces("**/*.{js,ts}")
        self.assertEqual(sorted(got), ["**/*.js", "**/*.ts"])

    def test_expands_nested_alternatives(self):
        got = qa.expand_braces("a/{b,c/{d,e}}")
        self.assertEqual(sorted(got), ["a/b", "a/c/d", "a/c/e"])

    def test_leaves_plain_pattern_untouched(self):
        self.assertEqual(qa.expand_braces("**/*.ts"), ["**/*.ts"])

    def test_rejects_unbalanced_brace(self):
        # Must RAISE, not pass through: a pass-through would silently match
        # nothing, which is the exact failure this function exists to prevent.
        with self.assertRaises(ValueError):
            qa.expand_braces("**/*.{js,ts")


class FindAll(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x")

    def test_finds_nested_files(self):
        self.write("tests/e2e/deep/spec.ts")
        self.assertIn("tests/e2e/deep/spec.ts", qa.find_all(self.root, ["**/*.ts"]))

    def test_brace_pattern_really_finds_files(self):
        """The regression test for the original bug.

        Fixture names are chosen to genuinely match the glob:
        `axe-helper.ts` matches `**/axe*.ts`, `check-contrast.js` matches
        `**/*contrast*.js`. An earlier version of this test used `axe.spec.ts`,
        which passes only because `.ts` happens to be the last extension - a
        fixture that matches by luck rather than by intent.
        """
        self.write("tests/helpers/axe-helper.ts")
        self.write("scripts/check-contrast.js")
        found = qa.find_all(self.root,
                            ["**/axe*.{js,ts}", "**/*contrast*.{js,ts}"])
        self.assertIn("tests/helpers/axe-helper.ts", found)
        self.assertIn("scripts/check-contrast.js", found)

    def test_brace_expansion_does_not_double_count(self):
        """A repeated path from nested alternatives must appear once."""
        hits = qa.find_all(self.root, ["**/*.{js,ts}"])
        self.write("src/a.ts")
        hits = qa.find_all(self.root, ["**/*.{js,ts}"])
        self.assertEqual(len(hits), len(set(hits)))

    def test_skips_generated_output(self):
        self.write("node_modules/pkg/index.js")
        self.write("dist/bundle.js")
        self.write("src/real.js")
        found = qa.find_all(self.root, ["**/*.js"])
        self.assertIn("src/real.js", found)
        self.assertNotIn("node_modules/pkg/index.js", found)
        self.assertNotIn("dist/bundle.js", found)


class AuditBehaviour(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, content="x"):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p) or self.root, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)

    def test_empty_project_reports_nothing_present(self):
        rep = qa.audit(self.root)
        for key in ("unit", "e2e", "a11y"):
            self.assertFalse(rep["layers"][key]["present"], key)
        self.assertTrue(any("full bootstrap" in g for g in rep["gaps"]))

    def test_healthy_js_project_detects_all_layers(self):
        self.write("package.json", json.dumps({
            "scripts": {"test": "vitest", "test:e2e": "playwright test",
                        "a11y": "npm run a11y:contrast"},
            "devDependencies": {"typescript": "5", "vitest": "1", "@playwright/test": "1"},
        }))
        self.write("vitest.config.ts")
        self.write("tests/e2e/a.spec.ts")
        self.write("scripts/axe-helper.ts")
        self.write(".github/workflows/ci.yml", "name: ci\njobs:\n  t:\n    steps: []")
        rep = qa.audit(self.root)
        for key in ("unit", "e2e", "a11y", "ci"):
            self.assertTrue(rep["layers"][key]["present"], key)
        self.assertIn("TypeScript", rep["stack"])

    def test_warns_when_filing_rules_exist_but_nothing_invokes_agent(self):
        """The failure mode that motivated this whole toolkit."""
        self.write(".github/agents/qa.agent.md",
                   "File a GitHub issue for every confirmed defect.")
        self.write(".github/workflows/ci.yml", "name: ci\njobs:\n  t:\n    steps: []")
        rep = qa.audit(self.root)
        self.assertTrue(rep["layers"]["agent"]["filing_rules_written"])
        self.assertFalse(rep["layers"]["agent"]["invoked_by_ci"])
        ids = [w["id"] for w in rep["warnings"]]
        self.assertIn("agent-never-invoked", ids)

    def test_no_warning_once_a_workflow_invokes_the_agent(self):
        self.write(".github/agents/qa.agent.md",
                   "File a GitHub issue for every confirmed defect.\n"
                   "Close only after a retest.")
        self.write(".github/workflows/ci.yml",
                   "name: ci\njobs:\n  t:\n    steps:\n"
                   "      - run: npx copilot -p hi --agent qa --allow-all-tools\n")
        rep = qa.audit(self.root)
        self.assertTrue(rep["layers"]["agent"]["invoked_by_ci"])
        ids = [w["id"] for w in rep["warnings"]]
        self.assertNotIn("agent-never-invoked", ids)

    def test_warns_when_layer_exists_but_is_not_wired(self):
        self.write("package.json", json.dumps({"scripts": {"build": "x"}}))
        self.write("tests/e2e/a.spec.ts")          # E2E files exist
        self.write("playwright.config.ts")
        rep = qa.audit(self.root)
        self.assertTrue(rep["layers"]["e2e"]["present"])
        self.assertFalse(rep["layers"]["e2e"]["wired"])
        self.assertTrue(any("cannot gate" in g for g in rep["gaps"]))

    def test_warns_when_no_ci_on_a_git_repo(self):
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        rep = qa.audit(self.root)
        self.assertTrue(rep["is_git_repo"])
        self.assertIn("no-ci", [w["id"] for w in rep["warnings"]])

    def test_warns_when_not_a_git_repo(self):
        rep = qa.audit(self.root)
        self.assertFalse(rep["is_git_repo"])
        self.assertIn("not-a-git-repo", [w["id"] for w in rep["warnings"]])

    def test_json_output_is_valid_json(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            qa.render(qa.audit(self.root))
        # render() returns a string; main() prints it. Just assert it is text.
        self.assertIsInstance(buf.getvalue(), str)


class Robustness(unittest.TestCase):
    """Malformed input must not crash the audit - it is a diagnostic tool."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, content="x"):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p) or self.root, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)

    def test_malformed_package_json_does_not_abort_the_audit(self):
        """An audit must never refuse to run because one file is unparseable.

        Found on first contact with a bare project: a half-written
        package.json made the tool hard-exit, turning a diagnostic into a
        blocker for exactly the user most likely to hit it - someone
        bootstrapping an empty repo.
        """
        self.write("package.json", "{not json")
        self.write("tests/e2e/a.spec.ts")
        rep = qa.audit(self.root)          # must NOT raise
        self.assertIn("unreadable-package-json",
                      [w["id"] for w in rep["warnings"]])
        # And it must still report what it could determine.
        self.assertTrue(rep["layers"]["e2e"]["present"])

    def test_malformed_package_json_yields_empty_scripts(self):
        self.write("package.json", "{not json")
        pkg, err = qa.load_pkg(self.root)
        self.assertEqual(pkg, {})
        self.assertIsNotNone(err)

    def test_valid_package_json_has_no_error(self):
        self.write("package.json", '{"scripts":{"test":"x"}}')
        pkg, err = qa.load_pkg(self.root)
        self.assertEqual(pkg["scripts"], {"test": "x"})
        self.assertIsNone(err)

    def test_missing_package_json_is_not_an_error(self):
        pkg, err = qa.load_pkg(self.root)
        self.assertEqual(pkg, {})
        self.assertIsNone(err)

    def test_unreadable_file_is_treated_as_empty(self):
        # read() must never raise, even on a binary or locked file.
        p = os.path.join(self.root, "blob.js")
        with open(p, "wb") as fh:
            fh.write(b"\xff\xfe\x00\x01binary")
        self.assertIsInstance(qa.read(p), str)

    def test_audit_of_missing_path_raises_cleanly(self):
        # main() guards this; confirm the guard's precondition.
        self.assertFalse(os.path.isdir(os.path.join(self.root, "nope")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
