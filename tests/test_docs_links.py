#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle
"""The documentation does not point at files or headings that do not exist, and it labels the screenshots as demo."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "README.de.md", "CONTRIBUTING.md", "CONTRIBUTING.de.md", "SECURITY.md", "SECURITY.de.md"]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")   # links and images
IMAGE = re.compile(r"!\[[^\]]*\]\((docs/screenshots/[^)\s]+)\)")


def slug(heading):
    """GitHub's anchor of a heading: lower case, punctuation removed (umlauts stay), spaces become hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def headings(text):
    out, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6}\s", line):
            out.append(line.lstrip("#").strip())
    return out


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class TestDocsLinks(unittest.TestCase):
    def test_relative_links_and_images_point_at_existing_files_and_headings(self):
        problems = []
        for name in DOCS:
            for target in LINK.findall(read(name)):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path, _, anchor = target.partition("#")
                dest = ROOT / path if path else ROOT / name
                if not dest.exists():
                    problems.append(f"{name}: missing file {target}")
                elif anchor and anchor not in {slug(h) for h in headings(dest.read_text(encoding="utf-8"))}:
                    problems.append(f"{name}: missing heading {target}")
        self.assertEqual(problems, [])

    def test_the_slug_follows_githubs_rules(self):
        for heading, anchor in (("Limits and behavior", "limits-and-behavior"), ("Lüftersteuerung", "lüftersteuerung"),
                                ("Installation (fish/bash)", "installation-fishbash"), ("Support und Mitarbeit", "support-und-mitarbeit")):
            self.assertEqual(slug(heading), anchor)

    def test_the_check_notices_a_broken_link(self):
        # the pattern must catch images as well as links, otherwise a missing screenshot would pass unnoticed
        self.assertEqual(LINK.findall("![alt](a/b.png) and [text](c.md#d) and [x](https://e.org)"),
                         ["a/b.png", "c.md#d", "https://e.org"])

    def test_both_readmes_show_the_same_screenshots_in_their_language(self):
        english = [Path(p).name for p in IMAGE.findall(read("README.md"))]
        german = [Path(p).name for p in IMAGE.findall(read("README.de.md"))]
        self.assertTrue(english, "README.md has no screenshots")
        self.assertEqual(sorted(set(english)), sorted(set(german)))
        self.assertTrue(all("/en/" in p for p in IMAGE.findall(read("README.md"))))
        self.assertTrue(all("/de/" in p for p in IMAGE.findall(read("README.de.md"))))

    def test_the_screenshots_are_labeled_as_demo_data(self):
        # the pictures come from tests/demo_client.py, not from real hardware, and the READMEs have to say so
        for name in ("README.md", "README.de.md"):
            self.assertIn("tests/demo_client.py", read(name), name)


WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


class TestCiWorkflow(unittest.TestCase):
    """The GitHub workflow runs the tests, and what it tests matches what the READMEs promise."""

    @classmethod
    def setUpClass(cls):
        assert WORKFLOW.exists(), f"{WORKFLOW.relative_to(ROOT)} is missing"
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_it_runs_the_suite_on_pushes_and_pull_requests(self):
        for needle in ("push:", "pull_request:", "python -m unittest discover -s tests"):
            self.assertIn(needle, self.text)

    def test_it_has_read_only_rights(self):
        # a workflow that runs code from pull requests must not be able to write to the repository
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read$")

    def test_the_lowest_python_the_readmes_promise_is_the_lowest_one_tested(self):
        promised = {name: re.search(r"Python ≥ (3\.\d+)", read(name)) for name in ("README.md", "README.de.md")}
        self.assertTrue(all(promised.values()), "a README names no minimum Python version")
        self.assertEqual(len({m.group(1) for m in promised.values()}), 1, "the READMEs disagree")
        minimum = promised["README.md"].group(1)
        matrix = re.search(r"python:\s*\[([^\]]*)\]", self.text)
        self.assertTrue(matrix, "no Python matrix in the workflow")
        tested = re.findall(r"3\.\d+", matrix.group(1))
        self.assertEqual(min(tested, key=lambda v: int(v.split(".")[1])), minimum)

    def test_the_gui_job_fails_when_a_test_is_skipped(self):
        # without this a missing library would turn the GUI tests into silent skips and the job would stay green
        self.assertIn("grep -q skipped", self.text)
        self.assertIn("PySide6", self.text)


if __name__ == "__main__":
    unittest.main()
