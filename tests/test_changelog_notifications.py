import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace


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
                    "html_theme_options = {'use_notification_button': True}\n"
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
                self.assertTrue((output / "_static" / "changelog-notifications-worker.js").is_file())
                html = (output / "index.html").read_text(encoding="utf-8")
                self.assertIn('<meta name="apple-mobile-web-app-capable" content="yes" />', html)
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
                self.assertIn('data-bs-toggle="dropdown"', notification_html)
                self.assertIn('</button>\n  <div class="dropdown-menu changelog-notifications-menu"', notification_html)
                self.assertNotIn('title="Enable JavaScript to use changelog notifications"', notification_html)
                self.assertIn('class="dropdown-item-text" role="status"', right_header)
                self.assertIn('class="btn btn-sm dropdown-item changelog-notifications-toggle"', right_header)
                self.assertIn('class="btn__icon-container" data-changelog-toggle-icon', right_header)
                self.assertIn('data-changelog-toggle-label>Enable notifications', right_header)
                self.assertIn('class="btn__text-container" data-changelog-toggle-label', right_header)
                self.assertIn('data-changelog-dismiss', right_header)
                notification_css = (
                    EXTENSIONS / "changelog_notifications_static" / "changelog-notifications.css"
                ).read_text(encoding="utf-8")
                self.assertIn(".changelog-notifications:hover > .changelog-notifications-menu", notification_css)
                self.assertIn(".changelog-notifications.hover-dismissed:hover", notification_css)
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
                "extensions = ['changelog_notifications']\n"
                "html_theme = 'sphinx_book_theme'\n"
                "html_theme_options = {'use_notification_button': True}\n",
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

    def test_theme_option_and_custom_header_components(self):
        cases = (
            ("default-enabled", {"use_notification_button": True}, True, True),
            ("disabled", {"use_notification_button": False}, False, True),
            ("omitted", {}, False, True),
            ("legacy", {"article_header_end": ["changelog-article-header-buttons.html"]}, True, True),
            ("legacy-disabled", {
                "use_notification_button": False,
                "article_header_end": ["changelog-article-header-buttons.html"],
            }, False, True),
            ("custom", {
                "use_notification_button": True,
                "article_header_end": ["before.html", "article-header-buttons", "after.html"],
            }, True, True),
            ("custom-string", {
                "use_notification_button": True,
                "article_header_end": "before, article-header-buttons, after",
            }, True, True),
            ("custom-without-buttons", {
                "use_notification_button": True,
                "article_header_end": ["before.html", "after.html"],
            }, True, False),
            ("custom-legacy-and-default", {
                "use_notification_button": True,
                "article_header_end": ["before.html", "changelog-article-header-buttons.html",
                                       "article-header-buttons.html", "after.html"],
            }, True, True),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            templates = source / "_templates"
            templates.mkdir()
            (templates / "before.html").write_text("<div>before-header</div>", encoding="utf-8")
            (templates / "after.html").write_text("<div>after-header</div>", encoding="utf-8")
            (source / "index.rst").write_text(
                "Home\n====\n\n.. toctree::\n\n   changelog\n", encoding="utf-8"
            )
            (source / "changelog.rst").write_text("Changelog\n=========\n", encoding="utf-8")
            self.git(root, "init", "-q")
            self.commit(root, "Initial documents")
            for name, options, enabled, has_buttons in cases:
                with self.subTest(case=name):
                    (source / "conf.py").write_text(
                        f"import sys\nsys.path.insert(0, {str(EXTENSIONS)!r})\n"
                        "extensions = ['changelog_notifications']\n"
                        "html_theme = 'sphinx_book_theme'\n"
                        "templates_path = ['_templates']\n"
                        f"html_theme_options = {options!r}\n",
                        encoding="utf-8",
                    )
                    output = root / name
                    result = subprocess.run(
                        [sys.executable, "-m", "sphinx", "-q", "-W", "-b", "html", str(source), str(output)],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    html = (output / "index.html").read_text(encoding="utf-8")
                    self.assertEqual(html.count('class="dropdown changelog-notifications"'), int(enabled))
                    self.assertEqual("changelog-notifications.js" in html, enabled)
                    self.assertEqual('name="apple-mobile-web-app-capable"' in html, enabled)
                    self.assertEqual((output / "_static" / "changelog-notifications.json").exists(), enabled)
                    self.assertEqual("btn-fullscreen-button" in html, has_buttons)
                    if name.startswith("custom"):
                        self.assertLess(html.index("before-header"), html.index("after-header"))
                        self.assertEqual(html.count("btn-fullscreen-button"), int(has_buttons))

    def test_disabling_on_an_incremental_build_removes_notification_assets_from_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "index.rst").write_text(
                "Home\n====\n\n.. toctree::\n\n   changelog\n", encoding="utf-8"
            )
            (source / "changelog.rst").write_text("Changelog\n=========\n", encoding="utf-8")
            self.git(root, "init", "-q")
            self.commit(root, "Initial documents")
            output = root / "output"
            for enabled in (True, False, True):
                (source / "conf.py").write_text(
                    f"import sys\nsys.path.insert(0, {str(EXTENSIONS)!r})\n"
                    "extensions = ['changelog_notifications']\n"
                    "html_theme = 'sphinx_book_theme'\n"
                    f"html_theme_options = {{'use_notification_button': {enabled}}}\n",
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [sys.executable, "-m", "sphinx", "-q", "-W", "-b", "html", str(source), str(output)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                html = (output / "index.html").read_text(encoding="utf-8")
                self.assertEqual("changelog-notifications.js" in html, enabled)
                self.assertEqual('class="dropdown changelog-notifications"' in html, enabled)
                self.assertEqual('name="apple-mobile-web-app-capable"' in html, enabled)

    def test_disabled_does_not_require_a_changelog_and_invalid_toggle_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "index.rst").write_text("Home\n====\n", encoding="utf-8")
            for option, should_succeed in ((False, True), ("false", False), (None, False)):
                (source / "conf.py").write_text(
                    f"import sys\nsys.path.insert(0, {str(EXTENSIONS)!r})\n"
                    "extensions = ['changelog_notifications']\n"
                    "html_theme = 'sphinx_book_theme'\n"
                    f"html_theme_options = {{'use_notification_button': {option!r}}}\n",
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [sys.executable, "-m", "sphinx", "-q", "-b", "html", str(source), str(root / "output")],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode == 0, should_succeed, result.stderr)
                if not should_succeed:
                    self.assertIn("use_notification_button must be a boolean", result.stderr)

    def test_existing_ios_web_app_metadata_is_preserved(self):
        sys.path.insert(0, str(EXTENSIONS))
        try:
            from changelog_notifications import add_ios_web_app_metadata
        finally:
            sys.path.pop(0)
        app = SimpleNamespace(config=SimpleNamespace(changelog_notifications_enabled=True))
        for tag in (
            "<meta name='apple-mobile-web-app-capable' content='no'>",
            "<META content=no name=apple-mobile-web-app-capable>",
        ):
            context = {"metatags": tag}
            add_ios_web_app_metadata(app, None, None, context, None)
            self.assertEqual(context["metatags"], tag)


if __name__ == "__main__":
    unittest.main()
