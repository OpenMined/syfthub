"""HTML template for rendering query results as static pages."""

import html
import json
from typing import Any


def render_query_result_html(result: dict[str, Any]) -> str:
    """Render a query result dict as a self-contained HTML page.

    The result dict should have keys: query, model, data_sources, answer, sources, error.

    The JSON is embedded in two forms:
    - A <pre> tag with HTML-escaped content for human viewing
    - A <script type="application/json"> block for programmatic extraction
    """
    json_formatted = json.dumps(result, indent=2, ensure_ascii=False)

    # HTML-escape for safe embedding in <pre>
    json_for_pre = html.escape(json_formatted)

    # Escape </ sequences for safe embedding in <script> block
    json_for_script = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SyftHub Query Result</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #09090b; color: #fafafa; font-family: ui-monospace, monospace; padding: 1rem; }}
    pre {{ white-space: pre-wrap; word-break: break-word; font-size: 0.875rem; line-height: 1.5; }}
  </style>
</head>
<body>
  <script id="query-result" type="application/json">{json_for_script}</script>
  <pre>{json_for_pre}</pre>
</body>
</html>"""
