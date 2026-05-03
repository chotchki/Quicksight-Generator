"""Compose rich-text XML for QuickSight ``SheetTextBox.Content``.

QuickSight accepts a small XML dialect inside a single ``<text-box>`` root
(undocumented — confirmed by round-tripping a UI-authored text box via
``describe-analysis-definition``):

* ``<inline font-size="36px" color="#hex">text</inline>`` — sized / tinted run
* ``<br/>`` — explicit line break
* ``<ul><li class="ql-indent-0">item</li></ul>`` — bulleted list
  (the ``ql-indent-0`` class is required for top-level bullets)
* ``<a href="..." target="_self">Link</a>`` — hyperlink
* Body text between tags must be XML-escaped

Theme tokens aren't supported by the parser, so colors are resolved to hex
at generate-time and interpolated here by the caller.

Authoring helpers:

* ``body(text)`` — single-line plain text, XML-escaped. Use for one-shot
  prose with no paragraph breaks or links.
* ``markdown(text)`` — multi-paragraph prose with optional inline
  ``[text](url)`` links. ``\\n\\n`` paragraph breaks become ``<br/><br/>``,
  single ``\\n`` becomes ``<br/>``, ``[text](url)`` becomes a clickable
  ``<a href="...">``. Use whenever the source string is L2-YAML-supplied
  description prose (which is markdown-shaped by convention).
"""

from __future__ import annotations

import re
from typing import Iterable
from xml.sax.saxutils import escape as _xml_escape


BR = "<br/>"


# Inline markdown link: ``[text](url)``. Captures the link text + the
# href separately so each can be XML-escaped before re-interpolation.
# Non-greedy on text + href so adjacent links don't collapse into one.
_MARKDOWN_LINK = re.compile(r"\[([^\]]+?)\]\(([^)]+?)\)")


def body(text: str) -> str:
    """Plain body text — XML-escaped, no styling."""
    return _xml_escape(text)


def inline(
    text: str,
    *,
    font_size: str | None = None,
    color: str | None = None,
) -> str:
    """Styled inline run. ``font_size`` like ``"24px"``; ``color`` like ``"#2E5090"``."""
    attrs: list[str] = []
    if font_size:
        attrs.append(f'font-size="{font_size}"')
    if color:
        attrs.append(f'color="{color}"')
    attr_str = (" " + " ".join(attrs)) if attrs else ""
    return f"<inline{attr_str}>{_xml_escape(text)}</inline>"


def heading(text: str, color: str | None = None) -> str:
    """Top-level heading (32px)."""
    return inline(text, font_size="32px", color=color)


def subheading(text: str, color: str | None = None) -> str:
    """Section subheading (20px)."""
    return inline(text, font_size="20px", color=color)


def bullets(items: Iterable[str]) -> str:
    """Bulleted list at indent level 0.

    Each item is processed through :func:`markdown`, so inline
    ``[text](url)`` links render as clickable anchors and lone
    ``\\n`` becomes ``<br/>`` (intra-bullet soft break). v8.5.4
    closes the footgun where bullet items sourced from L2 YAML
    descriptions (markdown-shaped by SPEC convention) leaked
    literal ``[...](...)`` markup into the rendered text box.
    Plain-text bullets behave identically to before — ``markdown()``
    is a strict superset of the old ``_xml_escape`` path.
    """
    lis = "".join(
        f'<li class="ql-indent-0">{markdown(item)}</li>' for item in items
    )
    return f"<ul>{lis}</ul>"


def bullets_raw(items: Iterable[str]) -> str:
    """Bulleted list whose items are pre-composed XML (so inline styling works inside bullets)."""
    lis = "".join(f'<li class="ql-indent-0">{item}</li>' for item in items)
    return f"<ul>{lis}</ul>"


def link(text: str, href: str) -> str:
    """Hyperlink opening in the same tab."""
    return f'<a href="{_xml_escape(href)}" target="_self">{_xml_escape(text)}</a>'


def markdown(text: str) -> str:
    """Multi-paragraph prose with inline markdown links.

    Transforms (in order):

    1. ``[text](url)`` markdown links → ``<a href="url" target="_self">text</a>``
       QuickSight clickable links. Both ``text`` and ``url`` are XML-escaped.
    2. The remaining non-link spans get XML-escaped.
    3. ``\\n\\n`` (one or more blank lines between paragraphs) → ``<br/><br/>``
    4. Lone ``\\n`` (intra-paragraph break) → ``<br/>``

    Use whenever the input is L2-YAML-supplied prose or any string with
    markdown-shaped paragraph breaks. ``body()`` is for plain single-line
    text only — feeding multi-paragraph or link-bearing strings to
    ``body()`` produces unrendered ``\\n`` and literal ``[text](url)`` in
    QuickSight (the v8.4.0 footgun this helper closes).
    """
    parts: list[str] = []
    cursor = 0
    for match in _MARKDOWN_LINK.finditer(text):
        # Plain prose between the previous match and this link
        before = text[cursor:match.start()]
        parts.append(_escape_with_breaks(before))
        # The link itself — link() XML-escapes both text and href
        parts.append(link(match.group(1), match.group(2)))
        cursor = match.end()
    parts.append(_escape_with_breaks(text[cursor:]))
    return "".join(parts)


def _escape_with_breaks(text: str) -> str:
    """XML-escape ``text`` and convert paragraph + line breaks.

    Paragraph break (``\\n\\n+``) becomes ``<br/><br/>`` so QuickSight
    renders the visible vertical gap between paragraphs that authors
    expect from markdown. A lone ``\\n`` becomes a single ``<br/>`` so
    intra-paragraph wrapping survives.

    Order matters: collapse paragraph breaks BEFORE single ``\\n`` so
    ``\\n\\n\\n`` becomes ``<br/><br/>`` (one paragraph break), not
    ``<br/><br/><br/>`` (three line breaks).
    """
    escaped = _xml_escape(text)
    # Two-or-more newlines = one paragraph break = two <br/>
    escaped = re.sub(r"\n{2,}", BR + BR, escaped)
    # Remaining single \n = soft break = one <br/>
    escaped = escaped.replace("\n", BR)
    return escaped


def text_box(*parts: str) -> str:
    """Wrap parts in a ``<text-box>`` root. Parts are concatenated verbatim."""
    return f"<text-box>{''.join(parts)}</text-box>"
