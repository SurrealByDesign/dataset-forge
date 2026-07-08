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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from dataset_forge.review_desk import (
    DEFAULT_REVIEW_PORT,
    INSPECTION_REPORT_FILENAME,
    LOCAL_REVIEW_HOST,
    RECOMMENDATION_SUMMARY_FILENAME,
    REVIEW_DECISIONS_FILENAME,
    TRIAGE_DOSSIERS_FILENAME,
    ReviewDeskError,
    ReviewWorkspace,
    build_review_data,
    load_review_workspace,
)
from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    ReviewDecision,
    ReviewDecisionValue,
    ReviewWorkflowState,
    parse_review_decisions,
)

ReviewServerError = ReviewDeskError

_DECISION_VALUES = {value.value for value in ReviewDecisionValue}
_WORKFLOW_STATES = {value.value for value in ReviewWorkflowState}


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


def update_review_decision(output_dir: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and persist one review decision update from the server endpoint."""

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
    return build_review_data(output_dir)


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


def _decision_from_payload(payload: Mapping[str, Any]) -> ReviewDecision:
    decision = payload.get("decision")
    if decision not in _DECISION_VALUES:
        raise ReviewServerError(f"invalid review decision: {decision!r}")
    workflow_state = payload.get("workflow_state", ReviewWorkflowState.IN_DATASET.value)
    if workflow_state not in _WORKFLOW_STATES:
        raise ReviewServerError(f"invalid workflow state: {workflow_state!r}")
    image_path = _required_str(payload, "image_path")
    recommendation = _optional_str(payload, "recommendation")
    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        raise ReviewServerError("notes must be a string")
    return ReviewDecision(
        image_path=image_path.replace("\\", "/"),
        workflow_state=str(workflow_state),
        recommendation=recommendation,
        decision=str(decision),
        notes=notes,
    )


def _decision_scope(decision: ReviewDecision) -> tuple[str, str | None, str | None]:
    return (decision.image_path, None, None)


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

def _review_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dataset Forge Review Desk</title>
<style>
:root { color-scheme: light; --ink: #17202a; --muted: #5d6877; --line: #d9dee7; --paper: #f5f6f8; --panel: #fff; --accent: #28536b; --danger: #8a3342; --warn: #8a611c; --ok: #2f684e; }
* { box-sizing: border-box; }
body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: var(--ink); background: var(--paper); }
button, input, select, textarea { font: inherit; }
button { border: 1px solid #9aa8b8; background: #fff; color: var(--ink); cursor: pointer; }
button:hover, button.selected { border-color: var(--accent); color: var(--accent); }
.app { display: grid; grid-template-columns: 280px minmax(360px, 1fr) 360px; min-height: 100vh; }
aside, main { min-width: 0; }
.left, .right { background: var(--panel); border-color: var(--line); border-style: solid; overflow: auto; max-height: 100vh; }
.left { border-width: 0 1px 0 0; padding: 16px; }
.right { border-width: 0 0 0 1px; padding: 16px; }
.center { padding: 16px; overflow: auto; max-height: 100vh; }
h1 { font-size: 1.35rem; margin: 0 0 12px; }
h2 { font-size: 1rem; margin: 20px 0 10px; }
h3 { font-size: .9rem; margin: 0 0 8px; overflow-wrap: anywhere; }
p { color: var(--muted); line-height: 1.35; margin: 0 0 10px; }
label { display: block; margin: 10px 0 4px; color: var(--muted); font-size: .78rem; font-weight: 700; text-transform: uppercase; }
input, select, textarea { width: 100%; border: 1px solid var(--line); background: #fff; color: var(--ink); padding: 8px; }
textarea { min-height: 90px; resize: vertical; }
.counts { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.count { border: 1px solid var(--line); padding: 8px; background: #fafbfc; }
.count strong { display: block; font-size: 1.15rem; }
.overview { background: var(--panel); border: 1px solid var(--line); padding: 12px; margin-bottom: 14px; }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin: 10px 0; }
.overview-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.overview-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.overview-actions button { padding: 7px 9px; }
.overview details { border-top: 1px solid var(--line); padding-top: 8px; margin-top: 10px; }
.overview summary { cursor: pointer; font-weight: 700; }
.intelligence-table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: .86rem; }
.intelligence-table th, .intelligence-table td { border: 1px solid var(--line); padding: 6px; text-align: left; vertical-align: top; }
.intelligence-table th { background: #eef2f6; color: var(--muted); }
.intelligence-note { border-left: 3px solid var(--accent); padding-left: 8px; margin: 8px 0; }
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.toolbar input { width: 180px; }
.group-title { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--line); padding-bottom: 6px; margin-top: 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--thumb-size, 170px), 1fr)); gap: 10px; }
.card { background: var(--panel); border: 3px solid var(--line); padding: 8px; min-width: 0; }
.card.priority { border-color: var(--danger); }
.card.needs { border-color: var(--warn); }
.card.none { border-color: var(--ok); }
.card.reviewed { box-shadow: inset 0 0 0 2px #4f7f64; }
.card.quarantine { box-shadow: inset 0 0 0 2px #8a611c; }
.card.selected { outline: 3px solid var(--accent); }
.card img { width: 100%; aspect-ratio: 1 / 1; object-fit: contain; background: #eef2f6; border: 1px solid var(--line); display: block; }
.badges { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0; }
.badge { border: 1px solid var(--line); padding: 3px 5px; font-size: .72rem; background: #f8f9fb; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; }
.actions button, .decision-buttons button { padding: 5px 7px; font-size: .78rem; }
.decision-buttons { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.preview { width: 100%; max-height: 360px; object-fit: contain; background: #eef2f6; border: 1px solid var(--line); cursor: zoom-in; }
.finding { border-top: 1px solid var(--line); padding-top: 10px; margin-top: 10px; }
.muted { color: var(--muted); }
.save-status { min-height: 1.2em; }
.shortcut { font-size: .78rem; color: var(--muted); }
.hidden { display: none !important; }
dialog { border: 1px solid var(--line); max-width: 620px; }
.zoom-viewer { position: fixed; inset: 0; z-index: 20; background: rgba(13, 18, 25, .94); color: #fff; display: grid; grid-template-rows: auto 1fr; }
.zoom-viewer[hidden] { display: none; }
.zoom-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px; background: rgba(13, 18, 25, .98); border-bottom: 1px solid #3a4659; }
.zoom-toolbar button { color: #fff; background: #1c2530; border-color: #667386; padding: 7px 9px; }
.zoom-title { flex: 1 1 220px; overflow-wrap: anywhere; color: #dbe4ee; }
.zoom-stage { overflow: hidden; position: relative; cursor: grab; }
.zoom-stage.dragging { cursor: grabbing; }
.zoom-image { position: absolute; left: 50%; top: 50%; transform-origin: center center; max-width: none; max-height: none; user-select: none; -webkit-user-drag: none; }
@media (max-width: 980px) { .app { grid-template-columns: 1fr; } .left, .right, .center { max-height: none; border-width: 0 0 1px; } }
</style>
</head>
<body>
<div class="app">
<aside class="left">
  <h1>Dataset Forge Review Desk</h1>
  <p>This local desk consumes generated sidecars and writes only <code>review_decisions.json</code>. Review Desk does not run analyzers, export datasets, or modify source images.</p>
  <section class="counts" id="counts"></section>
  <label for="search">Search</label>
  <input id="search" type="search" placeholder="filename or evidence">
  <label for="decisionFilter">Decision</label>
  <select id="decisionFilter"><option value="">All decisions</option></select>
  <label for="workflowFilter">Workflow</label>
  <select id="workflowFilter"><option value="">All workflow states</option></select>
  <label for="triageFilter">Triage</label>
  <select id="triageFilter">
    <option value="">All triage groups</option>
    <option value="Priority Review">Priority Review</option>
    <option value="Needs Review">Needs Review</option>
    <option value="No Findings Emitted">No Findings Emitted</option>
  </select>
  <label for="categoryFilter">Finding category</label>
  <select id="categoryFilter"><option value="">All categories</option></select>
  <label for="severityFilter">Severity</label>
  <select id="severityFilter"><option value="">All severities</option></select>
  <label for="confidenceFilter">Confidence</label>
  <select id="confidenceFilter">
    <option value="">All confidence</option>
    <option value="0.75">0.75 and above</option>
    <option value="0.5">0.50 and above</option>
  </select>
  <button id="nextUndecided" type="button" title="Next undecided (N)">Next Undecided <span class="shortcut">N</span></button>
  <button id="clearFilters" type="button" title="Clear all filters">Clear Filters</button>
  <button id="shortcutHelp" type="button" title="Keyboard reference (?)">Shortcuts <span class="shortcut">?</span></button>
</aside>
<main class="center">
  <section id="overview" class="overview"></section>
  <section class="toolbar">
    <label for="thumbSize">Thumbnail size</label>
    <input id="thumbSize" type="range" min="130" max="280" value="170">
    <span id="visibleCount" class="muted"></span>
    <span id="filterSummary" class="muted"></span>
  </section>
  <section id="groups"></section>
</main>
<aside class="right" id="detail">
  <p>Select an image to review its evidence.</p>
</aside>
</div>
<dialog id="shortcuts">
  <h2>Keyboard Shortcuts</h2>
  <p>J / Left: previous image. K / Right: next image. N: next undecided.</p>
  <p>1: Keep. 2: Accepted Style / False Positive. 3: Improvement Candidate. 4: Removal Candidate. U: Undecided.</p>
  <p>Space: larger preview. F: fullscreen preview. Escape: close dialogs.</p>
  <p>In zoom view: mouse wheel zooms, drag pans, + / - zoom, 0 fits, 1 shows actual size.</p>
  <button type="button" onclick="document.getElementById('shortcuts').close()">Close</button>
</dialog>
<section id="zoomViewer" class="zoom-viewer" hidden aria-label="Image zoom viewer">
  <div class="zoom-toolbar">
    <button id="zoomClose" type="button" title="Close zoom (Escape)">Close</button>
    <button id="zoomPrev" type="button" title="Previous image (J / Left)">Previous</button>
    <button id="zoomNext" type="button" title="Next image (K / Right)">Next</button>
    <button id="zoomFit" type="button" title="Fit image to window">Fit</button>
    <button id="zoomActual" type="button" title="Actual size: 100% pixels">100%</button>
    <button id="zoomOut" type="button" title="Zoom out">-</button>
    <button id="zoomIn" type="button" title="Zoom in">+</button>
    <span id="zoomTitle" class="zoom-title"></span>
  </div>
  <div id="zoomStage" class="zoom-stage">
    <img id="zoomImage" class="zoom-image" alt="">
  </div>
</section>
<script>
let data = null;
let selectedId = null;
let zoomState = { open: false, scale: 1, fitScale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, originX: 0, originY: 0 };
const decisionLabels = {
  KEEP: 'Keep',
  ACCEPTED_STYLE_FALSE_POSITIVE: 'Accepted Style / False Positive',
  IMPROVEMENT_CANDIDATE: 'Improvement Candidate',
  REMOVAL_CANDIDATE: 'Removal Candidate',
  UNDECIDED: 'Undecided'
};
const workflowLabels = {
  IN_DATASET: 'In Dataset',
  QUARANTINE_PLANNED: 'Set Aside Intent (no files moved)',
  REVIEWED: 'Reviewed'
};
const shortcutDecision = { '1': 'KEEP', '2': 'ACCEPTED_STYLE_FALSE_POSITIVE', '3': 'IMPROVEMENT_CANDIDATE', '4': 'REMOVAL_CANDIDATE', 'u': 'UNDECIDED' };
async function loadData() {
  const response = await fetch('/api/review-data');
  if (!response.ok) throw new Error('Could not load review data');
  return await response.json();
}
function countBox(label, value) {
  return `<div class="count"><strong>${value}</strong><br>${label}</div>`;
}
function percent(value) { return `${Number(value || 0).toFixed(1)}%`; }
function escapeText(value) {
  return String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function label(value, labels) { return labels[value] || value || 'Undecided'; }
function currentImages() {
  if (!data) return [];
  const search = document.getElementById('search').value.toLowerCase();
  const decision = document.getElementById('decisionFilter').value;
  const workflow = document.getElementById('workflowFilter').value;
  const triage = document.getElementById('triageFilter').value;
  const category = document.getElementById('categoryFilter').value;
  const severity = document.getElementById('severityFilter').value;
  const confidence = Number(document.getElementById('confidenceFilter').value || 0);
  return data.images.filter(image => {
    const searchable = [image.filename, image.evidence_summary, image.primary_reason, image.finding_categories.join(' ')].join(' ').toLowerCase();
    return (!search || searchable.includes(search))
      && (!decision || (image.decision || 'UNDECIDED') === decision)
      && (!workflow || image.workflow_state === workflow)
      && (!triage || image.triage_status === triage)
      && (!category || image.finding_categories.includes(category))
      && (!severity || image.severities.includes(severity))
      && (!confidence || Number(image.max_confidence || 0) >= confidence);
  });
}
function renderCard(image) {
  const card = document.createElement('article');
  card.className = 'card ' + triageClass(image);
  if (image.id === selectedId) card.classList.add('selected');
  if (image.workflow_state === 'REVIEWED') card.classList.add('reviewed');
  if (image.workflow_state === 'QUARANTINE_PLANNED') card.classList.add('quarantine');
  card.innerHTML = `
    <img loading="lazy" src="${escapeText(image.thumbnail_url)}" alt="${escapeText(image.filename)}">
    <h3>${escapeText(image.filename)}</h3>
    <div class="badges">
      <span class="badge">${escapeText(image.triage_status)}</span>
      <span class="badge">${escapeText(label(image.decision, decisionLabels))}</span>
      <span class="badge">${escapeText(label(image.workflow_state, workflowLabels))}</span>
      <span class="badge">${image.finding_count} findings</span>
    </div>
    <p>${escapeText(image.evidence_summary)}</p>
    <div class="actions">
      ${decisionButton('KEEP', 'Keep')}
      ${decisionButton('ACCEPTED_STYLE_FALSE_POSITIVE', 'Accepted Style')}
      ${decisionButton('IMPROVEMENT_CANDIDATE', 'Improvement Candidate')}
      ${decisionButton('REMOVAL_CANDIDATE', 'Exclude Candidate')}
      ${decisionButton('UNDECIDED', 'Undecided')}
    </div>`;
  card.addEventListener('click', () => selectImage(image.id));
  card.addEventListener('dblclick', () => openPreview(image));
  card.querySelectorAll('button').forEach(button => button.addEventListener('click', event => {
    event.stopPropagation();
    saveDecision(image, button.dataset.decision, image.workflow_state, image.notes);
  }));
  return card;
}
function decisionButton(value, text) {
  return `<button type="button" data-decision="${value}" title="${escapeText(decisionLabels[value])}">${escapeText(text)}</button>`;
}
function triageClass(image) {
  if (image.recommendation === 'PRIORITY_REVIEW') return 'priority';
  if (image.recommendation === 'NEEDS_REVIEW') return 'needs';
  return 'none';
}
function groupTitle(label, count) { return `<div class="group-title"><h2>${escapeText(label)}</h2><span class="muted">${count}</span></div>`; }
function renderGroups() {
  const groups = [
    ['Priority Review', currentImages().filter(i => i.triage_status === 'Priority Review')],
    ['Needs Review', currentImages().filter(i => i.triage_status === 'Needs Review')],
    ['No Findings Emitted', currentImages().filter(i => i.triage_status === 'No Findings Emitted')]
  ];
  const root = document.getElementById('groups');
  root.innerHTML = '';
  root.insertAdjacentHTML('beforeend', '<h2>Review Queue</h2>');
  let visible = 0;
  groups.forEach(([name, images]) => {
    visible += images.length;
    const section = document.createElement('section');
    section.innerHTML = groupTitle(name, images.length) + '<div class="grid"></div>';
    const grid = section.querySelector('.grid');
    images.forEach(image => grid.appendChild(renderCard(image)));
    if (!images.length) grid.innerHTML = '<p class="muted">No images match this group with the current filters.</p>';
    root.appendChild(section);
  });
  if (!visible) {
    root.insertAdjacentHTML('afterbegin', '<p class="muted">No matching images. Clear filters or broaden the current review selection.</p>');
  }
  document.getElementById('visibleCount').textContent = `${visible} visible`;
  document.getElementById('filterSummary').textContent = currentFilterSummary();
}
function renderCounts() {
  document.getElementById('counts').innerHTML =
    countBox('Images', data.summary.image_count) +
    countBox('Reviewed', data.summary.already_reviewed_count) +
    countBox('Priority', data.summary.priority_review_count) +
    countBox('Remaining', data.summary.pending_review_count);
}
function renderOverview() {
  const overview = data.overview || {};
  const intelligence = data.dataset_intelligence || {};
  const reviewStatus = intelligence.review_status || {};
  const evidence = intelligence.evidence_summary || {};
  const concentration = evidence.concentration || {};
  const analyzerContribution = intelligence.analyzer_contribution || [];
  const coverage = intelligence.dataset_coverage || {};
  const characteristics = intelligence.dataset_characteristics || {};
  const guidance = intelligence.review_guidance || {};
  const provenance = intelligence.provenance || {};
  const scope = intelligence.scope || {};
  const progress = overview.review_progress || {};
  const triage = overview.triage_counts || {};
  const next = overview.next_action || {};
  const categories = overview.top_finding_categories || [];
  const analyzers = overview.analyzer_coverage_summary || [];
  const remaining = reviewStatus.remaining_undecided_by_triage || {};
  const evidenceRows = (evidence.category_rows || []).slice(0, 8);
  const unresolvedRows = (guidance.unresolved_evidence_categories || []).slice(0, 5);
  const categoryButtons = categories.length
    ? categories.map(item => `<button type="button" data-category="${escapeText(item.category)}">${escapeText(item.category)} (${item.count})</button>`).join('')
    : '<span class="muted">No finding categories emitted.</span>';
  const analyzerRows = analyzers.length
    ? analyzers.map(item => `<span class="badge">${escapeText(item.analyzer)}: ${item.finding_count} findings on ${item.image_count} images, Advisory review signal</span>`).join('')
    : '<span class="muted">No analyzer coverage summary was recorded.</span>';
  const evidenceTable = evidenceRows.length
    ? `<table class="intelligence-table"><thead><tr><th>Category</th><th>Findings</th><th>Images</th><th>Dataset</th><th>Severity</th><th>Undecided</th></tr></thead><tbody>${evidenceRows.map(item => `
      <tr>
        <td>${escapeText(item.finding_category)}</td>
        <td>${item.finding_count}</td>
        <td>${item.affected_image_count}</td>
        <td>${percent(item.affected_image_percentage)}</td>
        <td>${escapeText(item.highest_observed_severity || 'not recorded')}</td>
        <td>${item.undecided_image_count}</td>
      </tr>`).join('')}</tbody></table>`
    : '<p class="muted">No dataset-level finding categories were emitted.</p>';
  const analyzerTable = analyzerContribution.length
    ? `<table class="intelligence-table"><thead><tr><th>Analyzer</th><th>Family</th><th>Findings</th><th>Images</th><th>Policies</th><th>Source</th></tr></thead><tbody>${analyzerContribution.map(item => `
      <tr>
        <td>${escapeText(item.analyzer)} ${escapeText(item.version)}</td>
        <td>${escapeText(item.family)}</td>
        <td>${item.finding_count}</td>
        <td>${item.affected_image_count}</td>
        <td>${escapeText(item.calibration_status)}; execution ${escapeText(item.execution_policy)}; display ${escapeText(item.display_policy)}; triage ${escapeText(item.triage_policy)}</td>
        <td>${escapeText(item.metadata_source)}</td>
      </tr>`).join('')}</tbody></table>`
    : '<p class="muted">No analyzer contribution rows were recorded.</p>';
  const sidecars = coverage.optional_sidecars || {};
  const profile = provenance.inspection_profile || characteristics.inspection_profile || {};
  const unresolved = unresolvedRows.length
    ? unresolvedRows.map(item => `<span class="badge">${escapeText(item.finding_category)}: ${item.undecided_image_count} undecided images</span>`).join('')
    : '<span class="muted">No unresolved evidence categories emitted by current filters.</span>';
  document.getElementById('overview').innerHTML = `
    <h2>Dataset Intelligence</h2>
    <p>Overview from existing sidecars. No scoring, no automation.</p>
    <h2>Next Action</h2>
    <p><strong>${escapeText(next.label || 'Review dataset')}</strong></p>
    <p>${escapeText(next.reason || '')}</p>
    <p class="muted">This only changes filters and selection.</p>
    <div class="overview-actions">
      <button id="applyNextAction" type="button">Show Next Review Set</button>
      <button id="overviewClearFilters" type="button">Clear Filters</button>
    </div>
    <div class="overview-grid">
      ${countBox('Total images', overview.image_count || 0)}
      ${countBox('Priority Review', triage['Priority Review'] || 0)}
      ${countBox('Needs Review', triage['Needs Review'] || 0)}
      ${countBox('No Findings Emitted', triage['No Findings Emitted'] || 0)}
      ${countBox('Reviewed', progress.reviewed_count || 0)}
      ${countBox('Pending', progress.pending_review_count || 0)}
      ${countBox('Complete', (progress.completion_percent || 0) + '%')}
    </div>
    <details>
      <summary>Review Status</summary>
      <div class="overview-grid">
        ${countBox('Remaining Priority Review', remaining['Priority Review'] || 0)}
        ${countBox('Remaining Needs Review', remaining['Needs Review'] || 0)}
        ${countBox('Remaining No Findings Emitted', remaining['No Findings Emitted'] || 0)}
        ${countBox('Decision completion', percent(reviewStatus.decision_completion_percent))}
      </div>
    </details>
    <details>
      <summary>Evidence Summary</summary>
      <p class="intelligence-note">Top category: ${escapeText(concentration.top_category || 'none')} on ${concentration.top_category_image_count || 0} images (${percent(concentration.top_category_percentage)}).</p>
      ${evidenceTable}
      <h3>Top Finding Category Filters</h3>
      <div class="overview-list">${categoryButtons}</div>
    </details>
    <details>
      <summary>Analyzer Contribution</summary>
      ${analyzerTable}
      <h3>Analyzer Coverage</h3>
      <div class="overview-list">${analyzerRows}</div>
    </details>
    <details>
      <summary>Dataset Coverage</summary>
      <div class="overview-grid">
        ${countBox('Manifest', coverage.manifest_available ? 'yes' : 'no')}
        ${countBox('Review decisions', coverage.review_decisions_available ? 'yes' : 'no')}
        ${countBox('Comparison', coverage.comparison_available ? 'yes' : 'no')}
        ${countBox('Analyzer errors', coverage.error_count || 0)}
      </div>
      <p class="muted">Optional sidecars: triage dossiers ${sidecars['triage_dossiers.json'] ? 'present' : 'missing'}, manifest ${sidecars['inspection_manifest.json'] ? 'present' : 'missing'}, review decisions ${sidecars['review_decisions.json'] ? 'present' : 'missing'}, comparison ${sidecars['comparison_summary.json'] ? 'present' : 'missing'}.</p>
    </details>
    <details>
      <summary>Dataset Characteristics</summary>
      <p class="muted">Profile: ${escapeText((profile && profile.id) || 'not recorded')} ${escapeText((profile && profile.version) || '')}. Dataset Forge version: ${escapeText(provenance.dataset_forge_version || characteristics.dataset_forge_version || 'not recorded')}. Inspection completed: ${escapeText(characteristics.inspection_completed_at || 'not recorded')}.</p>
    </details>
    <details>
      <summary>Unresolved Evidence Categories</summary>
      <div class="overview-list">${unresolved}</div>
    </details>
    <p class="muted">No current review finding. Not a guarantee.</p>
    <p class="muted">Dataset Intelligence scope: descriptive only ${scope.descriptive_only ? 'yes' : 'no'}; no quality score ${scope.no_quality_score ? 'yes' : 'no'}; does not run analyzers ${scope.does_not_run_analyzers ? 'yes' : 'no'}; does not modify images ${scope.does_not_modify_images ? 'yes' : 'no'}.</p>
    <p class="muted">Set Aside Intent is workflow intent only. Dataset Forge does not create quarantine folders or move files.</p>`;
  document.getElementById('applyNextAction').addEventListener('click', applyNextAction);
  document.getElementById('overviewClearFilters').addEventListener('click', clearFilters);
  document.querySelectorAll('#overview [data-category]').forEach(button => {
    button.addEventListener('click', () => {
      document.getElementById('categoryFilter').value = button.dataset.category;
      renderGroups();
    });
  });
}
function populateFilters() {
  const decision = document.getElementById('decisionFilter');
  data.decision_values.forEach(value => decision.insertAdjacentHTML('beforeend', `<option value="${value}">${escapeText(label(value, decisionLabels))}</option>`));
  const workflow = document.getElementById('workflowFilter');
  data.workflow_states.forEach(value => workflow.insertAdjacentHTML('beforeend', `<option value="${value}">${escapeText(label(value, workflowLabels))}</option>`));
  const categories = [...new Set(data.images.flatMap(image => image.finding_categories))].sort();
  categories.forEach(value => document.getElementById('categoryFilter').insertAdjacentHTML('beforeend', `<option value="${escapeText(value)}">${escapeText(value)}</option>`));
  const severities = [...new Set(data.images.flatMap(image => image.severities))].sort();
  severities.forEach(value => document.getElementById('severityFilter').insertAdjacentHTML('beforeend', `<option value="${escapeText(value)}">${escapeText(value)}</option>`));
}
function selectImage(id) {
  selectedId = id;
  renderGroups();
  renderDetail();
}
function selectedImage() {
  return data.images.find(image => image.id === selectedId) || data.images[0];
}
function currentFilterSummary() {
  const labels = [];
  const decision = document.getElementById('decisionFilter').value;
  const workflow = document.getElementById('workflowFilter').value;
  const values = [
    ['Search', document.getElementById('search').value],
    ['Decision', decision ? label(decision, decisionLabels) : ''],
    ['Workflow', workflow ? label(workflow, workflowLabels) : ''],
    ['Triage', document.getElementById('triageFilter').value],
    ['Category', document.getElementById('categoryFilter').value],
    ['Severity', document.getElementById('severityFilter').value],
    ['Confidence', document.getElementById('confidenceFilter').value ? document.getElementById('confidenceFilter').selectedOptions[0].textContent : '']
  ];
  values.forEach(([name, value]) => { if (value) labels.push(`${name}: ${value}`); });
  return labels.length ? `Filters: ${labels.join(' | ')}` : 'Filters: none';
}
function renderDetail() {
  const image = selectedImage();
  if (!image) return;
  selectedId = image.id;
  document.getElementById('detail').innerHTML = `
    <img class="preview" src="${escapeText(image.thumbnail_url)}" alt="${escapeText(image.filename)}">
    <h2>${escapeText(image.filename)}</h2>
    <p><strong>Path:</strong> ${escapeText(image.image_path)}</p>
    <p><strong>Triage:</strong> ${escapeText(image.triage_status)}</p>
    <p><strong>Evidence:</strong> ${escapeText(image.evidence_summary)}</p>
    <p><strong>Suggested review action:</strong> ${escapeText(image.suggested_review_action)}</p>
    <div class="decision-buttons">
      ${detailDecisionButton('KEEP', '1 Keep')}
      ${detailDecisionButton('ACCEPTED_STYLE_FALSE_POSITIVE', '2 Accepted Style / False Positive')}
      ${detailDecisionButton('IMPROVEMENT_CANDIDATE', '3 Improvement Candidate')}
      ${detailDecisionButton('REMOVAL_CANDIDATE', '4 Exclude Candidate')}
      ${detailDecisionButton('UNDECIDED', 'U Undecided')}
    </div>
    <p class="muted">All decisions save to <code>review_decisions.json</code>.</p>
    <p id="saveStatus" class="muted save-status" role="status" aria-live="polite">Saved</p>
    <label for="workflowState">Workflow state</label>
    <select id="workflowState">${data.workflow_states.map(value => `<option value="${value}" ${value === image.workflow_state ? 'selected' : ''}>${escapeText(label(value, workflowLabels))}</option>`).join('')}</select>
    <label for="notes">Notes</label>
    <textarea id="notes">${escapeText(image.notes)}</textarea>
    <h2>Findings</h2>
    ${renderFindings(image)}
    <h2>Analyzer Coverage</h2>
    ${renderCoverage()}
    <h2>Triage Dossier</h2>
    <p><a href="${escapeText(image.dossier_anchor)}">Dossier anchor</a></p>
    <p class="muted">No current review finding. Not a guarantee.</p>`;
  document.querySelectorAll('.decision-buttons button').forEach(button => button.addEventListener('click', () => {
    saveDecision(image, button.dataset.decision, document.getElementById('workflowState').value, document.getElementById('notes').value);
  }));
  document.querySelector('.preview').addEventListener('click', () => openZoom(image));
  document.getElementById('workflowState').addEventListener('change', event => saveDecision(image, image.decision || 'UNDECIDED', event.target.value, document.getElementById('notes').value));
  document.getElementById('notes').addEventListener('change', event => saveDecision(image, image.decision || 'UNDECIDED', document.getElementById('workflowState').value, event.target.value));
}
function detailDecisionButton(value, text) {
  const image = selectedImage();
  return `<button type="button" data-decision="${value}" class="${image && (image.decision || 'UNDECIDED') === value ? 'selected' : ''}">${escapeText(text)}</button>`;
}
function renderFindings(image) {
  if (!image.findings.length) return '<p>No current findings emitted.</p>';
  return image.findings.map(finding => `
    <section class="finding">
      <h3>${escapeText(finding.category)} / ${escapeText(finding.analyzer)}</h3>
      <p><strong>Severity:</strong> ${escapeText(finding.severity)} <strong>Confidence:</strong> ${escapeText(finding.confidence)}</p>
      <p>${escapeText(finding.explanation)}</p>
      <p>${escapeText(finding.recommendation)}</p>
    </section>`).join('');
}
function renderCoverage() {
  const analyzers = (data.analyzer_coverage && data.analyzer_coverage.analyzers) || [];
  if (!analyzers.length) return '<p>No analyzer coverage summary was recorded.</p>';
  return analyzers.map(item => `<p>${escapeText(item.analyzer || '')}: ${escapeText(item.finding_count || 0)} findings on ${escapeText(item.image_count || 0)} images. Advisory review signal.</p>`).join('');
}
async function saveDecision(image, decision, workflowState, notes) {
  const center = document.querySelector('.center');
  const previousScroll = center ? center.scrollTop : 0;
  setSaveStatus('Saving...');
  const response = await fetch('/api/decision', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ image_path: image.image_path, recommendation: image.triage_status, decision, workflow_state: workflowState, notes })
  });
  if (!response.ok) {
    const error = await response.json();
    setSaveStatus('Save failed');
    alert(error.error || 'Could not save decision');
    return;
  }
  data = await response.json();
  renderCounts();
  renderOverview();
  renderGroups();
  renderDetail();
  if (center) center.scrollTop = previousScroll;
  setSaveStatus('Saved');
}
function setSaveStatus(text) {
  const status = document.getElementById('saveStatus');
  if (status) status.textContent = text;
}
function moveSelection(offset) {
  const visible = currentImages();
  if (!visible.length) return;
  const index = Math.max(0, visible.findIndex(image => image.id === selectedId));
  const next = visible[(index + offset + visible.length) % visible.length];
  selectImage(next.id);
}
function nextUndecided() {
  const target = currentImages().find(image => !image.decision || image.decision === 'UNDECIDED');
  if (target) selectImage(target.id);
}
function clearFilters() {
  ['search', 'decisionFilter', 'workflowFilter', 'triageFilter', 'categoryFilter', 'severityFilter', 'confidenceFilter'].forEach(id => {
    document.getElementById(id).value = '';
  });
  renderGroups();
}
function applyNextAction() {
  const next = data.overview && data.overview.next_action;
  if (!next) return;
  clearFilters();
  const filter = next.target_filter || {};
  if (filter.triage_status) document.getElementById('triageFilter').value = filter.triage_status;
  if (filter.decision) document.getElementById('decisionFilter').value = filter.decision;
  renderGroups();
  if (next.target_image_id) selectImage(next.target_image_id);
}
function openPreview(image) {
  openZoom(image);
}
function openZoom(image) {
  if (!image) return;
  selectedId = image.id;
  const viewer = document.getElementById('zoomViewer');
  const zoomImage = document.getElementById('zoomImage');
  document.getElementById('zoomTitle').textContent = `${image.filename} - ${image.triage_status}`;
  zoomImage.alt = image.filename;
  zoomImage.onload = () => fitZoom();
  zoomImage.src = image.thumbnail_url;
  viewer.hidden = false;
  zoomState.open = true;
  renderGroups();
  renderDetail();
}
function closeZoom() {
  document.getElementById('zoomViewer').hidden = true;
  zoomState.open = false;
}
function fitZoom() {
  const stage = document.getElementById('zoomStage');
  const image = document.getElementById('zoomImage');
  const naturalWidth = image.naturalWidth || 1;
  const naturalHeight = image.naturalHeight || 1;
  zoomState.fitScale = Math.min(stage.clientWidth / naturalWidth, stage.clientHeight / naturalHeight, 1);
  zoomState.scale = zoomState.fitScale;
  zoomState.x = 0;
  zoomState.y = 0;
  applyZoom();
}
function actualZoom() {
  zoomState.scale = 1;
  zoomState.x = 0;
  zoomState.y = 0;
  applyZoom();
}
function changeZoom(delta, anchorX, anchorY) {
  const before = zoomState.scale;
  zoomState.scale = Math.max(zoomState.fitScale * .5, Math.min(8, zoomState.scale * delta));
  if (anchorX != null && anchorY != null && before > 0) {
    const ratio = zoomState.scale / before;
    zoomState.x = anchorX - (anchorX - zoomState.x) * ratio;
    zoomState.y = anchorY - (anchorY - zoomState.y) * ratio;
  }
  applyZoom();
}
function applyZoom() {
  const image = document.getElementById('zoomImage');
  image.style.width = `${image.naturalWidth || 1}px`;
  image.style.height = `${image.naturalHeight || 1}px`;
  image.style.transform = `translate(calc(-50% + ${zoomState.x}px), calc(-50% + ${zoomState.y}px)) scale(${zoomState.scale})`;
}
function zoomMove(offset) {
  moveSelection(offset);
  openZoom(selectedImage());
}
function toggleZoom() {
  if (zoomState.open) closeZoom();
  else openZoom(selectedImage());
}
async function render() {
  data = await loadData();
  populateFilters();
  selectedId = data.images[0] && data.images[0].id;
  renderCounts();
  renderOverview();
  renderGroups();
  renderDetail();
}
['search', 'decisionFilter', 'workflowFilter', 'triageFilter', 'categoryFilter', 'severityFilter', 'confidenceFilter'].forEach(id => {
  document.getElementById(id).addEventListener('input', renderGroups);
  document.getElementById(id).addEventListener('change', renderGroups);
});
document.getElementById('thumbSize').addEventListener('input', event => document.documentElement.style.setProperty('--thumb-size', event.target.value + 'px'));
document.getElementById('nextUndecided').addEventListener('click', nextUndecided);
document.getElementById('clearFilters').addEventListener('click', clearFilters);
document.getElementById('shortcutHelp').addEventListener('click', () => document.getElementById('shortcuts').showModal());
document.getElementById('zoomClose').addEventListener('click', closeZoom);
document.getElementById('zoomPrev').addEventListener('click', () => zoomMove(-1));
document.getElementById('zoomNext').addEventListener('click', () => zoomMove(1));
document.getElementById('zoomFit').addEventListener('click', fitZoom);
document.getElementById('zoomActual').addEventListener('click', actualZoom);
document.getElementById('zoomOut').addEventListener('click', () => changeZoom(1 / 1.25));
document.getElementById('zoomIn').addEventListener('click', () => changeZoom(1.25));
document.getElementById('zoomStage').addEventListener('wheel', event => {
  event.preventDefault();
  const rect = event.currentTarget.getBoundingClientRect();
  changeZoom(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left - rect.width / 2, event.clientY - rect.top - rect.height / 2);
});
document.getElementById('zoomStage').addEventListener('pointerdown', event => {
  zoomState.dragging = true;
  zoomState.startX = event.clientX;
  zoomState.startY = event.clientY;
  zoomState.originX = zoomState.x;
  zoomState.originY = zoomState.y;
  event.currentTarget.classList.add('dragging');
  event.currentTarget.setPointerCapture(event.pointerId);
});
document.getElementById('zoomStage').addEventListener('pointermove', event => {
  if (!zoomState.dragging) return;
  zoomState.x = zoomState.originX + event.clientX - zoomState.startX;
  zoomState.y = zoomState.originY + event.clientY - zoomState.startY;
  applyZoom();
});
document.getElementById('zoomStage').addEventListener('pointerup', event => {
  zoomState.dragging = false;
  event.currentTarget.classList.remove('dragging');
  event.currentTarget.releasePointerCapture(event.pointerId);
});
document.addEventListener('keydown', event => {
  if (zoomState.open) {
    if (event.key === 'Escape') { event.preventDefault(); closeZoom(); return; }
    if (event.key === ' ' || event.key === 'f') { event.preventDefault(); closeZoom(); return; }
    if (event.key === 'j' || event.key === 'ArrowLeft') { event.preventDefault(); zoomMove(-1); return; }
    if (event.key === 'k' || event.key === 'ArrowRight') { event.preventDefault(); zoomMove(1); return; }
    if (event.key === '+' || event.key === '=') { event.preventDefault(); changeZoom(1.25); return; }
    if (event.key === '-') { event.preventDefault(); changeZoom(1 / 1.25); return; }
    if (event.key === '0') { event.preventDefault(); fitZoom(); return; }
    if (event.key === '1') { event.preventDefault(); actualZoom(); return; }
  }
  if (event.target.matches('input, textarea, select')) return;
  if (event.key === '?' ) document.getElementById('shortcuts').showModal();
  if (event.key === 'j' || event.key === 'ArrowLeft') moveSelection(-1);
  if (event.key === 'k' || event.key === 'ArrowRight') moveSelection(1);
  if (event.key === 'n') nextUndecided();
  if (event.key === ' ') { event.preventDefault(); toggleZoom(); }
  if (event.key === 'f') { const image = selectedImage(); if (image) openPreview(image); }
  const decision = shortcutDecision[event.key.toLowerCase()];
  if (decision) { const image = selectedImage(); if (image) saveDecision(image, decision, image.workflow_state, image.notes); }
});
render().catch(error => document.body.insertAdjacentHTML('beforeend', `<pre>${escapeText(error.message)}</pre>`));
</script>
</body>
</html>
"""


__all__ = [
    "DEFAULT_REVIEW_PORT",
    "INSPECTION_REPORT_FILENAME",
    "LOCAL_REVIEW_HOST",
    "RECOMMENDATION_SUMMARY_FILENAME",
    "REVIEW_DECISIONS_FILENAME",
    "ReviewServerError",
    "ReviewWorkspace",
    "TRIAGE_DOSSIERS_FILENAME",
    "atomic_write_json",
    "build_review_data",
    "create_review_server",
    "load_review_workspace",
    "serve_review_server",
    "update_review_decision",
]
