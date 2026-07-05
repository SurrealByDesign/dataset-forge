"""Static HTML review gallery rendered from inspection sidecars."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Mapping


def write_static_review_gallery(
    inspection_report_path: Path,
    recommendation_summary_path: Path,
    output_path: Path,
    *,
    review_statuses: Mapping[str, Any] | None = None,
) -> Path:
    """Write review_gallery.html from existing report sidecars only."""

    inspection_report = json.loads(inspection_report_path.read_text(encoding="utf-8"))
    recommendation_summary = json.loads(
        recommendation_summary_path.read_text(encoding="utf-8")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_static_review_gallery(
            inspection_report,
            recommendation_summary,
            review_statuses=review_statuses,
        ),
        encoding="utf-8",
    )
    return output_path


def render_static_review_gallery(
    inspection_report: Mapping[str, Any],
    recommendation_summary: Mapping[str, Any],
    *,
    review_statuses: Mapping[str, Any] | None = None,
) -> str:
    """Render deterministic plain HTML from inspection and recommendation JSON."""

    summary = recommendation_summary.get("summary", {})
    recommendations = list(recommendation_summary.get("recommendations", []))
    dataset_path = str(inspection_report.get("dataset_path", ""))
    ready_count = int(summary.get("ready_for_training_count", 0))

    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Dataset Forge Review Gallery</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<h1>Dataset Forge Review Gallery</h1>",
    ]
    if dataset_path:
        lines.append(f"<p>Dataset: <code>{escape(dataset_path)}</code></p>")
    lines.extend([
        '<section class="dataset-summary" aria-label="Dataset Summary">',
        "<h2>Dataset Summary</h2>",
        '<div class="counts">',
        _count("Ready for Training", ready_count),
        _count("Needs Review", int(summary.get("needs_review_count", 0))),
        _count("Priority Review", int(summary.get("priority_review_count", 0))),
        _count("Images inspected", int(summary.get("image_count", 0))),
        "</div>",
        "<h3>Most common finding categories</h3>",
        "<ul>",
        *_common_category_lines(recommendations),
        "</ul>",
        "</section>",
        '<section class="note">',
        "<p>Recommendations are based only on current deterministic findings.</p>",
        "<p>Ready for Training means no current findings were emitted.</p>",
        (
            "<p>It does not guarantee the image is artifact-free.</p>"
        ),
        "<p>Dataset Forge never modifies source images.</p>",
        "</section>",
        "</header>",
    ])

    lines.extend(_section("Priority Review", recommendations, "PRIORITY_REVIEW", review_statuses))
    lines.extend(_section("Needs Review", recommendations, "NEEDS_REVIEW", review_statuses))
    lines.extend([
        '<section class="ready-summary">',
        "<h2>Ready for Training</h2>",
        (
            f"<p>{ready_count} {_image_word(ready_count)} emitted no current "
            "findings requiring review.</p>"
        ),
        "</section>",
        "</main>",
        "</body>",
        "</html>",
        "",
    ])
    return "\n".join(lines)


def _section(
    title: str,
    recommendations: list[Mapping[str, Any]],
    recommendation: str,
    review_statuses: Mapping[str, Any] | None,
) -> list[str]:
    items = [
        item for item in recommendations
        if item.get("recommendation") == recommendation
    ]
    lines = ["<section>", f"<h2>{escape(title)}</h2>"]
    if not items:
        lines.extend(["<p>No images in this group.</p>", "</section>"])
        return lines
    lines.append('<div class="cards">')
    for item in items:
        lines.extend(_card(item, review_statuses))
    lines.extend(["</div>", "</section>"])
    return lines


def _card(item: Mapping[str, Any], review_statuses: Mapping[str, Any] | None) -> list[str]:
    image_path = str(item.get("image_path", ""))
    refs = list(item.get("finding_refs", []))
    filename = Path(image_path).name or image_path
    image_src = _image_src(image_path)
    categories = _ref_values(refs, "category")
    analyzers = _ref_values(refs, "analyzer")
    severities = _ref_values(refs, "severity")
    review_status, review_decision = _review_status_text(image_path, review_statuses)
    return [
        '<article class="card">',
        f'<img src="{escape(image_src)}" alt="{escape(filename)}">',
        "<div>",
        f"<h3>{escape(filename)}</h3>",
        f"<p><strong>Recommendation:</strong> {escape(str(item.get('display_label', '')))}</p>",
        f"<p><strong>Review Status:</strong> {escape(review_status)}</p>",
        f"<p><strong>Decision:</strong> {escape(review_decision)}</p>",
        f"<p><strong>Primary reason:</strong> {escape(str(item.get('primary_reason', '')))}</p>",
        (
            "<p><strong>Finding categories:</strong> "
            f"{escape('; '.join(categories))}</p>"
        ),
        f"<p><strong>Severity:</strong> {escape('; '.join(severities))}</p>",
        f"<p><strong>Analyzer:</strong> {escape('; '.join(analyzers))}</p>",
        f"<p><strong>Finding count:</strong> {len(refs)}</p>",
        "</div>",
        "</article>",
    ]


def _count(label: str, count: int) -> str:
    return (
        '<div class="count">'
        f"<span>{escape(label)}</span>"
        f"<strong>{count}</strong>"
        "</div>"
    )


def _image_src(image_path: str) -> str:
    if not image_path:
        return ""
    return Path(image_path).expanduser().resolve().as_uri()


def _image_word(count: int) -> str:
    return "image" if count == 1 else "images"


def _common_category_lines(recommendations: list[Mapping[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for item in recommendations:
        for ref in item.get("finding_refs", []):
            category = str(ref.get("category", ""))
            if category:
                counts[category] = counts.get(category, 0) + 1
    if not counts:
        return ["<li>none</li>"]
    return [
        f"<li>{escape(category)}: {count}</li>"
        for category, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
    ]


def _ref_values(refs: list[Mapping[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for ref in refs:
        value = str(ref.get(field, ""))
        if value and value not in values:
            values.append(value)
    return values or ["none"]


def _review_status_text(
    image_path: str,
    review_statuses: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if review_statuses is None:
        return ("Pending Review", "None recorded")
    status = review_statuses.get(image_path)
    if status is None:
        return ("Pending Review", "None recorded")
    status_text = str(getattr(status, "status", "Pending Review"))
    decisions = tuple(getattr(status, "decisions", ()))
    if not decisions:
        return (status_text, "None recorded")
    return (status_text, "; ".join(str(decision) for decision in decisions))


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --ink: #1f2933;
  --muted: #5b6472;
  --line: #d9dee7;
  --paper: #f7f8fb;
  --panel: #ffffff;
  --accent: #28536b;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
  line-height: 1.45;
}
main {
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 20px 48px;
}
h1,
h2,
h3,
p {
  margin-top: 0;
}
header {
  border-bottom: 1px solid var(--line);
  margin-bottom: 28px;
  padding-bottom: 24px;
}
code {
  background: #eef2f6;
  padding: 2px 5px;
}
.counts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 20px 0;
}
.count,
.note,
.card,
.dataset-summary,
.ready-summary {
  background: var(--panel);
  border: 1px solid var(--line);
}
.count {
  padding: 14px;
}
.count span {
  display: block;
  color: var(--muted);
  font-size: 14px;
}
.count strong {
  display: block;
  font-size: 30px;
  margin-top: 6px;
}
.note,
.dataset-summary,
.ready-summary {
  padding: 16px;
}
.note p:last-child,
.dataset-summary ul,
.ready-summary p:last-child,
.card p:last-child {
  margin-bottom: 0;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
  margin-bottom: 28px;
}
.card {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 14px;
  padding: 12px;
}
.card img {
  width: 150px;
  height: 150px;
  object-fit: contain;
  background: #eef2f6;
  border: 1px solid var(--line);
}
.card h3 {
  color: var(--accent);
  font-size: 18px;
  overflow-wrap: anywhere;
}
.card p {
  color: var(--muted);
  margin-bottom: 6px;
}
@media (max-width: 560px) {
  .card {
    grid-template-columns: 1fr;
  }
  .card img {
    width: auto;
    height: auto;
    max-height: 240px;
  }
}
""".strip()


__all__ = [
    "render_static_review_gallery",
    "write_static_review_gallery",
]
