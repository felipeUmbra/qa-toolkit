"""Validate the YAML embedded in templates.md.

Why this exists: the two YAML authoring bugs that hit the real repo were both
found by parsing, not by reading - (1) a multi-line double-quoted scalar, and
(2) a heredoc body at column 0 silently terminating a `run: |` block. A
template that does not parse is worse than no template, because the agent will
copy it verbatim into a project and the failure only appears in CI.

Run: python test_templates.py
"""
import os
import re
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates.md")


def fenced_yaml_blocks(markdown):
    """Yield (heading_under, code) for every ```yaml fence."""
    blocks = []
    heading = "(top)"
    in_fence = False
    lang = None
    buf = []
    for line in markdown.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m and not in_fence:
            heading = m.group(1).strip()
        if line.startswith("```"):
            if not in_fence:
                in_fence, lang, buf = True, line[3:].strip(), []
                start_heading = heading
            else:
                if lang == "yaml":
                    blocks.append((start_heading, "\n".join(buf)))
                in_fence, lang, buf = False, None, []
            continue
        if in_fence:
            buf.append(line)
    return blocks


class TemplatesParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TEMPLATES, encoding="utf-8") as fh:
            cls.markdown = fh.read()
        cls.blocks = fenced_yaml_blocks(cls.markdown)

    def test_at_least_two_templates_present(self):
        self.assertGreaterEqual(len(self.blocks), 2,
                                "expected the CI and defect-hunt templates")

    def test_every_yaml_block_parses(self):
        for heading, code in self.blocks:
            with self.subTest(template=heading):
                try:
                    parsed = yaml.safe_load(code)
                except yaml.YAMLError as exc:
                    self.fail(f"{heading} does not parse: {exc}")
                self.assertIsInstance(parsed, dict)

    def test_ci_template_has_the_four_gates(self):
        ci = next(c for h, c in self.blocks if "ci-gates" in h)
        parsed = yaml.safe_load(ci)
        jobs = set(parsed["jobs"])
        for gate in ("typecheck", "unit", "accessibility", "e2e"):
            self.assertIn(gate, jobs)

    def test_ci_template_has_per_browser_cache_keys(self):
        """The shared-cache-key failure looks like a product bug and is not."""
        ci = next(c for h, c in self.blocks if "ci-gates" in h)
        keys = re.findall(r"key:.*?-(chromium|firefox|webkit)-", ci)
        self.assertGreaterEqual(
            len(set(keys)), 2,
            "each browser needs its OWN cache key; a shared key skips install")
        self.assertNotIn("hashFiles('package-lock.json') ${{ runner.os }}",
                         ci.replace("${{ runner.os }}-", ""))

    def test_ci_template_browser_install_is_unconditional(self):
        ci = next(c for h, c in self.blocks if "ci-gates" in h)
        parsed = yaml.safe_load(ci)
        e2e = parsed["jobs"]["e2e"]["steps"]
        installs = [s for s in e2e if "playwright install" in str(s.get("run", ""))]
        self.assertTrue(installs, "no browser install step found")
        for step in installs:
            self.assertNotIn("if", step,
                             "a conditional browser install is skipped on a "
                             "cache hit, which is the 'Executable doesn't "
                             "exist' failure")

    def test_defect_hunt_has_three_triggers(self):
        dh = next(c for h, c in self.blocks if "defect-hunt" in h)
        parsed = yaml.safe_load(dh)
        on = parsed.get(True, parsed.get("on"))
        for trigger in ("workflow_dispatch", "schedule", "workflow_run"):
            self.assertIn(trigger, on, f"missing trigger: {trigger}")

    def test_defect_hunt_issues_write_but_not_contents_write(self):
        dh = next(c for h, c in self.blocks if "defect-hunt" in h)
        parsed = yaml.safe_load(dh)
        perms = parsed["permissions"]
        self.assertEqual(perms.get("issues"), "write")
        self.assertNotIn("write", str(perms.get("contents")),
                         "the hunt must not be able to push code")

    def test_defect_hunt_triage_only_runs_on_failure(self):
        dh = next(c for h, c in self.blocks if "defect-hunt" in h)
        parsed = yaml.safe_load(dh)
        cond = parsed["jobs"]["triage-ci-failure"]["if"]
        self.assertIn("failure", cond)
        self.assertIn("workflow_run", cond)

    def test_heredocs_are_indented_inside_run_blocks(self):
        """A heredoc body at column 0 silently ends the `run: |` block.

        This is parseable-but-wrong in some shapes, so assert it directly: any
        line after `<<PROMPT_EOF` inside a run step must be indented.
        """
        for heading, code in self.blocks:
            lines = code.splitlines()
            for i, line in enumerate(lines):
                if "<<PROMPT_EOF" in line:
                    start = i + 1
                    indent = len(line) - len(line.lstrip())
                    for body in lines[start:]:
                        if body.strip() == "PROMPT_EOF":
                            break
                        if body.strip() and (len(body) - len(body.lstrip())) < indent:
                            self.fail(
                                f"{heading}: heredoc body line is less indented "
                                f"than its opening statement: {body!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
