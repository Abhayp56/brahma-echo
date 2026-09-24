"""
Micro-UI App Renderer Module for Brahma-Echo
===========================================
Parses Ada-SI manifest UI templates ('calendar', 'list', 'table', 'custom')
and renders responsive HTML/CSS/JS micro-app widgets for PyQt desktop view and web UI.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("BrahmaEcho.UIMicroAppRenderer")


class UIMicroAppRenderer:
    """
    Renders micro-app widgets for forged Ada-SI tools.
    """

    @staticmethod
    def render_widget_html(manifest: Dict[str, Any], tool_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate standalone HTML/JS widget code from Ada-SI manifest.
        """
        ui = manifest.get("ui") or {}
        template = ui.get("template", "list")
        tool_name = manifest.get("name", manifest.get("tool_name", "Skill Widget"))
        description = manifest.get("description", "")

        records = (tool_data or {}).get("records", [])

        # Common Glassmorphism CSS styling matching Brahma-Echo aesthetics
        css_styles = """
        <style>
            :root {
                --bg: #0d0f14;
                --panel: #141721;
                --primary: #ffb300;
                --text: #f4f6f8;
                --muted: #8e949d;
                --border: rgba(255, 179, 0, 0.2);
            }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 16px;
            }
            .widget-card {
                background: linear-gradient(135deg, rgba(20, 23, 33, 0.9), rgba(10, 12, 18, 0.95));
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 18px;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
                backdrop-filter: blur(8px);
            }
            .widget-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                border-bottom: 1px solid var(--border);
                padding-bottom: 10px;
                margin-bottom: 14px;
            }
            .widget-title {
                font-size: 1.1rem;
                font-weight: 700;
                color: var(--primary);
            }
            .widget-desc {
                font-size: 0.85rem;
                color: var(--muted);
                margin-bottom: 12px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }
            th, td {
                padding: 8px 12px;
                text-align: left;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            th {
                color: var(--primary);
                font-weight: 600;
            }
            .list-item {
                display: flex;
                justify-content: space-between;
                padding: 10px;
                background: rgba(255, 255, 255, 0.03);
                border-radius: 6px;
                margin-bottom: 6px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            .badge {
                background: rgba(255, 179, 0, 0.15);
                color: var(--primary);
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.75rem;
            }
        </style>
        """

        # Build template-specific HTML content
        body_content = ""

        if template == "table":
            if records and isinstance(records, list) and len(records) > 0 and isinstance(records[0], dict):
                headers = list(records[0].keys())
                header_html = "".join(f"<th>{h.capitalize()}</th>" for h in headers)
                rows_html = ""
                for r in records:
                    row_cells = "".join(f"<td>{r.get(h, '')}</td>" for h in headers)
                    rows_html += f"<tr>{row_cells}</tr>"
                body_content = f"<table><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>"
            else:
                body_content = "<div class='widget-desc'>No table data available yet.</div>"

        elif template in ("list", "calendar"):
            if records and isinstance(records, list):
                items_html = ""
                for r in records:
                    if isinstance(r, dict):
                        title = r.get("title") or r.get("name") or str(r)
                        detail = r.get("status") or r.get("date") or r.get("value") or ""
                        items_html += f"<div class='list-item'><span>{title}</span><span class='badge'>{detail}</span></div>"
                    else:
                        items_html += f"<div class='list-item'><span>{r}</span></div>"
                body_content = f"<div>{items_html}</div>"
            else:
                body_content = "<div class='widget-desc'>No items found.</div>"

        else: # custom layout
            custom_html = ui.get("custom_html", "")
            if custom_html:
                body_content = custom_html
            else:
                body_content = f"<pre style='color:var(--text);'>{json.dumps(tool_data or {}, indent=2)}</pre>"

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{tool_name}</title>
    {css_styles}
</head>
<body>
    <div class="widget-card">
        <div class="widget-header">
            <span class="widget-title">⚡ {tool_name}</span>
            <span class="badge">Ada-SI Skill</span>
        </div>
        <div class="widget-desc">{description}</div>
        {body_content}
    </div>
</body>
</html>
"""
        return html_doc


renderer = UIMicroAppRenderer()
