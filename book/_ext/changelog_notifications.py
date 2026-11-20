"""Notify readers when the published changelog changes."""

import json
import re
import subprocess
from pathlib import Path

from sphinx.errors import ExtensionError


def configure_notifications(app, config):
    options = config.html_theme_options
    header = options.get("article_header_end")
    if isinstance(header, str):
        header = [item.strip() for item in header.split(",") if item.strip()]
    elif header is not None:
        header = list(header)

    custom_group = "changelog-article-header-buttons.html"
    standalone = "changelog-notifications-header.html"

    def normalized(item):
        return item if Path(item).suffix else f"{item}.html"

    enabled = options.pop(
        "use_notification_button",
        header is not None and any(normalized(item) in (custom_group, standalone) for item in header),
    )
    if not isinstance(enabled, bool):
        raise ExtensionError("html_theme_options.use_notification_button must be a boolean")
    config.changelog_notifications_enabled = enabled

    if header is None:
        if enabled:
            options["article_header_end"] = [custom_group]
        return
    if not enabled and not any(normalized(item) in (custom_group, standalone) for item in header):
        return

    result = []
    added = False
    has_group = any(normalized(item) in ("article-header-buttons.html", custom_group) for item in header)
    for item in header:
        name = normalized(item)
        if name in ("article-header-buttons.html", custom_group):
            if enabled:
                if not added:
                    result.append(custom_group)
                    added = True
            elif not any(normalized(previous) == "article-header-buttons.html" for previous in result):
                result.append("article-header-buttons.html" if name == custom_group else item)
        elif name == standalone:
            if enabled and not added and not has_group:
                result.append(item)
                added = True
        else:
            result.append(item)
    if enabled and not added:
        result.append(standalone)
    options["article_header_end"] = result


def add_static_path(app):
    if app.builder.format == "html" and app.config.changelog_notifications_enabled:
        app.config.html_static_path.append(
            str(Path(__file__).parent / "changelog_notifications_static")
        )
        app.add_js_file("changelog-notifications.js", defer="defer")
        app.add_css_file("changelog-notifications.css")


def add_ios_web_app_metadata(app, pagename, templatename, context, doctree):
    if not app.config.changelog_notifications_enabled:
        return
    metatags = context.get("metatags", "")
    if not re.search(
        r'<meta\b[^>]*\bname\s*=\s*(?:["\']apple-mobile-web-app-capable["\']|apple-mobile-web-app-capable(?=[\s/>]))',
        metatags,
        re.IGNORECASE,
    ):
        context["metatags"] = (
            metatags + '\n<meta name="apple-mobile-web-app-capable" content="yes" />'
        )


def write_changelog_fingerprint(app, exception):
    if exception is not None or app.builder.format != "html" or not app.config.changelog_notifications_enabled:
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
    app.add_config_value("changelog_notifications_enabled", False, "html")
    app.config.templates_path.append(
        str(Path(__file__).parent / "changelog_notifications_templates")
    )
    app.connect("config-inited", configure_notifications)
    app.connect("builder-inited", add_static_path)
    app.connect("html-page-context", add_ios_web_app_metadata)
    app.connect("build-finished", write_changelog_fingerprint)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
