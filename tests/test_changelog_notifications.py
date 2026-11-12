import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXTENSIONS = Path(__file__).resolve().parents[1] / "book" / "_ext"


class ChangelogNotificationsBuildTest(unittest.TestCase):
    def test_html_builds_publish_current_fingerprint_and_assets(self):
        for builder, expected_url in (("html", "updates.html"), ("dirhtml", "updates/")):
            with self.subTest(builder=builder), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                output = root / "output"
                source.mkdir()
                (source / "conf.py").write_text(
                    f"import sys\nsys.path.insert(0, {str(EXTENSIONS)!r})\n"
                    "extensions = ['changelog_notifications']\n"
                    "html_theme = 'sphinx_book_theme'\n"
                    "changelog_notifications_docname = 'updates'\n",
                    encoding="utf-8",
                )
                (source / "index.rst").write_text(
                    "Home\n====\n\n.. toctree::\n\n   updates\n", encoding="utf-8"
                )
                changelog = source / "updates.rst"
                changelog.write_text("Updates\n=======\n\nFirst.\n", encoding="utf-8")

                def build():
                    subprocess.run(
                        [sys.executable, "-m", "sphinx", "-q", "-b", builder, str(source), str(output)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                build()
                manifest = output / "_static" / "changelog-notifications.json"
                first = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(first["url"], expected_url)
                self.assertEqual(first["fingerprint"], hashlib.sha256(changelog.read_bytes()).hexdigest())
                self.assertTrue((output / "_static" / "changelog-notifications.js").is_file())
                self.assertTrue((output / "_static" / "changelog-notifications.css").is_file())
                self.assertIn("changelog-notifications.js", (output / "index.html").read_text(encoding="utf-8"))
                self.assertIn('class="article-header-buttons"', (output / "index.html").read_text(encoding="utf-8"))

                changelog.write_text("Updates\n=======\n\nSecond.\n", encoding="utf-8")
                build()
                second = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(second["fingerprint"], hashlib.sha256(changelog.read_bytes()).hexdigest())
                self.assertNotEqual(first["fingerprint"], second["fingerprint"])


if __name__ == "__main__":
    unittest.main()
