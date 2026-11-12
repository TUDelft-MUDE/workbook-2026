import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


EXTENSIONS = Path(__file__).resolve().parents[1] / "book" / "_ext"


class HeaderParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.matches = {}

    def handle_starttag(self, tag, attrs):
        classes = set(dict(attrs).get("class", "").split())
        for name in ("changelog-notifications", "btn-fullscreen-button", "search-button__button"):
            if name in classes:
                self.matches[name] = self.stack.copy()
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


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
                    "html_theme_options = {'article_header_end': "
                    "['changelog-article-header-buttons.html']}\n"
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
                left_header, right_header = html.split('<div class="header-article-items__start">', 1)[1].split(
                    '<div class="header-article-items__end">', 1
                )
                self.assertNotIn('class="dropdown changelog-notifications"', left_header)
                self.assertIn('class="dropdown changelog-notifications"', right_header)
                notification_html = right_header.split(
                    '<div class="dropdown changelog-notifications">', 1
                )[1].split('<div class="dropdown dropdown-download-buttons">', 1)[0]
                parser = HeaderParser()
                parser.feed(html)
                self.assertEqual(len(parser.matches), 3)
                for ancestors in parser.matches.values():
                    self.assertTrue(any("article-header-buttons" in classes for _, classes in ancestors))
                self.assertIn("article-header-buttons", parser.matches["changelog-notifications"][-1][1])
                self.assertLess(right_header.index('class="dropdown changelog-notifications"'),
                                right_header.index("btn-fullscreen-button"))
                self.assertIn('class="btn btn-sm" disabled', right_header)
                self.assertNotIn('data-bs-toggle="tooltip"', notification_html)
                self.assertNotIn('title="Enable JavaScript to use changelog notifications"', notification_html)
                self.assertIn('class="dropdown-item-text" role="status"', right_header)
                self.assertIn('class="btn btn-sm dropdown-item changelog-notifications-toggle"', right_header)
                self.assertIn('class="btn__icon-container" data-changelog-toggle-icon', right_header)
                self.assertIn('data-changelog-toggle-label>Enable notifications', right_header)
                self.assertIn('class="btn__text-container" data-changelog-toggle-label', right_header)
                self.assertIn('data-changelog-dismiss', right_header)
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
