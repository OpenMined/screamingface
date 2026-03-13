"""HTML preview renderer for browser requests."""

from __future__ import annotations

import html
from typing import Any


def render_preview_html(backend: str, action: str, params: dict[str, Any]) -> str:
    """Render an HTML confirmation page with decoded params and an Execute button."""
    safe_backend = html.escape(backend)
    safe_action = html.escape(action)

    rows = ""
    for key, value in sorted(params.items()):
        safe_key = html.escape(str(key))
        safe_value = html.escape(str(value))
        rows += f"<tr><td><code>{safe_key}</code></td><td><pre>{safe_value}</pre></td></tr>\n"

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Execute: /x/{safe_backend}/{safe_action}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px;
         margin: 2rem auto; padding: 0 1rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  td, th {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
  pre {{ margin: 0; white-space: pre-wrap; word-break: break-all; }}
  .btn {{ background: #2563eb; color: white; border: none; padding: 0.75rem 2rem;
          font-size: 1rem; border-radius: 0.375rem; cursor: pointer; }}
  .btn:hover {{ background: #1d4ed8; }}
  #result {{ margin-top: 1rem; padding: 1rem; background: #f3f4f6; border-radius: 0.375rem;
             display: none; white-space: pre-wrap; font-family: monospace; font-size: 0.875rem; }}
</style>
</head>
<body>
<h1>URL Executor</h1>
<p>Backend: <strong>{safe_backend}</strong> &mdash; Action: <strong>{safe_action}</strong></p>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
{rows}</table>
<button class="btn" id="executeBtn">Execute</button>
<div id="result"></div>
<script>
document.getElementById('executeBtn').addEventListener('click', async () => {{
  const btn = document.getElementById('executeBtn');
  const result = document.getElementById('result');
  btn.disabled = true;
  btn.textContent = 'Executing...';
  result.style.display = 'block';
  result.textContent = 'Running...';
  try {{
    const resp = await fetch(window.location.href, {{
      headers: {{ 'Accept': 'application/json', 'X-SF-Execute': 'true' }}
    }});
    const data = await resp.json();
    result.textContent = JSON.stringify(data, null, 2);
  }} catch (err) {{
    result.textContent = 'Error: ' + err.message;
  }} finally {{
    btn.disabled = false;
    btn.textContent = 'Execute';
  }}
}});
</script>
</body>
</html>"""
