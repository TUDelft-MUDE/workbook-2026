"""Discover changelog versions and publish built GitHub releases."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit


CHANGELOG = "book/changelog.md"
HEADING = re.compile(
    r"^##\s+\d{4}-\d{2}-\d{2}:\s*(v\d+\.\d+\.\d+(?:\.pre-release)?)\s*$"
)
SECTION = re.compile(r"^##\s+(?:\d{4}-\d{2}-\d{2}:\s*)?v\d+(?:\.\d+)*(?:\.pre-release)?\s*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
LINK = re.compile(r"(\]\()<?([^\s()<>]+)>?(\))")


def run(*args, input=None, cwd=None, env=None):
    return subprocess.run(args, input=input, cwd=cwd, env=env, text=True,
                          capture_output=True, check=True).stdout


def sections(text):
    entries = {}
    version = None
    body = []
    fence = None

    def save():
        if version is not None:
            entries.setdefault(version, []).append("\n".join(body).strip())

    for line in text.splitlines():
        marker = FENCE.match(line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            if version is not None:
                body.append(line)
            continue
        if fence is None and SECTION.match(line):
            save()
            match = HEADING.fullmatch(line)
            version = match.group(1) if match else None
            body = []
        elif version is not None:
            body.append(line)
    save()
    return entries


def changelog(commit):
    return run("git", "show", f"{commit}:{CHANGELOG}")


def new_releases(before, after):
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", before) or not re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", after
    ):
        raise ValueError("Push commits must be full hexadecimal Git object IDs")
    if set(before) == {"0"}:
        raise ValueError("Cannot create releases for a new branch without a previous commit")
    commits = run("git", "rev-list", "--first-parent", "--reverse", f"{before}..{after}").splitlines()
    if not commits or run("git", "rev-parse", f"{commits[0]}^1").strip() != before:
        raise ValueError("Push is not a first-parent fast-forward; refusing to create releases")

    previous = sections(changelog(before))
    final = sections(changelog(after))
    added = set(final) - set(previous)
    for version in added:
        if len(final[version]) != 1:
            raise ValueError(f"New changelog version {version} appears more than once")
        if not final[version][0]:
            raise ValueError(f"New changelog version {version} has no release notes")

    introduced = {}
    for commit in commits:
        if not added - introduced.keys():
            break
        entries = sections(changelog(commit))
        for version in added & entries.keys() - introduced.keys():
            introduced[version] = commit
    if introduced.keys() != added:
        raise ValueError("Could not locate the introducing commit for every new version")

    def release_order(version):
        numbers = tuple(int(part) for part in version.removeprefix("v").split(".")[:3])
        return commits.index(introduced[version]), numbers, not version.endswith(".pre-release")

    return [(version, introduced[version], final[version][0]) for version in sorted(added, key=release_order)]


def release_notes(body, repository, commit):
    source = f"https://github.com/{repository}/blob/{commit}/{CHANGELOG}"

    def absolute_link(match):
        destination = match.group(2)
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc:
            return match.group(0)
        return f"{match.group(1)}{urljoin(source, destination)}{match.group(3)}"

    return LINK.sub(absolute_link, body)


def build_book(commit, directory, preprocess):
    checkout = Path(directory) / "source"
    run("git", "clone", "--no-checkout", "--no-hardlinks", str(Path.cwd()), str(checkout))
    run("git", "checkout", "--detach", commit, cwd=checkout)
    run("git", "submodule", "update", "--init", "--recursive", cwd=checkout)
    venv = Path(directory) / "venv"
    run(sys.executable, "-m", "venv", str(venv))
    run(str(venv / "bin/python"), "-m", "pip", "install", "-r", "requirements.txt", cwd=checkout)
    command = [str(venv / "bin/teachbooks"), "build"]
    if preprocess:
        command.append("--release")
    command.append("book/")
    env = os.environ.copy()
    env["PATH"] = f"{venv / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["VIRTUAL_ENV"] = str(venv)
    run(*command, cwd=checkout, env=env)
    output = checkout / "book/_build/html"
    if not output.is_dir() or not (output / "index.html").is_file():
        raise ValueError(f"Book build for {commit} did not produce HTML")
    return shutil.make_archive(str(Path(directory) / "workbook-html"), "zip", root_dir=output)


def publish(version, commit, body, repository, preprocess=False):
    ref = f"refs/tags/{version}"
    if run("git", "ls-remote", "--refs", "origin", ref).strip():
        print(f"Skipping {version}: tag already exists", flush=True)
        return
    print(f"Building {version} at {commit}", flush=True)
    with tempfile.TemporaryDirectory(prefix="changelog-release-") as directory:
        artifact = build_book(commit, directory, preprocess)
        run("gh", "api", "--method", "POST", f"repos/{repository}/git/refs",
            "-f", f"ref={ref}", "-f", f"sha={commit}")
        args = [
            "gh", "release", "create", version, artifact, "--repo", repository, "--target", commit,
            "--title", version, "--notes-file", "-", "--verify-tag",
        ]
        if version.endswith(".pre-release"):
            args.append("--prerelease")
        print(f"Creating {version} at {commit}", flush=True)
        try:
            run(*args, input=release_notes(body, repository, commit))
        except subprocess.CalledProcessError:
            print(f"Tag {version} was created, but the release failed; create the release manually.",
                  file=sys.stderr)
            raise
