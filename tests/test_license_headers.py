#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle
"""Every source file carries the license notice, and the notice agrees with LICENSE and the READMEs."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_GLOBS = ("*.py", "gui/*.py", "tests/*.py", "gui/qml/*.qml", "gui/qml/*.js", "install.sh", "hwpanel.service")
# optional shebang, then the SPDX line, then the copyright line; "#" or "//" depending on the language
NOTICE = re.compile(r"\A(?:#!.*\n)?(?:#|//) SPDX-License-Identifier: GPL-3\.0-or-later\n"
                    r"(?:#|//) Copyright \(C\) (?P<years>\d{4}(?:-\d{4})?) (?P<holder>\S.*)\n")


def source_files():
    return [f for pattern in SOURCE_GLOBS for f in sorted(ROOT.glob(pattern))]


class TestLicenseHeaders(unittest.TestCase):
    def test_every_source_file_has_the_notice(self):
        missing = [str(f.relative_to(ROOT)) for f in source_files() if not NOTICE.match(f.read_text(encoding="utf-8"))]
        self.assertEqual(missing, [], "files without the license notice at the top")

    def test_every_pattern_matches_files(self):
        # a typo in a glob must not turn the check above into a silent pass
        for pattern in SOURCE_GLOBS:
            self.assertTrue(list(ROOT.glob(pattern)), pattern)

    def test_all_files_name_the_same_holder_and_the_readmes_agree(self):
        notices = [NOTICE.match(f.read_text(encoding="utf-8")) for f in source_files()]
        holders = {m.group("years") + " " + m.group("holder") for m in notices if m}
        self.assertEqual(len(holders), 1, holders)
        line = f"Copyright (C) {holders.pop()}"
        for name in ("README.md", "README.de.md"):
            self.assertIn(line, (ROOT / name).read_text(encoding="utf-8"), name)

    def test_the_license_files_name_the_same_license(self):
        self.assertIn("GNU GENERAL PUBLIC LICENSE", (ROOT / "LICENSE").read_text(encoding="utf-8")[:200])
        for name in ("README.md", "README.de.md"):
            self.assertIn("GPL-3.0-or-later", (ROOT / name).read_text(encoding="utf-8"), name)

    def test_the_pattern_accepts_the_notice_and_rejects_near_misses(self):
        good = ("#!/usr/bin/env python3\n# SPDX-License-Identifier: GPL-3.0-or-later\n# Copyright (C) 2026 someone\n",
                "// SPDX-License-Identifier: GPL-3.0-or-later\n// Copyright (C) 2026-2027 some one\n",
                "# SPDX-License-Identifier: GPL-3.0-or-later\n# Copyright (C) 2026 x\n\n[Unit]\n")
        bad = ("# SPDX-License-Identifier: GPL-3.0-only\n# Copyright (C) 2026 x\n",
               "# SPDX-License-Identifier: GPL-3.0-or-later\n",
               "# SPDX-License-Identifier: GPL-3.0-or-later\n# Copyright 2026 x\n",
               "import os\n# SPDX-License-Identifier: GPL-3.0-or-later\n# Copyright (C) 2026 x\n",
               "# Copyright (C) 2026 x\n# SPDX-License-Identifier: GPL-3.0-or-later\n")
        for text in good:
            self.assertTrue(NOTICE.match(text), text)
        for text in bad:
            self.assertIsNone(NOTICE.match(text), text)


if __name__ == "__main__":
    unittest.main()
