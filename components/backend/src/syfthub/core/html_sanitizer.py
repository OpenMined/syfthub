"""HTML sanitization utilities for preventing XSS attacks.

This module provides functions to sanitize HTML output from markdown conversion
to prevent stored XSS vulnerabilities. It uses the bleach library to allow only
safe HTML tags and attributes.
"""

from __future__ import annotations

import bleach  # type: ignore[import-untyped]

# Allowed HTML tags for markdown README content
# These tags are safe and commonly produced by markdown conversion
ALLOWED_TAGS: frozenset[str] = frozenset(
    [
        # Headings
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        # Structural
        "p",
        "div",
        "span",
        "br",
        "hr",
        # Lists
        "ul",
        "ol",
        "li",
        # Text formatting
        "strong",
        "em",
        "b",
        "i",
        "u",
        "s",
        "del",
        "ins",
        "mark",
        "sub",
        "sup",
        "small",
        # Code (for syntax highlighting)
        "pre",
        "code",
        # Links (href validated separately)
        "a",
        # Tables
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "colgroup",
        "col",
        # Blockquotes
        "blockquote",
        # Definition lists
        "dl",
        "dt",
        "dd",
        # Abbreviations
        "abbr",
        # Keyboard/sample
        "kbd",
        "samp",
        "var",
        # Details/summary (collapsible sections)
        "details",
        "summary",
    ]
)

# Allowed attributes per tag
# Global attributes like 'class' and 'id' are allowed for styling/navigation
# Link 'href' is validated to prevent javascript: URLs
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "*": ["class", "id"],  # Global attributes for all tags
    "a": ["href", "title", "rel", "target"],
    "abbr": ["title"],
    "th": ["scope", "colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
    "col": ["span"],
    "colgroup": ["span"],
    "code": ["class"],  # For syntax highlighting (e.g., language-python)
    "pre": ["class"],  # For code block styling
}

# Protocols allowed in href attributes
# Only allow http, https, mailto, and fragment links
ALLOWED_PROTOCOLS: frozenset[str] = frozenset(
    [
        "http",
        "https",
        "mailto",
        "ftp",
    ]
)


def sanitize_readme_html(html: str) -> str:
    """Sanitize HTML output from markdown conversion to prevent XSS.

    This function removes potentially dangerous HTML elements and attributes
    while preserving safe formatting tags commonly used in README content.

    Args:
        html: Raw HTML string from markdown conversion

    Returns:
        Sanitized HTML string safe for rendering in templates

    Example:
        >>> raw_html = '<script>alert("xss")</script><p>Safe content</p>'
        >>> sanitize_readme_html(raw_html)
        '&lt;script&gt;alert("xss")&lt;/script&gt;<p>Safe content</p>'
    """
    if not html:
        return ""

    # bleach.clean returns str, cast to satisfy type checker
    result: str = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=False,  # Don't strip disallowed tags, escape them instead
    )
    return result
