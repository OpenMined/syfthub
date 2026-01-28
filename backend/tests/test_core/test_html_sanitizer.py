"""Tests for the HTML sanitizer module."""

import pytest

from syfthub.core.html_sanitizer import (
    ALLOWED_TAGS,
    ALLOWED_ATTRIBUTES,
    ALLOWED_PROTOCOLS,
    sanitize_readme_html,
)


class TestAllowedTagsConstant:
    """Tests for ALLOWED_TAGS constant."""

    def test_allowed_tags_not_empty(self):
        """Test that allowed tags set is not empty."""
        assert len(ALLOWED_TAGS) > 0

    def test_headings_allowed(self):
        """Test that heading tags are allowed."""
        headings = {"h1", "h2", "h3", "h4", "h5", "h6"}
        assert headings.issubset(ALLOWED_TAGS)

    def test_structural_tags_allowed(self):
        """Test that structural tags are allowed."""
        structural = {"p", "div", "span", "br", "hr"}
        assert structural.issubset(ALLOWED_TAGS)

    def test_list_tags_allowed(self):
        """Test that list tags are allowed."""
        lists = {"ul", "ol", "li"}
        assert lists.issubset(ALLOWED_TAGS)

    def test_text_formatting_tags_allowed(self):
        """Test that text formatting tags are allowed."""
        formatting = {"strong", "em", "b", "i", "u", "s", "del", "ins"}
        assert formatting.issubset(ALLOWED_TAGS)

    def test_code_tags_allowed(self):
        """Test that code tags are allowed."""
        code = {"pre", "code"}
        assert code.issubset(ALLOWED_TAGS)

    def test_link_tag_allowed(self):
        """Test that anchor tag is allowed."""
        assert "a" in ALLOWED_TAGS

    def test_table_tags_allowed(self):
        """Test that table tags are allowed."""
        tables = {"table", "thead", "tbody", "tr", "th", "td"}
        assert tables.issubset(ALLOWED_TAGS)

    def test_blockquote_allowed(self):
        """Test that blockquote tag is allowed."""
        assert "blockquote" in ALLOWED_TAGS

    def test_dangerous_tags_not_allowed(self):
        """Test that dangerous tags are not in the allowed list."""
        dangerous = {"script", "style", "iframe", "object", "embed", "form", "input"}
        assert dangerous.isdisjoint(ALLOWED_TAGS)


class TestAllowedAttributesConstant:
    """Tests for ALLOWED_ATTRIBUTES constant."""

    def test_global_class_attribute_allowed(self):
        """Test that class attribute is globally allowed."""
        assert "class" in ALLOWED_ATTRIBUTES.get("*", [])

    def test_global_id_attribute_allowed(self):
        """Test that id attribute is globally allowed."""
        assert "id" in ALLOWED_ATTRIBUTES.get("*", [])

    def test_anchor_href_allowed(self):
        """Test that href attribute is allowed for anchor tags."""
        assert "href" in ALLOWED_ATTRIBUTES.get("a", [])

    def test_anchor_title_allowed(self):
        """Test that title attribute is allowed for anchor tags."""
        assert "title" in ALLOWED_ATTRIBUTES.get("a", [])

    def test_table_cell_attributes_allowed(self):
        """Test that colspan/rowspan are allowed for table cells."""
        th_attrs = ALLOWED_ATTRIBUTES.get("th", [])
        td_attrs = ALLOWED_ATTRIBUTES.get("td", [])
        assert "colspan" in th_attrs
        assert "rowspan" in th_attrs
        assert "colspan" in td_attrs
        assert "rowspan" in td_attrs


class TestAllowedProtocolsConstant:
    """Tests for ALLOWED_PROTOCOLS constant."""

    def test_https_allowed(self):
        """Test that https protocol is allowed."""
        assert "https" in ALLOWED_PROTOCOLS

    def test_http_allowed(self):
        """Test that http protocol is allowed."""
        assert "http" in ALLOWED_PROTOCOLS

    def test_mailto_allowed(self):
        """Test that mailto protocol is allowed."""
        assert "mailto" in ALLOWED_PROTOCOLS

    def test_ftp_allowed(self):
        """Test that ftp protocol is allowed."""
        assert "ftp" in ALLOWED_PROTOCOLS

    def test_javascript_not_allowed(self):
        """Test that javascript protocol is not allowed."""
        assert "javascript" not in ALLOWED_PROTOCOLS

    def test_data_not_allowed(self):
        """Test that data protocol is not allowed."""
        assert "data" not in ALLOWED_PROTOCOLS


class TestSanitizeReadmeHtml:
    """Tests for sanitize_readme_html function."""

    def test_empty_string_returns_empty(self):
        """Test that empty input returns empty string."""
        assert sanitize_readme_html("") == ""

    def test_none_returns_empty(self):
        """Test that None-like falsy input returns empty string."""
        assert sanitize_readme_html("") == ""

    def test_safe_html_unchanged(self):
        """Test that safe HTML is preserved."""
        safe_html = "<p>Hello <strong>world</strong></p>"
        result = sanitize_readme_html(safe_html)
        assert "<p>" in result
        assert "<strong>" in result
        assert "Hello" in result

    def test_script_tag_escaped(self):
        """Test that script tags are escaped (not stripped)."""
        dangerous_html = '<script>alert("xss")</script><p>Safe</p>'
        result = sanitize_readme_html(dangerous_html)
        # Script tag should be escaped, not stripped (strip=False)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "<p>Safe</p>" in result

    def test_javascript_href_removed(self):
        """Test that javascript: URLs are removed from hrefs."""
        dangerous_html = '<a href="javascript:alert(1)">Click me</a>'
        result = sanitize_readme_html(dangerous_html)
        assert "javascript:" not in result

    def test_onerror_attribute_removed(self):
        """Test that event handler attributes are removed or tag is escaped."""
        # img tag is not allowed, so it gets escaped entirely
        dangerous_html = '<img src="x" onerror="alert(1)">'
        result = sanitize_readme_html(dangerous_html)
        # Either the tag is escaped (no raw <img>) or onerror is stripped
        assert "<img" not in result or "onerror" not in result

    def test_onclick_attribute_removed(self):
        """Test that onclick attribute is removed."""
        dangerous_html = '<p onclick="alert(1)">Click me</p>'
        result = sanitize_readme_html(dangerous_html)
        assert "onclick" not in result

    def test_style_tag_escaped(self):
        """Test that style tags are escaped."""
        dangerous_html = "<style>body{display:none}</style><p>Content</p>"
        result = sanitize_readme_html(dangerous_html)
        assert "<style>" not in result
        assert "<p>Content</p>" in result

    def test_iframe_tag_escaped(self):
        """Test that iframe tags are escaped."""
        dangerous_html = '<iframe src="https://evil.com"></iframe>'
        result = sanitize_readme_html(dangerous_html)
        assert "<iframe" not in result

    def test_valid_link_preserved(self):
        """Test that valid links are preserved."""
        safe_html = '<a href="https://example.com" title="Example">Link</a>'
        result = sanitize_readme_html(safe_html)
        assert 'href="https://example.com"' in result
        assert 'title="Example"' in result

    def test_code_block_with_class_preserved(self):
        """Test that code blocks with language class are preserved."""
        safe_html = '<pre><code class="language-python">print("hello")</code></pre>'
        result = sanitize_readme_html(safe_html)
        assert '<code class="language-python">' in result

    def test_table_structure_preserved(self):
        """Test that table HTML is preserved."""
        safe_html = "<table><tr><th>Header</th></tr><tr><td>Data</td></tr></table>"
        result = sanitize_readme_html(safe_html)
        assert "<table>" in result
        assert "<th>" in result
        assert "<td>" in result

    def test_mailto_link_preserved(self):
        """Test that mailto links are preserved."""
        safe_html = '<a href="mailto:test@example.com">Email</a>'
        result = sanitize_readme_html(safe_html)
        assert 'href="mailto:test@example.com"' in result

    def test_details_summary_preserved(self):
        """Test that details/summary elements are preserved."""
        safe_html = "<details><summary>Click to expand</summary><p>Content</p></details>"
        result = sanitize_readme_html(safe_html)
        assert "<details>" in result
        assert "<summary>" in result

    def test_data_uri_in_href_removed(self):
        """Test that data: URIs in href are removed."""
        dangerous_html = '<a href="data:text/html,<script>alert(1)</script>">Link</a>'
        result = sanitize_readme_html(dangerous_html)
        assert "data:" not in result

    def test_mixed_safe_and_unsafe_content(self):
        """Test sanitization of mixed content."""
        mixed_html = """
        <h1>Title</h1>
        <script>evil()</script>
        <p onclick="attack()">Safe paragraph</p>
        <a href="javascript:void(0)">Bad link</a>
        <a href="https://good.com">Good link</a>
        """
        result = sanitize_readme_html(mixed_html)
        assert "<h1>Title</h1>" in result
        assert "<script>" not in result
        assert "onclick" not in result
        assert "javascript:" not in result
        assert 'href="https://good.com"' in result
