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
"""

from __future__ import annotations

from typing import Iterable
from xml.sax.saxutils import escape as _xml_escape


BR = "<br/>"


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
    """Bulleted list at indent level 0. Each item is plain text, XML-escaped."""
    lis = "".join(
        f'<li class="ql-indent-0">{_xml_escape(item)}</li>' for item in items
    )
    return f"<ul>{lis}</ul>"


def bullets_raw(items: Iterable[str]) -> str:
    """Bulleted list whose items are pre-composed XML (so inline styling works inside bullets)."""
    lis = "".join(f'<li class="ql-indent-0">{item}</li>' for item in items)
    return f"<ul>{lis}</ul>"


def link(text: str, href: str) -> str:
    """Hyperlink opening in the same tab."""
    return f'<a href="{_xml_escape(href)}" target="_self">{_xml_escape(text)}</a>'


def text_box(*parts: str) -> str:
    """Wrap parts in a ``<text-box>`` root. Parts are concatenated verbatim."""
    return f"<text-box>{''.join(parts)}</text-box>"
