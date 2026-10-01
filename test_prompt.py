"""Validate initqa.prompt.md.

A prompt file is the one artifact in this toolkit that a user drops into an
editor and runs. If its frontmatter is malformed it silently does not appear as
a slash command; if the embedded script is malformed, the agent writes a broken
tool into someone else's project and never finds out.

So this validates three things:
  1. frontmatter parses and carries the fields that make the command appear
  2. every fenced block is balanced and the EMBEDDED SCRIPT still runs
  3. the embedded script is byte-identical to the tested source
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = os.path.join(HERE, "initqa.prompt.md")
AUDIT = os.path.join(HERE, "qa_bootstrap_audit.py")


def prompt_text():
    with open(PROMPT, encoding="utf-8") as fh:
        return fh.read()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "frontmatter block missing or not delimited by --- at column 0"
    return yaml.safe_load(m.group(1))


def fenced_blocks(text):
    """Return [(lang, body)] for every fence, honouring variable-length fences."""
    blocks, i, lines = [], 0, text.splitlines()
    while i < len(lines):
        m = re.match(r"^(`{3,})(\w*)\s*$", lines[i])
        if not m:
            i += 1
            continue
        ticks, lang = m.group(1), m.group(2)
        body, j = [], i + 1
        while j < len(lines) and lines[j].strip() != ticks:
            body.append(lines[j])
            j += 1
        if j >= len(lines):
            raise AssertionError(f"unterminated {ticks} fence at line {i + 1}")
        blocks.append((lang, "\n".join(body)))
        i = j + 1
    return blocks


class Frontmatter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = prompt_text()
        cls.fm = frontmatter(cls.text)

    def test_name_and_description_present(self):
        self.assertIn("description", self.fm)
        self.assertGreater(len(self.fm["description"]), 40)

    def test_description_is_what_routing_sees(self):
        d = self.fm["description"].lower()
        # The router only reads this. If it lacks the trigger words, the
        # prompt is never offered when it is needed.
        for word in ("quality", "test", "ci", "scaffold"):
            self.assertIn(word, d, f"description lacks '{word}'")

    def test_argument_hint_present(self):
        self.assertIn("argument-hint", self.fm)

    def test_body_after_frontmatter(self):
        body = self.text.split("---\n", 2)[2]
        self.assertTrue(body.strip().startswith("#"))


class Fences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = fenced_blocks(prompt_text())

    def test_no_unterminated_fence(self):
        # fenced_blocks raises on an unterminated fence; reaching here is
        # the assertion.
        self.assertTrue(self.blocks)

    def test_contains_the_audit_script(self):
        langs = [lang for lang, _ in self.blocks]
        self.assertIn("python", langs)
        self.assertIn("markdown", langs)

    def test_embedded_audit_script_is_byte_identical(self):
        """Drift here means the prompt ships an untested variant."""
        with open(AUDIT, encoding="utf-8") as fh:
            expected = fh.read().rstrip("\n")
        embedded = [b for lang, b in self.blocks if lang == "python"]
        self.assertEqual(len(embedded), 1, "expected exactly one python block")
        self.assertEqual(
            embedded[0].rstrip("\n"), expected,
            "embedded script has drifted from qa_bootstrap_audit.py")

    def test_embedded_script_actually_runs(self):
        """Extract and execute it. A prompt that ships a broken tool is worse
        than no prompt."""
        embedded = [b for lang, b in self.blocks if lang == "python"][0]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "qa_bootstrap_audit.py")
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(embedded + "\n")
            r = subprocess.run([sys.executable, p, d],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0,
                             f"extracted script failed: {r.stderr[:400]}")
            self.assertIn("QA bootstrap audit", r.stdout)


class WorkflowContent(unittest.TestCase):
    """The prompt must carry the rules that were learned the hard way."""

    @classmethod
    def setUpClass(cls):
        cls.text = prompt_text()

    def test_requires_interview_before_scaffolding(self):
        low = self.text.lower()
        # The agent must be told to interview, and told not to assume. Match the
        # prompt's actual wording rather than a phrase I imagined.
        self.assertIn("askquestions", low.replace(" ", ""))
        self.assertIn("do not assume", low)

    def test_requires_proving_gates_fail(self):
        self.assertIn("never been seen failing", self.text)
        self.assertIn("Break something deliberately", self.text)

    def test_mentions_escalation_and_retest(self):
        self.assertIn("even when you are about to fix it", self.text)
        self.assertIn("closes only after a retest", self.text)

    def test_warns_about_schedule_without_secret(self):
        self.assertIn("comment out the scheduled trigger", self.text)

    def test_every_tool_the_body_names_is_granted(self):
        """A tool named in prose but absent from `tools:` is a silent no-op.

        The body told the agent to use the askQuestions tool while the
        frontmatter did not grant it. The agent would then either skip the
        interview - the one phase that cannot be skipped - or guess, and the
        prompt would still look perfectly correct to the reader.

        So assert the invariant rather than the one known instance: any tool
        referenced by name in the body must appear in the granted list.
        """
        granted = frontmatter(self.text).get("tools") or []
        granted_names = {t.split("/")[-1].lower() for t in granted}

        # Tools the body refers to by name, in backticks or bold.
        body = self.text.split("\n---\n", 1)[-1]
        referenced = set()
        for pattern in (
            r"\*\*(\w+)\*\* tool",
            r"the \*\*(\w+)\*\* tool",
            r"#tool:[\w/]+",
        ):
            for hit in re.findall(pattern, body, re.I):
                referenced.add(hit.split("/")[-1].lower())

        self.assertTrue(
            referenced,
            "no tool references found - the patterns need updating, not deleting",
        )
        missing = referenced - granted_names
        self.assertEqual(
            missing, set(),
            "body references tools the prompt does not grant: %s" % sorted(missing),
        )

    def test_templates_include_both_traps(self):
        blocks = fenced_blocks(self.text)
        templates = "\n".join(b for lang, b in blocks if lang == "markdown")
        self.assertIn("Executable doesn't exist", templates)
        self.assertIn("PER-BROWSER", templates)


if __name__ == "__main__":
    unittest.main(verbosity=2)
