import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXTENSIONS = Path(__file__).resolve().parents[1] / "book" / "_ext"


class ChangelogNotificationsBuildTest(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, root, message):
        self.git(root, "add", "source")
        self.git(
            root, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-q", "-m", message,
            "-m", "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
        )
        return self.git(root, "rev-parse", "HEAD")

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
                    "html_theme_options = {'article_header_start': "
                    "['toggle-primary-sidebar.html', 'changelog-notifications.html']}\n"
                    "changelog_notifications_docname = 'updates'\n",
                    encoding="utf-8",
                )
                (source / "index.rst").write_text(
                    "Home\n====\n\n.. toctree::\n\n   updates\n", encoding="utf-8"
                )
                changelog = source / "updates.rst"
                changelog.write_text("Updates\n=======\n\nFirst.\n", encoding="utf-8")
                self.git(root, "init", "-q")
                first_commit = self.commit(root, "Initial documents")

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
                self.assertEqual(first["fingerprint"], first_commit)
                self.assertEqual(first["scheme"], "git-commit")
                self.assertTrue((output / "_static" / "changelog-notifications.js").is_file())
                self.assertTrue((output / "_static" / "changelog-notifications.css").is_file())
                html = (output / "index.html").read_text(encoding="utf-8")
                self.assertIn("changelog-notifications.js", html)
                left_header = html.split('<div class="header-article-items__start">', 1)[1].split(
                    '<div class="header-article-items__end">', 1
                )[0]
                self.assertIn('class="dropdown changelog-notifications"', left_header)
                self.assertIn('class="btn btn-sm" disabled', left_header)
                self.assertIn('data-bs-toggle="tooltip"', left_header)
                self.assertIn('class="dropdown-item-text" role="status"', left_header)
                self.assertIn('class="dropdown-menu changelog-notifications-intro" hidden', left_header)
                self.assertIn('data-changelog-enable>Enable notifications', left_header)
                self.assertIn('data-changelog-dismiss>Not now', left_header)
                self.assertEqual(html.count('class="dropdown changelog-notifications"'), 1)

                (source / "index.rst").write_text(
                    "Home\n====\n\nIntroduction.\n\n.. toctree::\n\n   updates\n",
                    encoding="utf-8",
                )
                self.commit(root, "Unrelated change")
                changelog.write_text("Updates\n=======\n\nSecond.\n", encoding="utf-8")
                build()
                self.assertEqual(json.loads(manifest.read_text())["fingerprint"], first_commit)

                second_commit = self.commit(root, "Update document")
                build()
                second = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(second["fingerprint"], second_commit)
                changelog.write_text("Updates\n=======\n\nFirst.\n", encoding="utf-8")
                reverted_commit = self.commit(root, "Revert document")
                build()
                self.assertEqual(json.loads(manifest.read_text())["fingerprint"], reverted_commit)
                self.assertNotEqual(first_commit, reverted_commit)

    def test_build_rejects_uncommitted_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "conf.py").write_text(
                f"import sys\nsys.path.insert(0, {str(EXTENSIONS)!r})\n"
                "extensions = ['changelog_notifications']\n",
                encoding="utf-8",
            )
            (source / "index.rst").write_text("Home\n====\n", encoding="utf-8")
            self.git(root, "init", "-q")
            self.commit(root, "Initial document")
            (source / "changelog.rst").write_text("Changelog\n=========\n", encoding="utf-8")
            self.git(root, "add", "source/changelog.rst")
            result = subprocess.run(
                [sys.executable, "-m", "sphinx", "-q", "-b", "html", str(source), str(root / "output")],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Document is not tracked in HEAD", result.stderr)


if __name__ == "__main__":
    unittest.main()
