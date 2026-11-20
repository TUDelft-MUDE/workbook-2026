import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "block-html-tags.yml"


class HtmlTagWorkflowTest(unittest.TestCase):
    def git(self, root, *args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def write(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def scan(self, root):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = workflow.split("      - name: Find HTML tags\n        run: |\n", 1)[1]
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", textwrap.dedent(script)],
            cwd=root, capture_output=True, text=True,
        )

    def test_extensions_are_excluded_but_book_and_submodule_content_is_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            source = Path(directory) / "submodule"
            root.mkdir()
            source.mkdir()
            self.git(source, "init", "-q")
            self.write(source, "book/_ext/example.md", "Safe content\n")
            self.git(source, "add", ".")
            self.git(source, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                     "commit", "-qm", "Initial submodule")

            self.git(root, "init", "-q")
            self.write(root, "book/_ext/templates/example.html", "<div>Intended extension HTML</div>\n")
            self.write(root, "book/page.md", "Safe content\n")
            self.write(root, "book/page.ipynb", '{"cells":[{"source":["Safe"],"outputs":[{"text":"<div>"}]}]}')
            self.git(root, "-c", "protocol.file.allow=always", "submodule", "add", "-q",
                     str(source), "book/submodule")
            self.git(root, "add", ".")

            result = self.scan(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            self.write(root, "book/page.md", "<p>Unexpected HTML</p>\n")
            result = self.scan(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("repository/book/page.md", result.stdout)
            self.write(root, "book/page.md", "Safe content\n")

            self.write(root, "book/page.ipynb", '{"cells":[{"source":["<div>Unexpected</div>"]}]}')
            result = self.scan(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("repository/book/page.ipynb", result.stdout)
            self.write(root, "book/page.ipynb", '{"cells":[{"source":["Safe"]}]}')

            self.write(root, "book/submodule/book/_ext/example.md", "<div>Submodule HTML</div>\n")
            result = self.scan(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("book/submodule/book/_ext/example.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
