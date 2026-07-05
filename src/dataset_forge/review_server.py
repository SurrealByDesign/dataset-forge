"""Local-only review decision server.

This module serves existing inspect sidecars and writes only
review_decisions.json. It is intentionally small, localhost-only, and based on
the Python standard library.
"""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse

from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    ReviewDecision,
    ReviewDecisionSet,
    ReviewDecisionValue,
    load_review_decisions,
    parse_review_decisions,
)

LOCAL_REVIEW_HOST = "127.0.0.1"
DEFAULT_REVIEW_PORT = 8765

INSPECTION_REPORT_FILENAME = "inspection_report.json"
RECOMMENDATION_SUMMARY_FILENAME = "recommendation_summary.json"
REVIEW_DECISIONS_FILENAME = "review_decisions.json"

_REVIEW_RECOMMENDATIONS = {"PRIORITY_REVIEW", "NEEDS_REVIEW"}
_DECISION_VALUES = {value.value for value in ReviewDecisionValue}


class ReviewServerError(ValueError):
    """Raised when a review server workspace or request is invalid."""


@dataclass(frozen=True)
class ReviewWorkspace:
    output_dir: Path
    inspection_report_path: Path
    recommendation_summary_path: Path
    review_decisions_path: Path
    inspection_report: dict[str, Any]
    recommendation_summary: dict[str, Any]
    review_decisions: ReviewDecisionSet


def load_review_workspace(output_dir: Path) -> ReviewWorkspace:
    """Load sidecars required by the local review server."""

    root = output_dir.expanduser().resolve()
    inspection_path = root / INSPECTION_REPORT_FILENAME
    recommendation_path = root / RECOMMENDATION_SUMMARY_FILENAME
    decisions_path = root / REVIEW_DECISIONS_FILENAME

    if not inspection_path.exists():
        raise ReviewServerError(f"Missing required sidecar: {inspection_path}")
    if not recommendation_path.exists():
        raise ReviewServerError(f"Missing required sidecar: {recommendation_path}")

    inspection_report = _load_json_object(inspection_path, "inspection report")
    recommendation_summary = _load_json_object(
        recommendation_path,
        "recommendation summary",
    )
    decisions = (
        load_review_decisions(decisions_path)
        if decisions_path.exists()
        else ReviewDecisionSet(schema=REVIEW_DECISIONS_SCHEMA, decisions=())
    )

    return ReviewWorkspace(
        output_dir=root,
        inspection_report_path=inspection_path,
        recommendation_summary_path=recommendation_path,
        review_decisions_path=decisions_path,
        inspection_report=inspection_report,
        recommendation_summary=recommendation_summary,
        review_decisions=decisions,
    )


def build_review_data(output_dir: Path) -> dict[str, Any]:
    """Build deterministic review data from existing sidecars."""

    workspace = load_review_workspace(output_dir)
    return _review_data_from_workspace(workspace)


def update_review_decision(output_dir: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and persist one review decision update."""

    workspace = load_review_workspace(output_dir)
    decision = _decision_from_payload(payload)
    existing = list(workspace.review_decisions.decisions)
    next_decisions = [
        item for item in existing
        if _decision_scope(item) != _decision_scope(decision)
    ]
    next_decisions.append(decision)
    normalized = parse_review_decisions({
        "schema": REVIEW_DECISIONS_SCHEMA,
        "decisions": [item.to_dict() for item in next_decisions],
    })
    atomic_write_json(workspace.review_decisions_path, normalized.to_dict())
    return _review_data_from_workspace(load_review_workspace(output_dir))


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write JSON using a temporary file and os.replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def create_review_server(
    output_dir: Path,
    *,
    host: str = LOCAL_REVIEW_HOST,
    port: int = DEFAULT_REVIEW_PORT,
) -> ThreadingHTTPServer:
    """Create a local-only HTTP server for review decisions."""

    if host != LOCAL_REVIEW_HOST:
        raise ReviewServerError("review server must bind only to 127.0.0.1")
    load_review_workspace(output_dir)
    root = output_dir.expanduser().resolve()

    class Handler(_ReviewRequestHandler):
        review_output_dir = root

    return ThreadingHTTPServer((host, port), Handler)


def serve_review_server(
    output_dir: Path,
    *,
    port: int = DEFAULT_REVIEW_PORT,
) -> None:
    """Serve the review UI until interrupted."""

    server = create_review_server(output_dir, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


class _ReviewRequestHandler(BaseHTTPRequestHandler):
    review_output_dir: Path

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(_review_html())
            return
        if parsed.path == "/api/review-data":
            self._send_json(build_review_data(self.review_output_dir))
            return
        if parsed.path == "/image":
            self._send_image(parsed.query)
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/decision":
            self.send_error(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ReviewServerError("decision payload must be an object")
            data = update_review_decision(self.review_output_dir, payload)
        except (json.JSONDecodeError, ReviewServerError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json(data)

    def _send_json(self, payload: Mapping[str, Any], *, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_image(self, query: str) -> None:
        params = parse_qs(query)
        raw_path = params.get("path", [""])[0]
        image_path = Path(unquote(raw_path)).expanduser().resolve()
        allowed = {
            Path(row["image_path"]).expanduser().resolve()
            for row in build_review_data(self.review_output_dir)["rows"]
        }
        if image_path not in allowed or not image_path.exists():
            self.send_error(404, "image not found")
            return
        content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        data = image_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _review_data_from_workspace(workspace: ReviewWorkspace) -> dict[str, Any]:
    rows = _review_rows(workspace)
    summary = workspace.recommendation_summary.get("summary", {})
    return {
        "schema": "dataset-forge/local-review-data/v1",
        "review_decisions_schema": REVIEW_DECISIONS_SCHEMA,
        "dataset_path": str(workspace.inspection_report.get("dataset_path", "")),
        "summary": {
            "priority_review_count": int(summary.get("priority_review_count", 0)),
            "needs_review_count": int(summary.get("needs_review_count", 0)),
            "review_row_count": len(rows),
            "already_reviewed_count": sum(1 for row in rows if row["current_decision"]),
            "pending_review_count": sum(1 for row in rows if not row["current_decision"]),
        },
        "decision_values": sorted(_DECISION_VALUES),
        "rows": rows,
    }


def _review_rows(workspace: ReviewWorkspace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in workspace.recommendation_summary.get("recommendations", []):
        if item.get("recommendation") not in _REVIEW_RECOMMENDATIONS:
            continue
        image_path = str(item.get("image_path", ""))
        for ref in item.get("finding_refs", []):
            category = str(ref.get("category", ""))
            analyzer = str(ref.get("analyzer", ""))
            scope = (image_path, category, analyzer)
            if not image_path or scope in seen:
                continue
            seen.add(scope)
            decision = workspace.review_decisions.decision_for(
                image_path,
                category,
                analyzer,
            )
            rows.append({
                "id": _row_id(image_path, category, analyzer),
                "image_path": image_path,
                "thumbnail_url": f"/image?path={quote(image_path)}",
                "filename": Path(image_path).name or image_path,
                "recommendation": str(item.get("display_label", "")),
                "primary_reason": str(item.get("primary_reason", "")),
                "category": category,
                "analyzer": analyzer,
                "severity": str(ref.get("severity", "")),
                "current_decision": decision.decision if decision else None,
                "notes": decision.notes if decision else "",
            })
    return sorted(rows, key=lambda row: (row["recommendation"], row["filename"], row["category"], row["analyzer"]))


def _decision_from_payload(payload: Mapping[str, Any]) -> ReviewDecision:
    decision = payload.get("decision")
    if decision not in _DECISION_VALUES:
        raise ReviewServerError(f"invalid review decision: {decision!r}")
    image_path = _required_str(payload, "image_path")
    category = _optional_str(payload, "category")
    analyzer = _optional_str(payload, "analyzer")
    recommendation = _optional_str(payload, "recommendation")
    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        raise ReviewServerError("notes must be a string")
    return ReviewDecision(
        image_path=image_path.replace("\\", "/"),
        category=category,
        analyzer=analyzer,
        recommendation=recommendation,
        decision=str(decision),
        notes=notes,
    )


def _decision_scope(decision: ReviewDecision) -> tuple[str, str | None, str | None]:
    return (decision.image_path, decision.category, decision.analyzer)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewServerError(f"Invalid {label} JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ReviewServerError(f"{label} must be a JSON object: {path}")
    return data


def _required_str(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ReviewServerError(f"{field} must be a non-empty string")
    return value


def _optional_str(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ReviewServerError(f"{field} must be a non-empty string when provided")
    return value


def _row_id(image_path: str, category: str, analyzer: str) -> str:
    return sha256(f"{image_path}\0{category}\0{analyzer}".encode("utf-8")).hexdigest()[:16]


def _review_html() -> str:
    buttons = "\n".join(
        f'<button type="button" data-decision="{value}">{value.replace("_", " ").title()}</button>'
        for value in sorted(_DECISION_VALUES)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dataset Forge Review Decisions</title>
<style>
body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #1f2933; background: #f7f8fb; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 28px 18px 48px; }}
.note, .card {{ background: #fff; border: 1px solid #d9dee7; padding: 14px; }}
.counts {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }}
.count {{ background: #fff; border: 1px solid #d9dee7; padding: 10px 14px; min-width: 150px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; }}
.card {{ display: grid; grid-template-columns: 120px 1fr; gap: 12px; }}
img {{ width: 120px; height: 120px; object-fit: contain; background: #eef2f6; border: 1px solid #d9dee7; }}
h1, h2, h3, p {{ margin-top: 0; }}
p {{ color: #5b6472; }}
button {{ margin: 3px 3px 3px 0; padding: 6px 8px; border: 1px solid #9aa8b8; background: #fff; cursor: pointer; }}
button.selected {{ background: #28536b; border-color: #28536b; color: #fff; }}
textarea {{ width: 100%; min-height: 54px; box-sizing: border-box; }}
.status {{ font-weight: bold; color: #28536b; }}
</style>
</head>
<body>
<main>
<h1>Dataset Forge Review Decisions</h1>
<section class="note">
<p>This local review surface writes only <code>review_decisions.json</code>.</p>
<p>Recommendations are advisory. Source images and inspection sidecars are not modified.</p>
</section>
<section class="counts" id="counts"></section>
<section>
<h2>Priority Review</h2>
<div class="cards" id="priority"></div>
</section>
<section>
<h2>Needs Review</h2>
<div class="cards" id="needs"></div>
</section>
</main>
<template id="decision-buttons">{buttons}</template>
<script>
async function loadData() {{
  const response = await fetch('/api/review-data');
  if (!response.ok) throw new Error('Could not load review data');
  return await response.json();
}}
function countBox(label, value) {{
  return `<div class="count"><strong>${{value}}</strong><br>${{label}}</div>`;
}}
function escapeText(value) {{
  return String(value || '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function renderRow(row) {{
  const card = document.createElement('article');
  card.className = 'card';
  card.innerHTML = `
    <img src="${{escapeText(row.thumbnail_url)}}" alt="${{escapeText(row.filename)}}">
    <div>
      <h3>${{escapeText(row.filename)}}</h3>
      <p><strong>Recommendation:</strong> ${{escapeText(row.recommendation)}}</p>
      <p><strong>Primary reason:</strong> ${{escapeText(row.primary_reason)}}</p>
      <p><strong>Category:</strong> ${{escapeText(row.category)}}</p>
      <p><strong>Analyzer:</strong> ${{escapeText(row.analyzer)}}</p>
      <p><strong>Severity:</strong> ${{escapeText(row.severity)}}</p>
      <p>Current decision: <span class="status">${{escapeText(row.current_decision || 'Pending Review')}}</span></p>
      <div class="buttons">${{document.getElementById('decision-buttons').innerHTML}}</div>
      <label>Notes<br><textarea>${{escapeText(row.notes)}}</textarea></label>
    </div>`;
  card.querySelectorAll('button').forEach(button => {{
    if (button.dataset.decision === row.current_decision) button.classList.add('selected');
    button.addEventListener('click', async () => {{
      const payload = {{
        image_path: row.image_path,
        category: row.category,
        analyzer: row.analyzer,
        recommendation: row.recommendation,
        decision: button.dataset.decision,
        notes: card.querySelector('textarea').value
      }};
      const response = await fetch('/api/decision', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload)
      }});
      if (!response.ok) {{
        const error = await response.json();
        alert(error.error || 'Could not save decision');
        return;
      }}
      await render();
    }});
  }});
  return card;
}}
async function render() {{
  const data = await loadData();
  document.getElementById('counts').innerHTML =
    countBox('Priority Review', data.summary.priority_review_count) +
    countBox('Needs Review', data.summary.needs_review_count) +
    countBox('Already Reviewed', data.summary.already_reviewed_count) +
    countBox('Pending Review', data.summary.pending_review_count);
  const priority = document.getElementById('priority');
  const needs = document.getElementById('needs');
  priority.innerHTML = '';
  needs.innerHTML = '';
  data.rows.forEach(row => {{
    if (row.recommendation === 'Priority Review') priority.appendChild(renderRow(row));
    if (row.recommendation === 'Needs Review') needs.appendChild(renderRow(row));
  }});
  if (!priority.childElementCount) priority.innerHTML = '<p>No images in this group.</p>';
  if (!needs.childElementCount) needs.innerHTML = '<p>No images in this group.</p>';
}}
render().catch(error => document.body.insertAdjacentHTML('beforeend', `<pre>${{escapeText(error.message)}}</pre>`));
</script>
</body>
</html>
"""


__all__ = [
    "DEFAULT_REVIEW_PORT",
    "LOCAL_REVIEW_HOST",
    "ReviewServerError",
    "atomic_write_json",
    "build_review_data",
    "create_review_server",
    "load_review_workspace",
    "serve_review_server",
    "update_review_decision",
]
