"""Notify readers when the published changelog changes."""

import json
import re
import subprocess
from pathlib import Path

from sphinx.errors import ExtensionError


def add_static_path(app):
    if app.builder.format == "html":
        app.config.html_static_path.append(
            str(Path(__file__).parent / "changelog_notifications_static")
        )


def write_changelog_fingerprint(app, exception):
    if exception is not None or app.builder.format != "html":
        return

    docname = app.config.changelog_notifications_docname
    try:
        source = Path(app.env.doc2path(docname))
        if not source.is_file():
            raise FileNotFoundError(source)
        git = ["git", "--literal-pathspecs", "-C", str(source.parent)]
        tracked = subprocess.run(
            [*git, "ls-tree", "--name-only", "HEAD", "--", source.name],
            check=True,
            capture_output=True,
            text=True,
        )
        if not tracked.stdout:
            raise ExtensionError(f"Document is not tracked in HEAD: {source}")
        result = subprocess.run(
            [*git, "log", "-1", "--format=%H", "--", source.name],
            check=True,
            capture_output=True,
            text=True,
        )
        fingerprint = result.stdout.strip()
        if not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", fingerprint):
            raise ExtensionError(f"No Git commit found for {source}")
        target = app.builder.get_target_uri(docname)
    except (OSError, KeyError, subprocess.CalledProcessError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise ExtensionError(
            f"Cannot prepare changelog notifications for {docname!r}: {detail}"
        ) from error

    output = Path(app.outdir) / "_static" / "changelog-notifications.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"fingerprint": fingerprint, "scheme": "git-commit", "url": target}) + "\n",
        encoding="utf-8",
    )


def setup(app):
    app.add_config_value("changelog_notifications_docname", "changelog", "html")
    app.add_js_file("changelog-notifications.js", defer="defer")
    app.add_css_file("changelog-notifications.css")
    app.connect("builder-inited", add_static_path)
    app.connect("build-finished", write_changelog_fingerprint)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
