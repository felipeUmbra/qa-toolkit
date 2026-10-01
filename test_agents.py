"""Tests for the tracked agent files.

These files used to exist only in a user profile, which meant no history and no
way back once they were lost. Tracking them in the repo fixes that, and creates
a new risk: a copy that drifts from the file actually in use is a fix that reads
as done but is not installed anywhere.

So the tests here assert the tracked copies are still valid agent files. They
deliberately do NOT compare against the live user profile, because the suite has
to pass on a machine that has never had this toolkit installed.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(HERE, "agents")
USER_AGENT = os.path.join(AGENTS, "user", "qa.agent.md")
EXAMPLE_AGENT = os.path.join(AGENTS, "project-example", "kboard.qa.agent.md")
README = os.path.join(AGENTS, "README.md")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "agent file has no frontmatter block"
    return m.group(1)


class UserAgentTests(unittest.TestCase):
    """The global agent must keep the properties that make it discoverable."""

    @classmethod
    def setUpClass(cls):
        cls.text = read(USER_AGENT)
        cls.fm = frontmatter(cls.text)

    def test_description_carries_the_routing_verbs(self):
        """The description is the only thing a router reads.

        If it stops mentioning discovering defects, the agent will never be
        summoned to find one, and every bug-filing rule below it becomes
        decoration. This exact failure is why the audit has an
        agent-never-invoked check.
        """
        low = self.fm.lower()
        for verb in ("defect", "test", "bug"):
            self.assertIn(verb, low,
                          "frontmatter description lost the routing verb %r" % verb)

    def test_declares_itself_user_invocable(self):
        self.assertIn("user-invocable: true", self.fm)

    def test_body_is_substantial(self):
        body = self.text.split("\n---\n", 1)[-1]
        self.assertGreater(len(body.splitlines()), 100,
                           "the doctrine body looks truncated")

    def test_does_not_leak_the_tools_prompt_syntax(self):
        """`tools:` in an agent file takes short names, not long-form ones.

        Long-form ids belong in a .prompt.md. A tools list of
        "codebase"/"search"/"editFiles" in an agent file grants nothing.
        """
        m = re.search(r"(?m)^tools:\s*\[(.*?)\]", self.fm)
        self.assertIsNotNone(m, "frontmatter declares no tools")
        granted = re.findall(r'"([^"]+)"', m.group(1))
        if granted:
            bad = [t for t in granted if "/" in t or t[0].isupper()]
            self.assertEqual(bad, [],
                             "agent file uses prompt-style tool ids: %s" % bad)

    def test_keeps_the_bootstrap_doctrine(self):
        for needle in ("/initqa", "NO_PYTHON", "NOT_WRITABLE"):
            self.assertIn(needle, self.text,
                          "agent lost its %s guidance" % needle)

    def test_states_the_repo_agent_wins_on_conflict(self):
        self.assertIn("authoritative for that project", self.text)


class ProjectAgentExampleTests(unittest.TestCase):
    """The repo-scoped example holds facts, not a restatement of the method."""

    @classmethod
    def setUpClass(cls):
        cls.text = read(EXAMPLE_AGENT)

    def test_has_frontmatter(self):
        frontmatter(self.text)

    def test_description_names_this_specific_project(self):
        fm = frontmatter(self.text)
        self.assertIn("kboard", fm.lower(),
                      "a repo agent must describe its own project")

    def test_does_not_restate_the_global_doctrine(self):
        """A restatement drifts. Point at the global file instead.

        A repo file may legitimately have a section *about* a global topic -
        what it must not do is re-explain the method. So the check is for the
        tell-tale sign: restating doctrine without deferring to the global
        agent, or copying a long run of its prose.

        kboard's "Diagnosing a flake here" is the correct pattern - it opens by
        deferring, then adds project-specific shortcuts.
        """
        low = self.text.lower()

        # If it discusses a global topic, it must say where the method lives.
        for topic in ("flake", "timeout", "route mock", "service worker"):
            if topic in low:
                self.assertTrue(
                    any(h in low for h in (
                        "follow the global",
                        "global agent",
                        "see the global",
                    )),
                    "repo agent discusses %r without deferring to the global "
                    "method" % topic,
                )

# Copying whole method passages is the real drift risk. A single shared
        # line is fine - a constraint like "NEVER leave test.only" is short,
        # high-value, and cheap to keep in both places. So is a shared command:
        # a repo file listing its own `npm run` invocations is the whole point
        # of a repo file.
        #
        # What breaks is a verbatim run of PROSE. That is an explanation which
        # will go stale in one file while the other still asserts it. So the
        # check ignores code fences and headings, and only fires on three or
        # more prose lines inside five consecutive lines.
        lines = read(USER_AGENT).splitlines()

        flags = []
        in_fence = False
        for line in lines:
            s = line.strip()
            if s.startswith("```"):
                in_fence = not in_fence
                flags.append(False)
                continue
            if in_fence or not s:
                flags.append(False)
                continue
            if s.startswith(("#", "tools:", "user-invocable:", "description:")):
                flags.append(False)
                continue
            if s == "---":
                flags.append(False)
                continue
            flags.append(True)

        mine = {ln.strip() for ln in self.text.splitlines()}

        # Compare on a run of consecutive PROSE lines only. Blank lines are
        # dropped first: markdown hard-wraps prose, so a copied paragraph is a
        # run of lines interrupted by blanks, and a window that counts those
        # blanks as content would never fire.
        prose_lines = [ln.strip() for ln, f in zip(lines, flags) if f]
        # A horizontal rule is not prose, but it sits between prose lines and
        # would otherwise be paired with whatever surrounds it.
        prose_lines = [ln for ln in prose_lines if ln != "---"]
        # Two consecutive prose lines. Markdown hard-wraps at ~75 chars, so a
        # two-line run is a full sentence of copied explanation - the smallest
        # unit that is unambiguously a passage rather than a shared phrase.
        run = 2
        for i in range(len(prose_lines) - run + 1):
            chunk = prose_lines[i:i + run]
            if all(c in mine for c in chunk):
                self.fail(
                    "repo agent copies a passage verbatim from the global file "
                    "(starting %r); defer to the global method instead" % chunk[0][:70]
                )

    def test_carries_project_facts(self):
        """The whole value of the repo file is project-specific detail."""
        self.assertRegex(self.text.lower(), r"\b(npm|npx|vitest|playwright)\b")


class ReadmeTests(unittest.TestCase):
    def test_explains_the_two_scopes(self):
        text = read(README)
        for needle in ("user/qa.agent.md", "project-example", "drift",
                       "wins"):
            self.assertIn(needle, text)

    def test_documents_how_to_install_and_commit_back(self):
        text = read(README)
        self.assertIn("Copy-Item", text,
                      "the readme must give a runnable install command")
        self.assertIn("git commit", text,
                      "edits are only really made once they are committed")


if __name__ == "__main__":
    unittest.main(verbosity=2)