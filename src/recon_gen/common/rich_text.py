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
* ``markdown_inline(text)`` — same XML-escape + ``[text](url)`` link
  handling, but ALL newlines collapse to a single space (no ``<br/>``).
  Use inside contexts where ``<br/>`` is not a valid child — most
  notably ``<li>``: QS's XML parser rejects ``<br/>`` as a child of
  ``<li>`` with ``Element 'li' cannot have 'br' elements as children``.

``bullets()`` is defensive: it routes items through ``markdown()``
then strips any ``<br/>`` from each item with a ``UserWarning``
showing the original input. Authors can choose ``markdown_inline``
explicitly when they need a guaranteed-no-``<br/>`` rendering of a
single string outside a bullet context.
"""

from __future__ import annotations

import re
import warnings
from typing import Iterable
from xml.sax.saxutils import escape as _xml_escape


BR = "<br/>"


# Match every ``<br>``-shape (self-closing, slash-self-closing, with or
# without whitespace inside the tag) so the bullets() defensive strip
# catches them regardless of which authoring path produced them.
_BR_TAG = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)


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

    Each item is processed through :func:`markdown` (so inline
    ``[text](url)`` links render as clickable anchors) and then
    defensively stripped of any ``<br/>`` tags — QS's XML parser
    rejects ``<br/>`` as a child of ``<li>`` with
    ``Element 'li' cannot have 'br' elements as children``. L2 YAML
    ``description: |`` block scalars carry embedded ``\\n`` for
    human-readable wrapping; those would otherwise reflow to
    ``<br/>`` via :func:`markdown` and break ``CreateAnalysis`` (the
    v8.5.4 → v8.5.8 regression on the L1 Drift sheet).

    Any stripped ``<br/>`` raises a ``UserWarning`` showing the
    original item so authors can clean the source string when the
    line break was actually intended (e.g. break the item into two).
    """
    lis_parts: list[str] = []
    for item in items:
        rendered = markdown(item)
        if _BR_TAG.search(rendered):
            stripped = _BR_TAG.sub(" ", rendered)
            warnings.warn(
                f"bullets(): stripped <br/> from list item — QS "
                f"rejects <br/> as a child of <li>. Original item: "
                f"{item!r}. Consider splitting into two bullets or "
                f"removing the embedded line break in the source.",
                UserWarning,
                stacklevel=2,
            )
            rendered = stripped
        lis_parts.append(f'<li class="ql-indent-0">{rendered}</li>')
    return f"<ul>{''.join(lis_parts)}</ul>"


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


def markdown_inline(text: str) -> str:
    """Single-line markdown with link handling but no ``<br/>``.

    Same transformations as :func:`markdown` for inline links and
    XML-escaping, but ANY whitespace run that contains a newline
    collapses to a single space. ``<br/>`` is never emitted. Use
    inside ``<li>`` (the QS XML parser rejects ``<br/>`` as an
    ``<li>`` child) or any other context where line breaks must
    not appear.

    Trailing / leading whitespace is stripped — useful when the
    input came from a YAML ``|`` block scalar (which always ends in
    ``\\n``). Strip happens after link substitution so a link sitting
    at the end of the input stays attached to the next part rather
    than getting whitespace-eaten.
    """
    parts: list[str] = []
    cursor = 0
    for match in _MARKDOWN_LINK.finditer(text):
        before = text[cursor:match.start()]
        parts.append(_escape_collapse_newlines(before))
        parts.append(link(match.group(1), match.group(2)))
        cursor = match.end()
    parts.append(_escape_collapse_newlines(text[cursor:]))
    return "".join(parts).strip()


def _escape_collapse_newlines(text: str) -> str:
    """XML-escape ``text`` and collapse newline-bearing whitespace runs.

    Any whitespace run that contains at least one ``\\n`` collapses
    to a single space — that handles the YAML block-scalar case where
    line wrapping creates ``\\n`` between words AND the case of
    ``\\n\\n`` paragraph breaks (both reflow to a single space here,
    since ``<li>`` doesn't take ``<br/>``). Pure-space runs that
    don't contain a newline are left alone, so authored intra-line
    spacing survives.
    """
    escaped = _xml_escape(text)
    # \s* on either side captures leading/trailing space adjacent to
    # the newline run; the whole match collapses to a single space.
    return re.sub(r"[ \t]*\n+[ \t]*", " ", escaped)


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
    """Wrap parts in a ``<text-box>`` root.

    Auto-pads the interior with leading + trailing ``<br/>`` so the
    rendered text doesn't sit flush against the box's top / bottom
    edges. ``SheetTextBox`` itself has no padding/margin fields in
    the AWS API — interior breathing room only comes via the
    rich-text grammar inside ``Content``. Two ``<br/>`` per side
    matches what hand-authored QS UI text boxes emit when an editor
    hits Enter twice for spacing (a common pattern).

    Pass already-``<br/>``-padded ``parts`` if you want even more
    space; the auto-pad is additive.
    """
    return f"<text-box>{BR}{BR}{''.join(parts)}{BR}{BR}</text-box>"
