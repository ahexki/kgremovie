"""The release name shows up where people look for it."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import version  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_name(self):
        self.assertEqual(version.APP_TITLE, "KG beta version 3.0")
        self.assertEqual((ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(), version.APP_TITLE)

    def test_header_name(self):
        self.assertEqual(version.APP_HEADER, "KG ReMovie version 3.0")

    def test_it_is_used_in_the_window_the_launchers_and_the_readme(self):
        controller = (ROOT / "app" / "controller.py").read_text(encoding="utf-8")
        self.assertIn('self.title(f"{APP_TITLE}', controller)
        self.assertIn("text=APP_HEADER", controller)
        for name in ("RUN.bat", "INSTALL_REQUIREMENTS.bat", "INSTALL_MMS.bat"):
            self.assertIn("title KG beta version 3.0", (ROOT / name).read_text(encoding="utf-8"), name)
        self.assertTrue((ROOT / "README.md").read_text(encoding="utf-8").startswith("# KG beta version 3.0"))


if __name__ == "__main__":
    unittest.main()
