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
) -> Path:
    """Write review_gallery.html from existing report sidecars only."""

    inspection_report = json.loads(inspection_report_path.read_text(encoding="utf-8"))
    recommendation_summary = json.loads(
        recommendation_summary_path.read_text(encoding="utf-8")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_static_review_gallery(inspection_report, recommendation_summary),
        encoding="utf-8",
    )
    return output_path


def render_static_review_gallery(
    inspection_report: Mapping[str, Any],
    recommendation_summary: Mapping[str, Any],
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
        '<section class="counts" aria-label="Recommendation counts">',
        _count("Ready for Training", ready_count),
        _count("Needs Review", int(summary.get("needs_review_count", 0))),
        _count("Priority Review", int(summary.get("priority_review_count", 0))),
        "</section>",
        '<section class="note">',
        "<p>Recommendations are review priorities.</p>",
        "<p>Source images were not modified.</p>",
        (
            "<p>Ready for Training is not a guarantee of artifact-free "
            "images.</p>"
        ),
        "</section>",
        "</header>",
    ])

    lines.extend(_section("Priority Review", recommendations, "PRIORITY_REVIEW"))
    lines.extend(_section("Needs Review", recommendations, "NEEDS_REVIEW"))
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
        lines.extend(_card(item))
    lines.extend(["</div>", "</section>"])
    return lines


def _card(item: Mapping[str, Any]) -> list[str]:
    image_path = str(item.get("image_path", ""))
    refs = list(item.get("finding_refs", []))
    primary_ref = refs[0] if refs else {}
    filename = Path(image_path).name or image_path
    image_src = _image_src(image_path)
    return [
        '<article class="card">',
        f'<img src="{escape(image_src)}" alt="{escape(filename)}">',
        "<div>",
        f"<h3>{escape(filename)}</h3>",
        f"<p><strong>Recommendation:</strong> {escape(str(item.get('display_label', '')))}</p>",
        f"<p><strong>Primary reason:</strong> {escape(str(item.get('primary_reason', '')))}</p>",
        (
            "<p><strong>Finding category:</strong> "
            f"{escape(str(primary_ref.get('category', 'none')))}</p>"
        ),
        f"<p><strong>Severity:</strong> {escape(str(primary_ref.get('severity', 'none')))}</p>",
        f"<p><strong>Analyzer:</strong> {escape(str(primary_ref.get('analyzer', 'none')))}</p>",
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
.ready-summary {
  padding: 16px;
}
.note p:last-child,
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
    width: 100%;
    height: auto;
    max-height: 240px;
  }
}
""".strip()


__all__ = [
    "render_static_review_gallery",
    "write_static_review_gallery",
]
