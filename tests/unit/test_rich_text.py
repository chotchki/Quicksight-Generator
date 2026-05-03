"""Unit tests for ``common/rich_text.py`` — XML composition helpers
for QuickSight ``SheetTextBox.Content``.

Pre-v8.4.0 the only break primitive was ``BR`` and the only authoring
helper was ``body()`` — multi-paragraph prose was a footgun (``\\n\\n``
in the input string survived as literal whitespace, since QS only
honors ``<br/>`` for breaks). v8.4.0 added ``markdown()`` which
handles paragraph + line breaks AND inline ``[text](url)`` links.
"""

from __future__ import annotations

from quicksight_gen.common import rich_text as rt


class TestBody:
    def test_xml_escapes(self) -> None:
        assert rt.body("a < b & c") == "a &lt; b &amp; c"

    def test_passthrough_for_safe_text(self) -> None:
        assert rt.body("hello world") == "hello world"


class TestInline:
    def test_no_attrs(self) -> None:
        assert rt.inline("hi") == "<inline>hi</inline>"

    def test_font_size(self) -> None:
        assert rt.inline("hi", font_size="24px") == '<inline font-size="24px">hi</inline>'

    def test_color(self) -> None:
        assert rt.inline("hi", color="#2E5090") == '<inline color="#2E5090">hi</inline>'

    def test_xml_escapes_body(self) -> None:
        assert "&lt;" in rt.inline("a < b")


class TestLink:
    def test_emits_href_and_text(self) -> None:
        assert rt.link("Click", "https://example.com") == (
            '<a href="https://example.com" target="_self">Click</a>'
        )

    def test_xml_escapes_both_text_and_href(self) -> None:
        out = rt.link("Q & A", "https://x.com/?a=1&b=2")
        assert "&amp;" in out
        # href escaping
        assert "?a=1&amp;b=2" in out
        # text escaping
        assert "Q &amp; A" in out


class TestMarkdown:
    """v8.4.0 — class fix for the rt.body() multi-paragraph footgun."""

    def test_single_line_no_breaks(self) -> None:
        assert rt.markdown("just one line") == "just one line"

    def test_paragraph_break_becomes_double_br(self) -> None:
        # Markdown convention: blank line between paragraphs.
        out = rt.markdown("first para\n\nsecond para")
        assert out == "first para<br/><br/>second para"

    def test_three_or_more_newlines_collapse_to_one_paragraph_break(self) -> None:
        # \n\n\n\n is still one paragraph break, not three line breaks.
        out = rt.markdown("a\n\n\n\nb")
        assert out == "a<br/><br/>b"

    def test_single_newline_becomes_one_br(self) -> None:
        # Soft break inside a paragraph.
        out = rt.markdown("line one\nline two")
        assert out == "line one<br/>line two"

    def test_xml_escapes_body_text(self) -> None:
        assert rt.markdown("a < b & c") == "a &lt; b &amp; c"

    def test_inline_link_becomes_anchor(self) -> None:
        out = rt.markdown("see [the docs](https://example.com) for more")
        assert (
            out
            == 'see <a href="https://example.com" target="_self">the docs</a> for more'
        )

    def test_link_with_special_chars_in_url(self) -> None:
        # Query string ampersands in the URL must XML-escape inside the href.
        out = rt.markdown("[search](https://x.com/?a=1&b=2)")
        assert 'href="https://x.com/?a=1&amp;b=2"' in out

    def test_link_text_xml_escapes(self) -> None:
        out = rt.markdown("[Q & A](https://x.com)")
        assert ">Q &amp; A</a>" in out

    def test_multiple_links_in_one_line(self) -> None:
        out = rt.markdown("see [foo](https://foo.com) and [bar](https://bar.com)")
        assert out.count("<a ") == 2
        assert "foo</a>" in out
        assert "bar</a>" in out

    def test_link_inside_paragraph_break(self) -> None:
        out = rt.markdown("intro\n\nclick [here](https://x.com) please")
        assert out == (
            'intro<br/><br/>click <a href="https://x.com" '
            'target="_self">here</a> please'
        )

    def test_no_literal_double_newline_survives(self) -> None:
        # The footgun this helper closes: post-conversion text MUST
        # NOT contain literal ``\n\n`` anywhere.
        out = rt.markdown("a\n\nb\n\nc\n\nd")
        assert "\n\n" not in out

    def test_no_unconverted_markdown_link_survives(self) -> None:
        # Same: post-conversion text MUST NOT contain unconverted
        # markdown link syntax.
        out = rt.markdown("see [docs](https://x.com)")
        assert "[" not in out
        assert "](https" not in out

    def test_brackets_without_link_url_stay_as_text(self) -> None:
        # Plain text using [brackets] without a (url) should survive
        # unchanged (no false-positive conversion).
        out = rt.markdown("see [section 3] of the spec")
        assert "[section 3]" in out

    def test_empty_string(self) -> None:
        assert rt.markdown("") == ""


class TestTextBox:
    def test_wraps_parts_in_root(self) -> None:
        assert rt.text_box("a", "b") == "<text-box>ab</text-box>"

    def test_empty(self) -> None:
        assert rt.text_box() == "<text-box></text-box>"


class TestBullets:
    def test_bullets_emit_ql_indent_class(self) -> None:
        out = rt.bullets(["one", "two"])
        assert out.count('class="ql-indent-0"') == 2

    def test_bullets_xml_escape(self) -> None:
        out = rt.bullets(["a < b"])
        assert "a &lt; b" in out

    def test_bullets_raw_does_not_escape(self) -> None:
        # bullets_raw is for pre-composed XML (e.g. inline-styled
        # bullets) — must NOT escape the items.
        out = rt.bullets_raw(['<inline color="#fff">styled</inline>'])
        assert '<inline color="#fff">styled</inline>' in out
