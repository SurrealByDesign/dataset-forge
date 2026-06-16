from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageOps

from dataset_forge.quality import Recommendation

SEVERITY_RANK = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}
PLACEHOLDER_IMAGE = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg' width='256' height='256'%3E"
    "%3Crect width='100%25' height='100%25' fill='%23202736'/%3E"
    "%3Ctext x='50%25' y='50%25' fill='%239aa4b2' text-anchor='middle'"
    " dominant-baseline='middle' font-family='sans-serif'%3E"
    "Preview unavailable%3C/text%3E%3C/svg%3E"
)


def generate_review_gallery(
    output_path: Path,
    rows: list[dict[str, object]],
    recommendations: list[Recommendation],
    health_report: dict[str, object],
    *,
    thumbnail_size: int = 256,
    create_thumbnails: bool = True,
    decision_metadata: Mapping[str, Mapping[str, object]] | None = None,
) -> Path:
    gallery_path = output_path / "review_gallery"
    gallery_path.mkdir(parents=True, exist_ok=True)
    thumbnails_path = gallery_path / "thumbnails"
    if create_thumbnails:
        thumbnails_path.mkdir(parents=True, exist_ok=True)

    recommendation_queues: dict[str, list[Recommendation]] = {}
    for recommendation in recommendations:
        recommendation_queues.setdefault(recommendation.filename, []).append(
            recommendation
        )
    metadata = (
        dict(decision_metadata)
        if decision_metadata is not None
        else _load_decision_metadata(output_path)
    )

    cards: list[str] = []
    for index, row in enumerate(rows):
        filename = str(row.get("filename", "Unknown image"))
        queue = recommendation_queues.get(filename, [])
        recommendation = queue.pop(0) if queue else _missing_recommendation(filename)
        image_source = _image_source(
            row,
            index,
            thumbnails_path,
            gallery_path,
            thumbnail_size,
            create_thumbnails,
        )
        cards.append(
            _render_card(
                row,
                recommendation,
                image_source,
                metadata.get(filename, {}),
            )
        )

    index_path = gallery_path / "index.html"
    index_path.write_text(
        _render_page(cards, health_report),
        encoding="utf-8",
    )
    return index_path


def _image_source(
    row: dict[str, object],
    index: int,
    thumbnails_path: Path,
    gallery_path: Path,
    thumbnail_size: int,
    create_thumbnails: bool,
) -> str:
    source = Path(str(row.get("original_path", ""))).expanduser().resolve()
    if not create_thumbnails:
        try:
            return source.as_uri()
        except ValueError:
            return PLACEHOLDER_IMAGE

    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    thumbnail_name = f"{index:06d}-{digest}.jpg"
    destination = thumbnails_path / thumbnail_name
    if destination.parent.resolve() != thumbnails_path.resolve():
        raise ValueError("Thumbnail path escaped the review gallery.")
    try:
        _create_thumbnail(source, destination, thumbnail_size)
    except (OSError, ValueError):
        return PLACEHOLDER_IMAGE
    return destination.relative_to(gallery_path).as_posix()


def _create_thumbnail(source: Path, destination: Path, size: int) -> None:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image.save(destination, "JPEG", quality=82, optimize=True)


def _render_card(
    row: dict[str, object],
    recommendation: Recommendation,
    image_source: str,
    decision: Mapping[str, object],
) -> str:
    severity = recommendation.severity if recommendation.severity in SEVERITY_RANK else "INFO"
    cleanup = recommendation.recommended_action == "Recommend cleanup"
    duplicate = float(row.get("duplicate_risk") or 0) > 0
    proposed_action = str(
        decision.get("generated_action")
        or decision.get("action")
        or "Not planned"
    )
    approval_status = str(
        decision.get("approval_status")
        or decision.get("status")
        or "proposed"
    )
    override_status = bool(decision.get("override_status", False))
    locked = bool(decision.get("locked", False))
    return f"""
<article class="card severity-{severity.lower()}"
  data-artifact="{_number(row.get('artifact_score'))}"
  data-quality="{_number(row.get('overall_quality_score'))}"
  data-severity="{SEVERITY_RANK[severity]}"
  data-severity-name="{severity}"
  data-cleanup="{str(cleanup).lower()}"
  data-duplicate="{str(duplicate).lower()}">
  <img loading="lazy" src="{html.escape(image_source, quote=True)}"
       alt="Preview of {html.escape(str(row.get('filename', 'image')), quote=True)}">
  <div class="card-body">
    <div class="card-heading">
      <h2>{html.escape(str(row.get('filename', 'Unknown image')))}</h2>
      <span class="badge">{severity}</span>
    </div>
    <div class="scores">
      {_score("Quality", row.get("overall_quality_score"))}
      {_score("Artifact", row.get("artifact_score"))}
      {_score("Texture", row.get("texture_score"))}
      {_score("Duplicate risk", row.get("duplicate_risk"))}
    </div>
    {_detail("Action", recommendation.recommended_action)}
    {_detail("Reason", recommendation.reason)}
    {_detail("Suggested preset", recommendation.suggested_preset or "None")}
    {_detail("Suggested strength", recommendation.suggested_strength or "None")}
    {_detail("Proposed action", proposed_action)}
    {_detail("Approval status", approval_status)}
    {_detail("Override status", "overridden" if override_status else "unchanged")}
    {_detail("Locked status", "locked" if locked else "unlocked")}
  </div>
</article>"""


def _score(label: str, value: object) -> str:
    return (
        f'<div><span>{html.escape(label)}</span>'
        f"<strong>{_number(value):.1f}</strong></div>"
    )


def _detail(label: str, value: str) -> str:
    return (
        f'<p><strong>{html.escape(label)}:</strong> '
        f"{html.escape(value)}</p>"
    )


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _missing_recommendation(filename: str) -> Recommendation:
    return Recommendation(
        filename=filename,
        severity="INFO",
        issue="Recommendation unavailable",
        recommended_action="Recommend review",
        reason="No image-level recommendation data was available for this item.",
    )


def _load_decision_metadata(
    output_path: Path,
) -> dict[str, Mapping[str, object]]:
    for name in ("approved_cleanup_plan.json", "cleanup_plan.json"):
        path = output_path / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return {
            str(item.get("filename", "")): item
            for item in data.get("decisions", [])
            if isinstance(item, dict)
        }
    return {}


def _render_page(cards: list[str], health: dict[str, object]) -> str:
    summary = (
        _summary_item("Dataset health", health.get("dataset_health_score"), "/100")
        + _summary_item("Total images", health.get("total_images"))
        + _summary_item("Cleanup", health.get("images_requiring_cleanup"))
        + _summary_item("Duplicates", health.get("likely_duplicates"))
        + _summary_item("Low resolution", health.get("low_resolution_images"))
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dataset Forge Review Gallery</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #10141d; color: #eef2f7; }}
header {{ position: sticky; top: 0; z-index: 2; padding: 20px; background: #171d28ee; backdrop-filter: blur(12px); }}
h1 {{ margin: 0 0 14px; font-size: 1.6rem; }}
.summary, .controls, .scores {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.summary div {{ min-width: 130px; padding: 10px 14px; background: #222a38; border-radius: 9px; }}
.summary span, .scores span {{ display: block; color: #aeb8c7; font-size: .78rem; }}
.summary strong {{ font-size: 1.25rem; }}
.controls {{ margin-top: 14px; align-items: center; }}
select, label {{ padding: 8px 10px; background: #222a38; color: #eef2f7; border: 1px solid #3a4659; border-radius: 7px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 18px; padding: 20px; }}
.card {{ overflow: hidden; background: #1a202c; border: 1px solid #303a4b; border-radius: 12px; }}
.card[hidden] {{ display: none; }}
.card img {{ width: 100%; height: 250px; display: block; object-fit: contain; background: #0c1017; }}
.card-body {{ padding: 14px; }}
.card-heading {{ display: flex; gap: 10px; align-items: start; justify-content: space-between; }}
h2 {{ margin: 0; overflow-wrap: anywhere; font-size: 1rem; }}
.badge {{ padding: 4px 7px; border-radius: 6px; font-size: .7rem; font-weight: 700; }}
.severity-critical .badge {{ background: #8e2635; }}
.severity-warning .badge {{ background: #8a611c; }}
.severity-info .badge {{ background: #285f82; }}
.scores {{ margin: 12px 0; }}
.scores div {{ flex: 1 1 90px; padding: 8px; background: #222a38; border-radius: 7px; }}
.scores strong {{ font-size: 1.05rem; }}
p {{ margin: 7px 0; color: #cbd3df; font-size: .88rem; line-height: 1.35; }}
.empty {{ padding: 40px; color: #aeb8c7; }}
</style>
</head>
<body>
<header>
  <h1>Dataset Forge Review Gallery</h1>
  <section class="summary">{summary}</section>
  <section class="controls">
    <select id="sort">
      <option value="artifact">Sort: artifact score</option>
      <option value="quality">Sort: quality score</option>
      <option value="severity">Sort: severity</option>
    </select>
    <select id="severity">
      <option value="ALL">All severities</option>
      <option value="CRITICAL">CRITICAL</option>
      <option value="WARNING">WARNING</option>
      <option value="INFO">INFO</option>
    </select>
    <label><input id="cleanup" type="checkbox"> Cleanup recommended</label>
    <label><input id="duplicates" type="checkbox"> Duplicates</label>
  </section>
</header>
<main id="gallery">
{''.join(cards) if cards else '<p class="empty">No images were available for review.</p>'}
</main>
<script>
const gallery = document.getElementById('gallery');
const controls = ['sort', 'severity', 'cleanup', 'duplicates'].map(id => document.getElementById(id));
function refresh() {{
  const cards = [...gallery.querySelectorAll('.card')];
  const sort = document.getElementById('sort').value;
  const severity = document.getElementById('severity').value;
  const cleanup = document.getElementById('cleanup').checked;
  const duplicates = document.getElementById('duplicates').checked;
  cards.forEach(card => {{
    card.hidden = (severity !== 'ALL' && card.dataset.severityName !== severity)
      || (cleanup && card.dataset.cleanup !== 'true')
      || (duplicates && card.dataset.duplicate !== 'true');
  }});
  const field = sort === 'quality' ? 'quality' : sort;
  cards.sort((a, b) => Number(b.dataset[field]) - Number(a.dataset[field]));
  cards.forEach(card => gallery.appendChild(card));
}}
controls.forEach(control => control.addEventListener('change', refresh));
refresh();
</script>
</body>
</html>
"""


def _summary_item(label: str, value: object, suffix: str = "") -> str:
    return (
        f"<div><span>{html.escape(label)}</span>"
        f"<strong>{html.escape(str(value if value is not None else 0))}"
        f"{html.escape(suffix)}</strong></div>"
    )
