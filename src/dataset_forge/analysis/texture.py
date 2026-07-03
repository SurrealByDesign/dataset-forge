"""Read-only texture normalization evaluation and reporting."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from dataset_forge.analysis.metrics import extract_image_metrics
from dataset_forge.image_primitives import (
    gaussian_blur,
    load_rgb_thumbnail,
    rgb_to_gray_float32,
)
from dataset_forge.decisions import EngineDecision, evaluate_decision
from dataset_forge.discovery import discover_images
from dataset_forge.evidence import Evidence, ImageEvidence, write_evidence
from dataset_forge.recommendations.engine import recommend_evidence

_RULES_PATH = Path(__file__).parent.parent / "config" / "cleanup_rules.json"


def _load_rules() -> dict:
    try:
        return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

ANALYSIS_MAX_SIZE = 512
RECOMMENDATIONS = (
    "KEEP",
    "TEXTURE_NORMALIZE_LIGHT",
    "TEXTURE_NORMALIZE_MEDIUM",
    "MANUAL_REVIEW",
)
PLACEHOLDER_IMAGE = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http%3A%2F%2Fwww.w3.org%2Fsvg' width='256' height='256'%3E"
    "%3Crect width='100%25' height='100%25' fill='%23131820'/%3E"
    "%3Ctext x='50%25' y='50%25' fill='%239aa4b2' text-anchor='middle'"
    " dominant-baseline='middle' font-family='sans-serif'%3E"
    "Preview unavailable%3C/text%3E%3C/svg%3E"
)


@dataclass
class TextureImageResult:
    filename: str
    original_path: str
    status: str
    error: str = ""
    microtexture_density_score: float = 0.0
    local_contrast_score: float = 0.0
    edge_sharpness_score: float = 0.0
    highlight_speck_score: float = 0.0
    texture_consistency_score: float = 0.0
    watercolor_smoothness_score: float = 0.0
    pencil_grain_score: float = 0.0
    representative_score: float = 0.0
    cleanliness_score: float = 0.0
    texture_delta_from_average: float = 0.0
    recommendation: str = ""
    explanation: str = ""
    engine_recommendation: str = ""
    engine_confidence: int = 0
    engine_deciding_factor: str = ""
    engine_explanation: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TextureReportSummary:
    total_images: int
    analyzed_images: int
    error_images: int
    average_microtexture_density: float
    microtexture_standard_deviation: float
    above_average_outliers: list[str]
    below_average_outliers: list[str]
    most_over_textured: str
    most_under_textured: str
    most_representative: str
    cleanest: str
    recommendation_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_texture(path: Path) -> TextureImageResult:
    """Calculate texture-normalization signals without modifying the image."""
    resolved = path.expanduser().resolve()
    try:
        rgb = load_rgb_thumbnail(resolved, ANALYSIS_MAX_SIZE)
    except (OSError, ValueError) as exc:
        return TextureImageResult(
            filename=resolved.name,
            original_path=str(resolved),
            status="error",
            error=str(exc),
        )

    gray = rgb_to_gray_float32(rgb)
    if min(gray.shape) < 3:
        return TextureImageResult(
            filename=resolved.name,
            original_path=str(resolved),
            status="error",
            error="Image is too small for texture analysis.",
        )

    blur_small = gaussian_blur(gray, 1.0)
    blur_large = gaussian_blur(gray, 2.4)
    high_frequency = np.abs(gray - blur_small)
    band_pass = np.abs(blur_small - blur_large)
    laplacian = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)

    microtexture = _saturating(float(np.mean(high_frequency)), 12.0)
    local_contrast = _local_contrast(gray)
    edge_sharpness = _saturating(float(np.var(laplacian)), 1800.0)
    highlight_speck = _highlight_speck(gray)
    texture_consistency = _texture_consistency(high_frequency)
    watercolor_smoothness = _score(
        100.0
        - 0.62 * microtexture
        - 0.23 * edge_sharpness
        - 0.15 * highlight_speck
    )
    pencil_grain = _score(
        0.58 * _saturating(float(np.mean(band_pass)), 6.0)
        + 0.42 * texture_consistency
    )

    return TextureImageResult(
        filename=resolved.name,
        original_path=str(resolved),
        status="analyzed",
        microtexture_density_score=microtexture,
        local_contrast_score=local_contrast,
        edge_sharpness_score=edge_sharpness,
        highlight_speck_score=highlight_speck,
        texture_consistency_score=texture_consistency,
        watercolor_smoothness_score=watercolor_smoothness,
        pencil_grain_score=pencil_grain,
    )


def generate_texture_report(
    input_path: Path,
    output_path: Path,
    *,
    recursive: bool = False,
    limit: int | None = None,
    thumbnail_size: int = 256,
    create_thumbnails: bool = True,
) -> TextureReportSummary:
    """Evaluate a folder and write JSON, CSV, and an offline HTML report."""
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not input_path.is_dir():
        raise ValueError(f"Input folder does not exist: {input_path}")
    if thumbnail_size < 32:
        raise ValueError("Thumbnail size must be at least 32 pixels.")
    if limit is not None and limit < 1:
        raise ValueError("Limit must be at least 1.")

    discovery = discover_images(
        input_path,
        recursive=recursive,
        limit=limit,
        excluded_root=output_path,
    )
    if not discovery.images:
        raise ValueError(f"No supported images found under: {input_path}")

    results = [evaluate_texture(path) for path in discovery.images]
    summary = _finalize_results(results)
    output_path.mkdir(parents=True, exist_ok=True)
    _write_json(output_path / "texture_report.json", results, summary)
    write_evidence(
        output_path / "evidence.json",
        _texture_evidence(
            results,
            summary.average_microtexture_density,
            summary.microtexture_standard_deviation,
        ),
    )
    _write_csv(output_path / "texture_report.csv", results)
    _write_html(
        output_path / "texture_report.html",
        results,
        summary,
        thumbnail_size=thumbnail_size,
        create_thumbnails=create_thumbnails,
    )
    return summary


def _finalize_results(
    results: list[TextureImageResult],
) -> TextureReportSummary:
    analyzed = [item for item in results if item.status == "analyzed"]
    if not analyzed:
        evidence = _texture_evidence(results, 0.0, 0.0)
        decisions = {
            item.filename: item for item in recommend_evidence(evidence)
        }
        for item in results:
            item.recommendation = decisions[item.filename].action
            item.explanation = decisions[item.filename].explanation
        return TextureReportSummary(
            total_images=len(results),
            analyzed_images=0,
            error_images=len(results),
            average_microtexture_density=0.0,
            microtexture_standard_deviation=0.0,
            above_average_outliers=[],
            below_average_outliers=[],
            most_over_textured="",
            most_under_textured="",
            most_representative="",
            cleanest="",
            recommendation_counts={
                name: sum(result.recommendation == name for result in results)
                for name in RECOMMENDATIONS
            },
        )

    densities = np.array(
        [item.microtexture_density_score for item in analyzed],
        dtype=np.float32,
    )
    average = float(np.mean(densities))
    deviation = float(np.std(densities))
    outlier_distance = max(8.0, deviation)

    metric_names = (
        "microtexture_density_score",
        "local_contrast_score",
        "edge_sharpness_score",
        "highlight_speck_score",
        "texture_consistency_score",
    )
    means = {
        name: float(np.mean([getattr(item, name) for item in analyzed]))
        for name in metric_names
    }
    deviations = {
        name: max(5.0, float(np.std([getattr(item, name) for item in analyzed])))
        for name in metric_names
    }

    for item in analyzed:
        item.texture_delta_from_average = _signed_score(
            item.microtexture_density_score - average
        )
        distance = math.sqrt(
            sum(
                ((getattr(item, name) - means[name]) / deviations[name]) ** 2
                for name in metric_names
            )
            / len(metric_names)
        )
        item.representative_score = _score(100.0 * math.exp(-distance))
        burden = (
            0.52 * item.microtexture_density_score
            + 0.30 * item.highlight_speck_score
            + 0.18
            * max(0.0, item.edge_sharpness_score - item.local_contrast_score)
        )
        item.cleanliness_score = _score(100.0 - burden)
    evidence = _texture_evidence(results, average, deviation)
    decisions = {
        item.filename: item for item in recommend_evidence(evidence)
    }
    rules = _load_rules()
    for item in results:
        decision = decisions[item.filename]
        item.recommendation = decision.action
        item.explanation = decision.explanation
        if item.status == "analyzed":
            eng: EngineDecision = evaluate_decision(
                microtexture=item.microtexture_density_score,
                highlight_speck=item.highlight_speck_score,
                watercolor_smoothness=item.watercolor_smoothness_score,
                texture_consistency=item.texture_consistency_score,
                dataset_average=average,
                dataset_stddev=max(1.0, deviation),
                rules=rules,
            )
            item.engine_recommendation = eng.recommendation
            item.engine_confidence = eng.confidence
            item.engine_deciding_factor = eng.deciding_factor
            item.engine_explanation = eng.human_readable

    above = sorted(
        (
            item
            for item in analyzed
            if item.microtexture_density_score > average + outlier_distance
        ),
        key=lambda item: (-item.microtexture_density_score, item.filename.casefold()),
    )
    below = sorted(
        (
            item
            for item in analyzed
            if item.microtexture_density_score < average - outlier_distance
        ),
        key=lambda item: (item.microtexture_density_score, item.filename.casefold()),
    )
    over = max(
        analyzed,
        key=lambda item: (item.microtexture_density_score, item.filename.casefold()),
    )
    under = min(
        analyzed,
        key=lambda item: (item.microtexture_density_score, item.filename.casefold()),
    )
    representative = max(
        analyzed,
        key=lambda item: (item.representative_score, item.filename.casefold()),
    )
    cleanest = max(
        analyzed,
        key=lambda item: (item.cleanliness_score, item.filename.casefold()),
    )
    counts = {
        recommendation: sum(
            item.recommendation == recommendation for item in results
        )
        for recommendation in RECOMMENDATIONS
    }
    return TextureReportSummary(
        total_images=len(results),
        analyzed_images=len(analyzed),
        error_images=len(results) - len(analyzed),
        average_microtexture_density=_score(average),
        microtexture_standard_deviation=_score(deviation),
        above_average_outliers=[item.filename for item in above],
        below_average_outliers=[item.filename for item in below],
        most_over_textured=over.filename,
        most_under_textured=under.filename,
        most_representative=representative.filename,
        cleanest=cleanest.filename,
        recommendation_counts=counts,
    )


def _texture_evidence(
    results: list[TextureImageResult],
    average: float,
    deviation: float,
) -> Evidence:
    return Evidence(
        images=[
            ImageEvidence(
                image_id=hashlib.sha256(
                    item.original_path.encode("utf-8")
                ).hexdigest()[:16],
                filename=item.filename,
                original_path=item.original_path,
                status=item.status,
                error=item.error,
                texture_metrics={
                    name: getattr(item, name)
                    for name in (
                        "microtexture_density_score",
                        "local_contrast_score",
                        "edge_sharpness_score",
                        "highlight_speck_score",
                        "texture_consistency_score",
                        "watercolor_smoothness_score",
                        "pencil_grain_score",
                    )
                },
                dataset_relative_metrics={
                    "texture_delta_from_average": item.texture_delta_from_average,
                    "representative_score": item.representative_score,
                    "cleanliness_score": item.cleanliness_score,
                },
            )
            for item in results
        ],
        dataset_metrics={
            "average_microtexture_density": _score(average),
            "microtexture_standard_deviation": _score(deviation),
        },
    )


def _local_contrast(gray: np.ndarray) -> float:
    height, width = gray.shape
    values: list[float] = []
    block = max(8, min(height, width) // 16)
    for top in range(0, height, block):
        for left in range(0, width, block):
            sample = gray[top : top + block, left : left + block]
            if sample.size > 1:
                values.append(float(np.std(sample)))
    return _saturating(float(np.mean(values)) if values else 0.0, 38.0)


def _highlight_speck(gray: np.ndarray) -> float:
    local_mean = cv2.GaussianBlur(gray, (0, 0), 1.2)
    isolated = (gray >= 242.0) & ((gray - local_mean) >= 28.0)
    ratio = float(np.mean(isolated))
    return _score(100.0 * (1.0 - math.exp(-ratio / 0.004)))


def _texture_consistency(high_frequency: np.ndarray) -> float:
    height, width = high_frequency.shape
    block = max(8, min(height, width) // 16)
    block_means: list[float] = []
    for top in range(0, height, block):
        for left in range(0, width, block):
            sample = high_frequency[top : top + block, left : left + block]
            if sample.size:
                block_means.append(float(np.mean(sample)))
    if not block_means:
        return 0.0
    mean = float(np.mean(block_means))
    if mean < 0.25:
        return 100.0
    coefficient = float(np.std(block_means)) / mean
    return _score(100.0 * math.exp(-coefficient))


def _write_json(
    path: Path,
    results: list[TextureImageResult],
    summary: TextureReportSummary,
) -> None:
    payload = {
        "version": 1,
        "analysis_only": True,
        "summary": summary.to_dict(),
        "images": [item.to_dict() for item in results],
        "evidence": _texture_evidence(
            results,
            summary.average_microtexture_density,
            summary.microtexture_standard_deviation,
        ).to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, results: list[TextureImageResult]) -> None:
    fields = list(TextureImageResult.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(item.to_dict() for item in results)


def _write_html(
    path: Path,
    results: list[TextureImageResult],
    summary: TextureReportSummary,
    *,
    thumbnail_size: int,
    create_thumbnails: bool,
) -> None:
    thumbnail_dir = path.parent / "texture_thumbnails"
    if create_thumbnails:
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
    cards = [
        _render_card(
            item,
            _image_source(
                item,
                index,
                thumbnail_dir,
                path.parent,
                thumbnail_size,
                create_thumbnails,
            ),
        )
        for index, item in enumerate(results)
    ]
    path.write_text(_render_page(cards, summary), encoding="utf-8")


def _image_source(
    item: TextureImageResult,
    index: int,
    thumbnail_dir: Path,
    output_path: Path,
    size: int,
    create_thumbnails: bool,
) -> str:
    source = Path(item.original_path)
    if not create_thumbnails:
        try:
            return source.as_uri()
        except ValueError:
            return PLACEHOLDER_IMAGE
    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    destination = thumbnail_dir / f"{index:06d}-{digest}.jpg"
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            image.save(destination, "JPEG", quality=82, optimize=True)
    except (OSError, ValueError):
        return PLACEHOLDER_IMAGE
    return destination.relative_to(output_path).as_posix()


def _render_card(item: TextureImageResult, image_source: str) -> str:
    return f"""
<article class="card" data-micro="{item.microtexture_density_score}"
 data-contrast="{item.local_contrast_score}" data-speck="{item.highlight_speck_score}"
 data-representative="{item.representative_score}" data-clean="{item.cleanliness_score}"
 data-engineconf="{item.engine_confidence}">
 <img loading="lazy" src="{html.escape(image_source, quote=True)}"
  alt="Preview of {html.escape(item.filename, quote=True)}">
 <div class="body"><div class="heading"><h2>{html.escape(item.filename)}</h2>
 <span class="badge">{html.escape(item.recommendation)}</span>
 {f'<span class="badge engine">{html.escape(item.engine_recommendation)} ({item.engine_confidence}%)</span>' if item.engine_recommendation else ''}
 </div>
 <div class="scores">
  {_score_html("Microtexture", item.microtexture_density_score)}
  {_score_html("Local contrast", item.local_contrast_score)}
  {_score_html("Edge sharpness", item.edge_sharpness_score)}
  {_score_html("Highlight speck", item.highlight_speck_score)}
  {_score_html("Consistency", item.texture_consistency_score)}
  {_score_html("Watercolor smoothness", item.watercolor_smoothness_score)}
  {_score_html("Pencil grain", item.pencil_grain_score)}
 </div>
 <p>{html.escape(item.explanation)}</p>
 {f'<p class="engine-note"><strong>Engine:</strong> {html.escape(item.engine_deciding_factor)} — {html.escape(item.engine_explanation)}</p>' if item.engine_explanation else ''}
 </div>
</article>"""


def _render_page(cards: list[str], summary: TextureReportSummary) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dataset Forge Texture Report</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui,sans-serif; }}
* {{ box-sizing:border-box }} body {{ margin:0;background:#0f141b;color:#eef2f7 }}
header {{ position:sticky;top:0;z-index:2;padding:20px;background:#171d28ee;backdrop-filter:blur(12px) }}
h1 {{ margin:0 0 12px;font-size:1.55rem }} .summary,.controls,.scores {{ display:flex;flex-wrap:wrap;gap:9px }}
.summary div,.scores div {{ padding:9px 11px;background:#222b38;border-radius:8px }}
.summary span,.scores span {{ display:block;color:#aeb8c7;font-size:.76rem }}
.summary strong {{ font-size:1.12rem }} .controls {{ margin-top:13px }}
select {{ padding:8px 10px;background:#222b38;color:#eef2f7;border:1px solid #3a4659;border-radius:7px }}
main {{ display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;padding:20px }}
.card {{ overflow:hidden;background:#1a212c;border:1px solid #303b4b;border-radius:12px }}
.card img {{ width:100%;height:240px;display:block;object-fit:contain;background:#0b1016 }}
.body {{ padding:14px }} .heading {{ display:flex;gap:10px;justify-content:space-between;align-items:start }}
h2 {{ margin:0;font-size:1rem;overflow-wrap:anywhere }} .badge {{ font-size:.68rem;font-weight:700;color:#cce8ff }}
.badge.engine {{ color:#b5e8c8 }} .engine-note {{ color:#9eb8a0;font-size:.82rem;line-height:1.4;margin-top:6px }}
.scores {{ margin:12px 0 }} .scores div {{ flex:1 1 100px }} .scores strong {{ font-size:1rem }}
p {{ color:#cbd3df;font-size:.88rem;line-height:1.4 }}
</style></head><body><header><h1>Texture Normalization Evaluator</h1>
<section class="summary">
{_summary_html("Analyzed", summary.analyzed_images)}
{_summary_html("Average microtexture", summary.average_microtexture_density)}
{_summary_html("Most over-textured", summary.most_over_textured)}
{_summary_html("Most under-textured", summary.most_under_textured)}
{_summary_html("Most representative", summary.most_representative)}
{_summary_html("Cleanest", summary.cleanest)}
</section><section class="controls"><select id="sort">
<option value="micro">Highest microtexture</option>
<option value="contrast">Highest local contrast</option>
<option value="speck">Highest highlight speck</option>
<option value="representative">Most representative</option>
<option value="clean">Cleanest</option>
<option value="engineconf">Highest engine confidence</option>
</select></section></header><main id="gallery">{''.join(cards)}</main>
<script>
const gallery=document.getElementById('gallery'),sort=document.getElementById('sort');
function refresh(){{const cards=[...gallery.querySelectorAll('.card')];
cards.sort((a,b)=>Number(b.dataset[sort.value])-Number(a.dataset[sort.value]));
cards.forEach(card=>gallery.appendChild(card));}}
sort.addEventListener('change',refresh);refresh();
</script></body></html>"""


def _score_html(label: str, value: float) -> str:
    return f"<div><span>{html.escape(label)}</span><strong>{value:.1f}</strong></div>"


def _summary_html(label: str, value: object) -> str:
    return (
        f"<div><span>{html.escape(label)}</span>"
        f"<strong>{html.escape(str(value))}</strong></div>"
    )


def _saturating(value: float, scale: float) -> float:
    return _score(100.0 * (1.0 - math.exp(-max(0.0, value) / scale)))


def _score(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


def _signed_score(value: float) -> float:
    return round(min(100.0, max(-100.0, value)), 2)


__all__ = [
    "TextureImageResult",
    "TextureReportSummary",
    "evaluate_texture",
    "extract_image_metrics",
    "generate_texture_report",
]
