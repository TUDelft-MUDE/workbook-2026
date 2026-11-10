"""Make \\href{url}{text} work in BibTeX fields rendered by pybtex."""
import re

from pybtex.richtext import HRef, Text

HREF = re.compile(r"\\href\{([^}]*)\}\{([^}]*)\}")
_original_from_latex = Text.from_latex.__func__


def _plain(cls, latex):
    if not latex:
        return cls()
    parsed = _original_from_latex(cls, latex)
    text = str(parsed)
    lead = " " if latex[0].isspace() and not text[:1].isspace() else ""
    trail = " " if latex[-1].isspace() and not text[-1:].isspace() else ""
    return cls(lead, parsed, trail)


def _from_latex(cls, latex):
    if not isinstance(latex, str) or "\\href{" not in latex:
        return _original_from_latex(cls, latex)
    parts = []
    position = 0
    for match in HREF.finditer(latex):
        parts.append(_plain(cls, latex[position:match.start()]))
        parts.append(HRef(match.group(1), _original_from_latex(cls, match.group(2))))
        position = match.end()
    parts.append(_plain(cls, latex[position:]))
    return cls(*parts)


def setup(app):
    Text.from_latex = classmethod(_from_latex)
    return {"parallel_read_safe": True}