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


if __name__ == "__main__":
    unittest.main()
