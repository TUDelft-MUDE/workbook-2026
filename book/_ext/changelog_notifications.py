"""Notify readers when the published changelog changes."""

import hashlib
import json
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
        fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
        target = app.builder.get_target_uri(docname)
    except (OSError, KeyError) as error:
        raise ExtensionError(
            f"Cannot prepare changelog notifications for {docname!r}"
        ) from error

    output = Path(app.outdir) / "_static" / "changelog-notifications.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"fingerprint": fingerprint, "url": target}) + "\n",
        encoding="utf-8",
    )


def setup(app):
    app.add_config_value("changelog_notifications_docname", "changelog", "html")
    app.add_js_file("changelog-notifications.js", defer="defer")
    app.add_css_file("changelog-notifications.css")
    app.connect("builder-inited", add_static_path)
    app.connect("build-finished", write_changelog_fingerprint)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
