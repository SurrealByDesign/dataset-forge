"""Report writer for Dataset Forge Inspect.

Consumes list[Finding] and DatasetContext, produces:
  - inspection_report.json
  - inspection_report.txt

Does not run analysis, make decisions, invoke cleanup, or open image files.
Output is deterministic: findings are sorted by image path then analyzer id.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity
from dataset_forge.post_inspection import build_post_inspection_sections

REPORT_SCHEMA = "dataset-forge/inspection/v1"

# Severities shown in summary counts, in display order.
_COUNTED_SEVERITIES = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_local_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sort_key(f: Finding) -> tuple[str, str]:
    return (str(f.image_path), f.analyzer)


def _severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {s.name: 0 for s in _COUNTED_SEVERITIES}
    counts["NONE"] = 0
    for f in findings:
        counts[f.severity.name] = counts.get(f.severity.name, 0) + 1
    return counts


def _images_with_findings(findings: list[Finding]) -> set[str]:
    return {str(f.image_path) for f in findings}


def _group_by_image(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Return findings grouped by image path, sorted deterministically."""
    groups: dict[str, list[Finding]] = {}
    for f in sorted(findings, key=_sort_key):
        key = str(f.image_path)
        groups.setdefault(key, []).append(f)
    return dict(sorted(groups.items()))


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def _build_json(
    findings: list[Finding],
    context: DatasetContext,
    dataset_path: Path | str,
    generated_at: str,
) -> dict[str, Any]:
    affected = _images_with_findings(findings)
    total = context.image_count
    clean_count = total - len(affected)
    dataset_summary, review_queue = build_post_inspection_sections(findings, context)

    return {
        "schema": REPORT_SCHEMA,
        "generated_at": generated_at,
        "dataset_path": str(dataset_path),
        "context": {
            "total_images": total,
            "analyzed_images": context.analyzed_count,
            "error_images": context.error_count,
            "resolution_stats": context.resolution_stats.to_dict(),
            "aspect_ratio_stats": context.aspect_ratio_stats.to_dict(),
            "texture_distributions": context.texture_distributions.to_dict(),
            "frequency_distributions": context.frequency_distributions.to_dict(),
            "exact_duplicate_count": context.exact_duplicate_count,
            "duplicate_groups": [
                [str(p) for p in group] for group in context.duplicate_groups
            ],
            "analyzer_versions": dict(context.analyzer_versions),
        },
        "findings": [
            f.to_dict() for f in sorted(findings, key=_sort_key)
        ],
        "summary": {
            "total_findings": len(findings),
            "images_with_findings": len(affected),
            "images_clean": clean_count,
            "severity_counts": _severity_counts(findings),
        },
        "dataset_summary": dataset_summary.to_dict(),
        "review_queue": review_queue.to_dict(),
    }


def write_json_report(
    findings: list[Finding],
    context: DatasetContext,
    output_path: Path,
    dataset_path: Path | str = "",
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write inspection_report.json and return the report dict."""
    ts = generated_at or _now_utc()
    report = _build_json(findings, context, dataset_path, ts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


# ---------------------------------------------------------------------------
# TXT report
# ---------------------------------------------------------------------------

def _fp_percent(rate: float) -> str:
    return f"~{round(rate * 100)}%"


def _evidence_line(evidence: dict[str, Any]) -> str:
    """Render evidence dict as a compact key=value string, skip internal flags."""
    _SKIP = {"calibrated"}
    parts = [
        f"{k}={v}" for k, v in evidence.items()
        if k not in _SKIP and not isinstance(v, dict)
    ]
    return "  Evidence: " + ", ".join(parts) if parts else ""


def _score_table_rows(
    image_scores: dict[str, dict],
    findings: list[Finding],
    context: DatasetContext,
) -> list[str]:
    """Build the full per-image texture score table, sorted by microtexture desc.

    Shows every analyzed image — not just those with findings. This lets the
    reviewer see the full distribution and judge the flagging threshold visually.
    """
    affected = _images_with_findings(findings)
    dist = context.texture_distributions

    # Build one row per image
    rows: list[tuple[float, str]] = []  # (sort_key, rendered_line)
    for path_str, scores in image_scores.items():
        name = Path(path_str).name
        if "error" in scores:
            rows.append((
                -1.0,
                f"  [ERROR ] {name:<40}  error: {scores['error']}"
            ))
            continue

        micro = scores.get("microtexture_density", 0.0)
        smooth = scores.get("watercolor_smoothness", 0.0)
        speck = scores.get("highlight_speck", 0.0)

        if dist.stddev > 0:
            z = (micro - dist.mean) / dist.stddev
            z_str = f"{z:+.2f}"
        else:
            z = 0.0
            z_str = "  n/a"

        tag = "[FINDING]" if path_str in affected else "[clean  ]"
        line = (
            f"  {tag} {name:<40} "
            f"micro={micro:5.1f}  z={z_str:>6}  "
            f"smooth={smooth:5.1f}  speck={speck:5.1f}"
        )
        rows.append((micro, line))

    rows.sort(key=lambda r: r[0], reverse=True)
    return [r[1] for r in rows]


def _build_txt(
    findings: list[Finding],
    context: DatasetContext,
    dataset_path: Path | str,
    generated_at_display: str,
    image_scores: dict[str, dict] | None = None,
) -> str:
    total = context.image_count
    affected = _images_with_findings(findings)
    clean_count = total - len(affected)
    sev_counts = _severity_counts(findings)
    groups = _group_by_image(findings)
    dataset_summary, review_queue = build_post_inspection_sections(findings, context)

    lines: list[str] = []

    # Header
    lines += [
        "Dataset Forge Inspection Report",
        "================================",
        f"Generated:  {generated_at_display}",
        f"Dataset:    {dataset_path}",
        f"Images:     {context.analyzed_count} analyzed, {context.error_count} errors",
        "",
    ]

    # Findings by image
    if groups:
        lines += ["FINDINGS BY IMAGE", "-----------------", ""]
        for image_path, img_findings in groups.items():
            lines.append(Path(image_path).name)
            for f in img_findings:
                fp_pct = _fp_percent(f.false_positive_rate)
                lines.append(
                    f"  [{f.severity.name}] {f.category} — "
                    f"confidence {f.confidence:.2f} (FP rate {fp_pct})"
                )
                lines.append(f"  Benchmark: {f.benchmark_version}")
                ev_line = _evidence_line(f.evidence)
                if ev_line:
                    lines.append(ev_line)
                # Wrap explanation at ~72 chars after the "  Why: " prefix
                lines += _wrap_field("Why", f.explanation)
                lines += _wrap_field("Action", f.recommendation)
            lines.append("")
    else:
        lines += ["FINDINGS BY IMAGE", "-----------------", ""]
        lines += ["  No findings. All images are within normal parameters.", ""]

    # Clean images
    lines += [
        "CLEAN IMAGES (no findings)",
        "--------------------------",
    ]
    if clean_count > 0:
        lines += [
            f"{clean_count} image{'s' if clean_count != 1 else ''} produced no "
            "findings at any severity level.",
            (
                "These images emitted no current review findings. This does "
                "not guarantee they are artifact-free or training-ready."
            ),
        ]
    else:
        lines.append("All images produced at least one finding.")
    lines.append("")

    # Full dataset score table (validation aid)
    if image_scores:
        dist = context.texture_distributions
        lines += [
            "DATASET TEXTURE SCORES (all images, sorted by microtexture density)",
            "--------------------------------------------------------------------",
            f"  Dataset baseline:  mean={dist.mean:.1f}  stddev={dist.stddev:.1f}"
            f"  p10={dist.p10:.1f}  p90={dist.p90:.1f}",
            f"  {'Tag':<9}  {'Filename':<40}  {'micro':>5}  {'z':>6}  "
            f"{'smooth':>6}  {'speck':>5}",
            "",
        ]
        lines += _score_table_rows(image_scores, findings, context)
        lines.append("")

    # Additive post-inspection sections
    lines += [
        "DATASET SUMMARY",
        "---------------",
        f"Images with findings:       {dataset_summary.images_with_findings}",
        f"Images without findings:    {dataset_summary.images_without_findings}",
        f"Analyzer errors:            {dataset_summary.analyzer_error_count}",
        f"Calibrated findings:        {dataset_summary.calibrated_finding_count}",
        f"Uncalibrated findings:      {dataset_summary.uncalibrated_finding_count}",
    ]
    if dataset_summary.dominant_artifact_families:
        lines.append(
            "Dominant artifact families: "
            + ", ".join(dataset_summary.dominant_artifact_families)
        )
    else:
        lines.append("Dominant artifact families: none")
    lines.append("")

    lines += [
        "REVIEW QUEUE",
        "------------",
        "Review Queue is advisory only. Dataset Forge does not delete, modify,",
        "repair, reject, regenerate, or export images.",
        f"No attention needed: {review_queue.outcomes['no_attention_needed']}",
        f"Review recommended:  {review_queue.outcomes['review_recommended']}",
        f"Priority review:     {review_queue.outcomes['priority_review']}",
    ]
    priority_items = [
        item for item in review_queue.items
        if item.outcome == "priority_review"
    ]
    review_items = [
        item for item in review_queue.items
        if item.outcome == "review_recommended"
    ]
    display_items = priority_items + review_items
    if display_items:
        lines.append("")
        lines.append("Images needing attention:")
        for item in display_items:
            lines.append(
                f"  [{item.priority.upper()}] {Path(item.image_path).name} "
                f"- {item.finding_count} finding"
                f"{'s' if item.finding_count != 1 else ''}; "
                f"strongest={item.strongest_severity}"
            )
    lines.append("")

    # Summary
    lines += ["SUMMARY", "-------"]
    sev_parts = ", ".join(
        f"{sev_counts[s.name]} {s.name}"
        for s in _COUNTED_SEVERITIES
        if sev_counts.get(s.name, 0) > 0
    ) or "none"
    lines.append(f"Findings:         {len(findings)} total ({sev_parts})")
    lines.append(f"Images affected:  {len(affected)} / {total}")
    lines.append(f"Images clean:     {clean_count} / {total}")
    lines.append("")
    lines.append(
        "Recommendation: Review findings before making any dataset changes."
    )
    lines.append(
        "                Dataset Forge inspect is read-only and does not modify images."
    )

    return "\n".join(lines) + "\n"


def _wrap_field(label: str, text: str, width: int = 72) -> list[str]:
    """Render a labelled block, wrapping long text at word boundaries."""
    prefix = f"  {label}: "
    continuation = " " * len(prefix)
    words = text.split()
    result: list[str] = []
    current = prefix
    for word in words:
        if current == prefix:
            current += word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            result.append(current)
            current = continuation + word
    if current not in (prefix, continuation):
        result.append(current)
    return result


def write_txt_report(
    findings: list[Finding],
    context: DatasetContext,
    output_path: Path,
    dataset_path: Path | str = "",
    *,
    generated_at_display: str | None = None,
    image_scores: dict[str, dict] | None = None,
) -> str:
    """Write inspection_report.txt and return the report text."""
    ts = generated_at_display or _now_local_display()
    text = _build_txt(findings, context, dataset_path, ts, image_scores=image_scores)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Convenience: write both at once
# ---------------------------------------------------------------------------

def write_inspection_report(
    findings: list[Finding],
    context: DatasetContext,
    output_dir: Path,
    dataset_path: Path | str = "",
    *,
    image_scores: dict[str, dict] | None = None,
) -> tuple[Path, Path]:
    """Write both report files to output_dir. Returns (json_path, txt_path)."""
    ts_utc = _now_utc()
    ts_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    json_path = output_dir / "inspection_report.json"
    txt_path = output_dir / "inspection_report.txt"

    write_json_report(findings, context, json_path, dataset_path, generated_at=ts_utc)
    write_txt_report(
        findings, context, txt_path, dataset_path,
        generated_at_display=ts_local,
        image_scores=image_scores,
    )

    return json_path, txt_path
