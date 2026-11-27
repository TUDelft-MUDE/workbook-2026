import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/changelog_releases.py"
spec = importlib.util.spec_from_file_location("changelog_releases", SCRIPT)
releases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(releases)


class ChangelogReleasesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.previous_dir = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.previous_dir)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        (self.root / "book").mkdir()

    def git(self, *args):
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, text):
        (self.root / "book/changelog.md").write_text(text, encoding="utf-8")
        self.git("add", "book/changelog.md")
        self.git("commit", "-q", "--allow-empty", "-m", "Update")
        return self.git("rev-parse", "HEAD")

    def test_new_versions_are_tagged_at_introduction_not_every_edit(self):
        original = "## 2026-01-01: v2026.1.0\nOld\n\n## 2026-01-02: v2026.1.0\nDuplicate old\n"
        before = self.commit(original)
        first = self.commit("## 2026-01-03: v2026.2.0.pre-release\nNew\n\n" + original)
        self.commit("## 2026-01-03: v2026.2.0.pre-release\nCorrected\n\n" + original)
        second = self.commit("## 2026-01-04: v2026.3.0\nNext\n\n"
                             "## 2026-01-03: v2026.2.0.pre-release\nCorrected\n\n" + original)
        self.assertEqual(releases.new_releases(before, second), [
            ("v2026.2.0.pre-release", first, "Corrected"),
            ("v2026.3.0", second, "Next"),
        ])
        self.assertEqual(releases.new_releases(first, self.git("rev-parse", f"{second}^")), [])

    def test_fenced_headings_and_transient_versions_are_not_released(self):
        before = self.commit("## 2026-01-01: v2026.1.0\nOld\n")
        self.commit("## 2026-01-02: v2026.2.0\nTemporary\n")
        after = self.commit("## 2026-01-01: v2026.1.0\n```\n"
                            "## 2026-01-02: v2026.3.0\n```\n")
        self.assertEqual(releases.new_releases(before, after), [])

    def test_multiple_versions_in_one_commit_are_ordered_by_version(self):
        before = self.commit("## 2026-01-01: v2026.1.0\nOld\n")
        after = self.commit("## 2026-01-03: v2026.10.0\nTen\n"
                            "## 2026-01-02: v2026.9.0\nNine\n"
                            "## 2026-01-02: v2026.9.0.pre-release\nPreview\n")
        self.assertEqual([item[0] for item in releases.new_releases(before, after)],
                         ["v2026.9.0.pre-release", "v2026.9.0", "v2026.10.0"])

    def test_feature_branch_change_is_tagged_at_merge_commit(self):
        before = self.commit("## 2026-01-01: v2026.1.0\nOld\n")
        branch = self.git("branch", "--show-current")
        self.git("switch", "-c", "feature")
        feature = self.commit("## 2026-01-02: v2026.2.0\nNew\n")
        self.git("switch", branch)
        self.git("merge", "--no-ff", "-m", "Merge feature", "feature")
        merge = self.git("rev-parse", "HEAD")
        self.assertNotEqual(feature, merge)
        self.assertEqual(releases.new_releases(before, merge), [("v2026.2.0", merge, "New")])

    def test_end_to_end_plans_merge_tag_and_release_without_backfilling(self):
        before = self.commit("## 2026-01-01: v2026.1.0\nOld\n")
        branch = self.git("branch", "--show-current")
        self.git("switch", "-c", "feature")
        self.commit("## 2026-01-02: v2026.2.0.pre-release\nNew notes\n"
                    "## 2026-01-01: v2026.1.0\nOld\n")
        self.git("switch", branch)
        self.git("merge", "--no-ff", "-m", "Merge feature", "feature")
        merge = self.git("rev-parse", "HEAD")
        commands = []
        original_run = releases.run

        def fake_publish(*args, input=None):
            if args[:2] == ("git", "ls-remote"):
                return ""
            if args[0] == "gh":
                commands.append((args, input))
                return ""
            return original_run(*args, input=input)

        with patch.object(releases, "run", side_effect=fake_publish), \
             patch.object(releases.sys, "argv", ["script", before, merge, "owner/repo"]):
            releases.main()
        self.assertEqual(len(commands), 2)
        self.assertIn(f"sha={merge}", commands[0][0])
        self.assertIn("v2026.2.0.pre-release", commands[1][0])
        self.assertEqual(commands[1][1], "New notes")

    def test_duplicate_or_empty_new_entries_fail_without_publishing(self):
        before = self.commit("## 2026-01-01: v2026.1.0\nOld\n")
        duplicate = self.commit("## 2026-01-02: v2026.2.0\nA\n"
                                "## 2026-01-03: v2026.2.0\nB\n")
        with self.assertRaisesRegex(ValueError, "appears more than once"):
            releases.new_releases(before, duplicate)
        empty = self.commit("## 2026-01-02: v2026.3.0\n")
        with self.assertRaisesRegex(ValueError, "no release notes"):
            releases.new_releases(before, empty)

    def test_non_fast_forward_and_new_branch_are_rejected(self):
        before = self.commit("## 2026-01-01: v2026.1.0\nOld\n")
        after = self.commit("## 2026-01-02: v2026.2.0\nNew\n")
        with self.assertRaisesRegex(ValueError, "new branch"):
            releases.new_releases("0" * 40, after)
        with self.assertRaisesRegex(ValueError, "fast-forward"):
            releases.new_releases(after, before)

    def test_existing_tag_is_not_changed_or_released(self):
        with patch.object(releases, "run", return_value="existing tag") as run:
            releases.publish("v2026.2.0", "a" * 40, "Notes", "TUDelft-MUDE/workbook-2026")
        run.assert_called_once_with("git", "ls-remote", "--refs", "origin", "refs/tags/v2026.2.0")

    def test_creates_tag_and_prerelease_with_resolved_links(self):
        with patch.object(releases, "run", side_effect=["", "", ""]) as run:
            releases.publish(
                "v2026.2.0.pre-release", "a" * 40,
                "- [Assignment](assignments/GA/README.md)\n- [External](https://example.com/)",
                "TUDelft-MUDE/workbook-2026",
            )
        self.assertEqual(run.call_args_list[1].args[:4], (
            "gh", "api", "--method", "POST",
        ))
        command = run.call_args_list[2]
        self.assertIn("--verify-tag", command.args)
        self.assertIn("--prerelease", command.args)
        self.assertIn("/blob/" + "a" * 40 + "/book/assignments/GA/README.md", command.kwargs["input"])
        self.assertIn("https://example.com/", command.kwargs["input"])

    def test_release_failure_exposes_partially_created_tag(self):
        error = subprocess.CalledProcessError(1, ["gh"], stderr="Denied")
        with patch.object(releases, "run", side_effect=["", "", error]), \
             patch("sys.stderr") as stderr:
            with self.assertRaises(subprocess.CalledProcessError):
                releases.publish("v2026.2.0", "a" * 40, "Notes", "TUDelft-MUDE/workbook-2026")
        self.assertIn("create the release manually", "".join(call.args[0] for call in stderr.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
