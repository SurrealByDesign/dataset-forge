"""Dataset Health Report — primary dashboard for LoRA dataset readiness.

Answers: "If I trained a LoRA on this dataset today, how confident should I
feel that the dataset itself is well prepared?"

This module reads from existing ``generate_texture_report()`` outputs only.
It never re-runs analysis, never opens source images, and never touches any
existing report or cleanup output.
"""

from __future__ import annotations

import html
import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataset_forge.analysis.texture import TextureImageResult, TextureReportSummary

_DISCLAIMER = (
    "This score is an estimate intended to guide preparation decisions. "
    "It does not predict actual model performance."
)
_RULES_PATH = Path(__file__).parent.parent / "config" / "cleanup_rules.json"

_FUTURE_SECTIONS: dict[str, None] = {
    "ai_conservator_statistics": None,
    "caption_quality": None,
    "prompt_consistency": None,
    "lora_validation_results": None,
    "training_history": None,
    "style_clustering": None,
    "outlier_detection": None,
}


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ConsistencyScores:
    texture_consistency: float
    resolution_consistency: float | None
    aspect_ratio_consistency: float | None
    style_consistency: float
    cleanup_consistency: float
    overall_dataset_consistency: float


@dataclass
class LoRAReadiness:
    score: int
    disclaimer: str
    penalty_breakdown: dict[str, float]


@dataclass
class DatasetHealthReport:
    version: int
    generated_at: str

    # Section 1
    total_images: int
    analyzed_images: int
    error_images: int
    skipped_images: int
    dataset_health_score: float
    lora_readiness_score: int
    lora_readiness_disclaimer: str
    headline: str
    recommendations: list[str]

    # Section 2
    leave_alone_count: int
    leave_alone_pct: float
    deterministic_only_count: int
    deterministic_only_pct: float
    ai_conservation_count: int
    ai_conservation_pct: float
    manual_review_count: int
    manual_review_pct: float
    intervention_ratio: float
    high_confidence_decisions: int
    low_confidence_decisions: int

    # Section 3 (cleanup)
    cleanup_status: str  # "not_applied" | "applied"
    projected_images_to_clean: int
    projected_ai_candidates: int
    projected_manual_review: int
    cleanup_applied_details: dict[str, Any]  # empty dict when not applied

    # Section 4
    texture_stats: dict[str, Any]
    resolution_stats: dict[str, Any] | None
    duplicate_stats: dict[str, int]
    future_data_fields: dict[str, None]

    # Section 5
    consistency_scores: ConsistencyScores

    # Section 6
    lora_readiness: LoRAReadiness

    # Section 8
    export_guidance: dict[str, Any]

    # Section 9
    future_sections: dict[str, None]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Flatten the top-level layout to match the JSON schema
        return {
            "version": d["version"],
            "generated_at": d["generated_at"],
            "executive_summary": {
                "total_images": d["total_images"],
                "analyzed_images": d["analyzed_images"],
                "error_images": d["error_images"],
                "skipped_images": d["skipped_images"],
                "dataset_health_score": d["dataset_health_score"],
                "lora_readiness_score": d["lora_readiness_score"],
                "lora_readiness_disclaimer": d["lora_readiness_disclaimer"],
                "headline": d["headline"],
                "recommendations": d["recommendations"],
            },
            "decision_engine_summary": {
                "leave_alone_count": d["leave_alone_count"],
                "leave_alone_pct": d["leave_alone_pct"],
                "deterministic_only_count": d["deterministic_only_count"],
                "deterministic_only_pct": d["deterministic_only_pct"],
                "ai_conservation_count": d["ai_conservation_count"],
                "ai_conservation_pct": d["ai_conservation_pct"],
                "manual_review_count": d["manual_review_count"],
                "manual_review_pct": d["manual_review_pct"],
                "intervention_ratio": d["intervention_ratio"],
                "high_confidence_decisions": d["high_confidence_decisions"],
                "low_confidence_decisions": d["low_confidence_decisions"],
            },
            "cleanup_summary": {
                "status": d["cleanup_status"],
                "projected_images_to_clean": d["projected_images_to_clean"],
                "projected_ai_candidates": d["projected_ai_candidates"],
                "projected_manual_review": d["projected_manual_review"],
                **(d["cleanup_applied_details"] if d["cleanup_status"] == "applied" else {}),
            },
            "dataset_statistics": {
                "texture": d["texture_stats"],
                "resolution": d["resolution_stats"],
                "duplicates": d["duplicate_stats"],
                "future": d["future_data_fields"],
            },
            "consistency_scores": d["consistency_scores"],
            "lora_readiness": d["lora_readiness"],
            "export_guidance": d["export_guidance"],
            "future_sections": d["future_sections"],
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_health_report(
    results: list[TextureImageResult],
    summary: TextureReportSummary,
    output_path: Path,
    *,
    cleanup_execution_report: dict[str, Any] | None = None,
    duplicate_count: int = 0,
    near_duplicate_count: int = 0,
    rules: dict[str, Any] | None = None,
) -> DatasetHealthReport:
    """Build and write the Dataset Health Report.

    Args:
        results: Per-image results from ``generate_texture_report()``.
        summary: Dataset-level summary from ``generate_texture_report()``.
        output_path: Folder where the three report files are written.
        cleanup_execution_report: Optional dict from a completed cleanup run.
            When ``None`` the Cleanup Summary section is projected only.
        duplicate_count: Exact duplicate image count (from manifest pipeline).
        near_duplicate_count: Near-duplicate pair count.
        rules: Raw dict from ``cleanup_rules.json``.  Defaults apply when None.
    """
    if rules is None:
        rules = _load_rules()

    output_path = output_path.expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    analyzed = [r for r in results if r.status == "analyzed"]
    n_total = len(results)
    n_analyzed = len(analyzed)
    n_errors = n_total - n_analyzed
    n_skipped = 0  # extension point for future exclusion tracking

    # -- Section 2: engine routing counts ----------------------------------
    engine_counts = _count_engine(analyzed)
    la = engine_counts["LEAVE_ALONE"]
    det = engine_counts["DETERMINISTIC_ONLY"]
    ai = engine_counts["AI_CONSERVATION_CANDIDATE"]
    mr = engine_counts["MANUAL_REVIEW"]
    n_eng = n_analyzed or 1  # guard divide-by-zero
    intervention_count = det + ai + mr
    intervention_ratio = round(intervention_count / n_eng, 4)

    high_conf = sum(1 for r in analyzed if r.engine_confidence >= 80)
    low_conf = sum(1 for r in analyzed if r.engine_confidence < 60)

    # -- Section 3: cleanup ------------------------------------------------
    if cleanup_execution_report is not None:
        cleanup_status = "applied"
        cleanup_details = dict(cleanup_execution_report)
    else:
        cleanup_status = "not_applied"
        cleanup_details = {}

    # -- Section 4: statistics ---------------------------------------------
    ref_baseline = float(
        rules.get("decision_engine", {}).get("reference_baseline_microtexture", 26.86)
    )
    texture_stats = _texture_stats(analyzed, summary, ref_baseline)

    # Resolution: not available from texture analysis alone
    resolution_stats: dict[str, Any] | None = None

    duplicate_stats = {
        "exact_duplicate_count": duplicate_count,
        "near_duplicate_count": near_duplicate_count,
    }
    future_data_fields: dict[str, None] = {
        "caption_completeness": None,
        "caption_consistency": None,
        "prompt_consistency": None,
    }

    # -- Section 5: consistency scores -------------------------------------
    consistency = _compute_consistency_scores(
        analyzed, intervention_ratio, n_eng
    )

    # -- Section 6: readiness score ----------------------------------------
    readiness = _compute_readiness_score(
        n_total=n_total,
        n_errors=n_errors,
        manual_review_count=mr,
        ai_conservation_count=ai,
        intervention_ratio=intervention_ratio,
        stddev_microtexture=summary.microtexture_standard_deviation,
        average_microtexture=summary.average_microtexture_density,
        ref_baseline=ref_baseline,
        duplicate_count=duplicate_count,
        near_duplicate_count=near_duplicate_count,
        resolution_consistency=consistency.resolution_consistency,
        aspect_ratio_consistency=consistency.aspect_ratio_consistency,
        overall_consistency=consistency.overall_dataset_consistency,
        mean_confidence=_mean_confidence(analyzed),
    )

    # -- Section 1: health score and headline ------------------------------
    health_score = _compute_health_score(
        n_analyzed=n_analyzed,
        n_errors=n_errors,
        n_total=n_total,
        intervention_ratio=intervention_ratio,
        consistency=consistency,
        readiness_score=readiness.score,
    )

    recommendations = _generate_recommendations(
        n_errors=n_errors,
        leave_alone_count=la,
        deterministic_only_count=det,
        ai_conservation_count=ai,
        manual_review_count=mr,
        intervention_ratio=intervention_ratio,
        duplicate_count=duplicate_count,
        near_duplicate_count=near_duplicate_count,
        overall_consistency=consistency.overall_dataset_consistency,
        resolution_consistency=consistency.resolution_consistency,
        aspect_ratio_consistency=consistency.aspect_ratio_consistency,
        cleanup_status=cleanup_status,
        cleanup_details=cleanup_details,
    )

    headline = _headline(health_score, readiness.score, la, n_analyzed)

    # -- Section 8: export guidance ----------------------------------------
    export_guidance: dict[str, Any] = {
        "leave_unchanged": la,
        "deterministic_cleanup": det,
        "ai_conservation": ai,
        "manual_review": mr,
        "recommended_training_set_size": n_total - duplicate_count,
    }

    report = DatasetHealthReport(
        version=1,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_images=n_total,
        analyzed_images=n_analyzed,
        error_images=n_errors,
        skipped_images=n_skipped,
        dataset_health_score=health_score,
        lora_readiness_score=readiness.score,
        lora_readiness_disclaimer=_DISCLAIMER,
        headline=headline,
        recommendations=recommendations,
        leave_alone_count=la,
        leave_alone_pct=round(la / n_eng * 100, 1),
        deterministic_only_count=det,
        deterministic_only_pct=round(det / n_eng * 100, 1),
        ai_conservation_count=ai,
        ai_conservation_pct=round(ai / n_eng * 100, 1),
        manual_review_count=mr,
        manual_review_pct=round(mr / n_eng * 100, 1),
        intervention_ratio=intervention_ratio,
        high_confidence_decisions=high_conf,
        low_confidence_decisions=low_conf,
        cleanup_status=cleanup_status,
        projected_images_to_clean=det,
        projected_ai_candidates=ai,
        projected_manual_review=mr,
        cleanup_applied_details=cleanup_details,
        texture_stats=texture_stats,
        resolution_stats=resolution_stats,
        duplicate_stats=duplicate_stats,
        future_data_fields=future_data_fields,
        consistency_scores=consistency,
        lora_readiness=readiness,
        export_guidance=export_guidance,
        future_sections=dict(_FUTURE_SECTIONS),
    )

    _write_json(output_path / "dataset_health_report.json", report)
    _write_txt(output_path / "dataset_health_report.txt", report)
    _write_html(output_path / "dataset_health_report.html", report)

    return report


# ---------------------------------------------------------------------------
# Score computations
# ---------------------------------------------------------------------------


def _compute_health_score(
    *,
    n_analyzed: int,
    n_errors: int,
    n_total: int,
    intervention_ratio: float,
    consistency: ConsistencyScores,
    readiness_score: int,
) -> float:
    """Texture-aware dataset health score (0–100).

    Distinct from quality.py's HealthSummary.dataset_health_score, which is
    based on image-level quality weights.  This score reflects texture
    distribution health, intervention load, and consistency — the factors
    visible from texture analysis output alone.
    """
    if n_total == 0:
        return 0.0

    # Error rate penalty
    error_rate = n_errors / n_total
    error_penalty = min(30.0, error_rate * 100.0)

    # Intervention load (high intervention = lower health)
    intervention_penalty = intervention_ratio * 20.0

    # Consistency bonus (0–15)
    consistency_bonus = consistency.overall_dataset_consistency * 0.15

    # Readiness contribution (30% weight)
    readiness_contribution = readiness_score * 0.30

    # Completeness: full credit when all images are analyzed
    completeness = (n_analyzed / n_total) * 35.0

    raw = completeness + readiness_contribution + consistency_bonus - intervention_penalty - error_penalty
    return round(max(0.0, min(100.0, raw)), 1)


def _compute_readiness_score(
    *,
    n_total: int,
    n_errors: int,
    manual_review_count: int,
    ai_conservation_count: int,
    intervention_ratio: float,
    stddev_microtexture: float,
    average_microtexture: float,
    ref_baseline: float,
    duplicate_count: int,
    near_duplicate_count: int,
    resolution_consistency: float | None,
    aspect_ratio_consistency: float | None,
    overall_consistency: float,
    mean_confidence: float,
) -> LoRAReadiness:
    penalties: dict[str, float] = {}

    # Manual review
    mr_pen = min(15.0, manual_review_count * 0.5)
    if mr_pen:
        penalties["manual_review_penalty"] = -mr_pen

    # AI candidates
    ai_pen = min(10.0, ai_conservation_count * 0.3)
    if ai_pen:
        penalties["ai_conservation_penalty"] = -ai_pen

    # Intervention ratio
    if intervention_ratio > 0.80:
        penalties["high_intervention_ratio_penalty"] = -20.0
    elif intervention_ratio > 0.60:
        penalties["high_intervention_ratio_penalty"] = -10.0

    # Texture variance
    if stddev_microtexture > 25:
        penalties["texture_variance_penalty"] = -10.0
    elif stddev_microtexture > 15:
        penalties["texture_variance_penalty"] = -5.0

    # Gap from reference baseline
    gap = average_microtexture - ref_baseline
    if gap > 30:
        penalties["gap_from_reference_penalty"] = -10.0
    elif gap > 20:
        penalties["gap_from_reference_penalty"] = -5.0
    elif gap > 10:
        penalties["gap_from_reference_penalty"] = -5.0

    # Duplicates
    dup_pen = min(15.0, duplicate_count * 3.0)
    if dup_pen:
        penalties["exact_duplicate_penalty"] = -dup_pen
    near_pen = min(8.0, near_duplicate_count * 1.0)
    if near_pen:
        penalties["near_duplicate_penalty"] = -near_pen

    # Resolution / aspect ratio (when available)
    if resolution_consistency is not None and resolution_consistency < 60:
        penalties["resolution_inconsistency_penalty"] = -5.0
    if aspect_ratio_consistency is not None and aspect_ratio_consistency < 60:
        penalties["aspect_ratio_inconsistency_penalty"] = -5.0

    # Error rate
    if n_total > 0:
        error_rate = n_errors / n_total
        if error_rate > 0.15:
            penalties["error_rate_penalty"] = -15.0
        elif error_rate > 0.05:
            penalties["error_rate_penalty"] = -5.0

    # Average microtexture above V1 ceiling
    if average_microtexture > 50:
        penalties["above_v1_ceiling_penalty"] = -8.0

    # Reward: high confidence reduces uncertainty penalty by half
    if mean_confidence > 80 and "manual_review_penalty" in penalties:
        penalties["manual_review_penalty"] = penalties["manual_review_penalty"] * 0.5

    # Reward: high consistency reduces variance penalty by 25%
    if overall_consistency > 80 and "texture_variance_penalty" in penalties:
        penalties["texture_variance_penalty"] = penalties["texture_variance_penalty"] * 0.75

    total_penalty = sum(penalties.values())
    penalties["total_penalty"] = round(total_penalty, 1)
    score = max(0, min(100, round(100 + total_penalty)))

    return LoRAReadiness(
        score=score,
        disclaimer=_DISCLAIMER,
        penalty_breakdown={k: round(v, 1) for k, v in penalties.items()},
    )


def _compute_consistency_scores(
    analyzed: list[TextureImageResult],
    intervention_ratio: float,
    n_eng: int,
) -> ConsistencyScores:
    if not analyzed:
        return ConsistencyScores(
            texture_consistency=0.0,
            resolution_consistency=None,
            aspect_ratio_consistency=None,
            style_consistency=0.0,
            cleanup_consistency=100.0,
            overall_dataset_consistency=0.0,
        )

    # Texture consistency: mean of per-image texture_consistency_score
    tex_cons = round(
        statistics.mean(r.texture_consistency_score for r in analyzed), 1
    )

    # Style consistency: coefficient-of-variation of smoothness + microtexture
    smooth_vals = [r.watercolor_smoothness_score for r in analyzed]
    micro_vals = [r.microtexture_density_score for r in analyzed]
    cv_smooth = _cv(smooth_vals)
    cv_micro = _cv(micro_vals)
    style_cons = round(100.0 * math.exp(-(cv_smooth + cv_micro) / 2), 1)

    # Resolution and aspect ratio: not available from texture analysis alone
    res_cons: float | None = None
    ar_cons: float | None = None

    # Cleanup consistency
    if intervention_ratio >= 1.0:
        cleanup_cons = 0.0
    elif intervention_ratio == 0.0:
        cleanup_cons = 100.0
    else:
        non_la = [r for r in analyzed if r.engine_recommendation != "LEAVE_ALONE"]
        if non_la:
            mean_conf = statistics.mean(r.engine_confidence for r in non_la) / 100.0
        else:
            mean_conf = 1.0
        cleanup_cons = round(100.0 * (1.0 - intervention_ratio) * mean_conf, 1)

    # Overall: weighted mean, redistribute resolution weight to texture if null
    if res_cons is None:
        weights = {"texture": 0.55, "style": 0.25, "cleanup": 0.20}
    else:
        weights = {"texture": 0.35, "style": 0.25, "resolution": 0.20, "cleanup": 0.20}

    overall = 0.0
    overall += weights["texture"] * tex_cons
    overall += weights["style"] * style_cons
    overall += weights.get("cleanup", weights["cleanup"]) * cleanup_cons
    if res_cons is not None:
        overall += weights["resolution"] * res_cons
    overall = round(overall, 1)

    return ConsistencyScores(
        texture_consistency=tex_cons,
        resolution_consistency=res_cons,
        aspect_ratio_consistency=ar_cons,
        style_consistency=style_cons,
        cleanup_consistency=cleanup_cons,
        overall_dataset_consistency=overall,
    )


# ---------------------------------------------------------------------------
# Recommendation generation
# ---------------------------------------------------------------------------


def _generate_recommendations(
    *,
    n_errors: int,
    leave_alone_count: int,
    deterministic_only_count: int,
    ai_conservation_count: int,
    manual_review_count: int,
    intervention_ratio: float,
    duplicate_count: int,
    near_duplicate_count: int,
    overall_consistency: float,
    resolution_consistency: float | None,
    aspect_ratio_consistency: float | None,
    cleanup_status: str,
    cleanup_details: dict[str, Any],
) -> list[str]:
    recs: list[str] = []

    # 1. Positive statements
    if leave_alone_count >= 1:
        pct = round(leave_alone_count / max(1, leave_alone_count + deterministic_only_count + ai_conservation_count + manual_review_count) * 100)
        if leave_alone_count > 0:
            recs.append(
                f"{leave_alone_count} images are already excellent training "
                f"examples and should not be modified."
            )
    if overall_consistency > 80:
        recs.append(
            "The dataset already demonstrates strong stylistic consistency."
        )

    # 2. Critical issues
    if n_errors > 0:
        recs.append(
            f"{n_errors} image{'s' if n_errors != 1 else ''} could not be "
            f"analyzed and should be reviewed manually."
        )
    if duplicate_count > 0:
        recs.append(
            f"Remove {duplicate_count} exact duplicate "
            f"image{'s' if duplicate_count != 1 else ''} before training."
        )
    if near_duplicate_count > 0:
        recs.append(
            f"Review {near_duplicate_count} near-duplicate "
            f"pair{'s' if near_duplicate_count != 1 else ''} — similar images "
            f"reduce training diversity."
        )

    # 3. Deterministic cleanup
    if deterministic_only_count > 0:
        if cleanup_status == "applied":
            cleaned = cleanup_details.get("images_cleaned", deterministic_only_count)
            recs.append(
                f"Deterministic cleanup applied to {cleaned} "
                f"image{'s' if cleaned != 1 else ''}. "
                f"All accepted by preservation checks."
            )
        else:
            recs.append(
                f"Run deterministic cleanup on {deterministic_only_count} "
                f"image{'s' if deterministic_only_count != 1 else ''}. "
                f"Expected benefit: speck removal and mild texture reduction."
            )

    # 4. AI conservation
    if ai_conservation_count > 0:
        recs.append(
            f"{ai_conservation_count} "
            f"image{'s are' if ai_conservation_count != 1 else ' is'} "
            f"AI conservation candidate{'s' if ai_conservation_count != 1 else ''}. "
            f"These have recursive microfacet structure that deterministic "
            f"cleanup cannot resolve."
        )
    elif manual_review_count > 0:
        # Manual review is holding what would be AI candidates
        recs.append(
            "No AI conservation backend is configured. "
            f"{manual_review_count} "
            f"image{'s are' if manual_review_count != 1 else ' is'} held in "
            f"manual review pending AI Conservator availability."
        )

    # 5. Manual review detail
    if manual_review_count > 0 and ai_conservation_count == 0:
        recs.append(
            f"{manual_review_count} "
            f"image{'s' if manual_review_count != 1 else ''} "
            f"with heavy texture complexity are candidates for the AI "
            f"Conservator phase once a backend is configured."
        )

    # 6. Resolution guidance
    if resolution_consistency is not None and resolution_consistency < 60:
        recs.append(
            "Resolution normalization recommended — "
            "significant variation across the dataset."
        )
    if aspect_ratio_consistency is not None and aspect_ratio_consistency < 60:
        recs.append(
            "Aspect ratio normalization recommended before export."
        )

    # 7. Restraint statement
    if intervention_ratio < 0.30:
        recs.append(
            "The expected benefit of further cleanup is low. "
            "The dataset appears close to needing no intervention."
        )

    # 8. Export readiness
    has_actions = (
        deterministic_only_count > 0
        or ai_conservation_count > 0
        or duplicate_count > 0
        or n_errors > 0
    )
    if has_actions:
        recs.append("Ready for LoRA export after applying the actions above.")
    else:
        recs.append("Ready for LoRA export now.")

    return recs


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------


def _write_json(path: Path, report: DatasetHealthReport) -> None:
    path.write_text(
        json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
    )


def _write_txt(path: Path, report: DatasetHealthReport) -> None:
    n = report.analyzed_images or 1
    cs = asdict(report.consistency_scores)
    ts = report.texture_stats
    eg = report.export_guidance
    pb = asdict(report.lora_readiness)["penalty_breakdown"]
    lines = [
        "Dataset Forge — Dataset Health Report",
        "=" * 40,
        f"Dataset Health:          {report.dataset_health_score:.0f}/100",
        f"Estimated LoRA Readiness:{report.lora_readiness_score:4d}/100",
        f"  ({report.lora_readiness_disclaimer})",
        "",
        f"Images:   {report.total_images} total  |  "
        f"{report.analyzed_images} analyzed  |  "
        f"{report.error_images} errors",
        "",
        "Recommendations:",
    ]
    for rec in report.recommendations:
        lines.append(f"  * {rec}")

    lines += [
        "",
        "Decision Engine",
        "-" * 30,
        _bar_line("Leave alone     ", report.leave_alone_count, n),
        _bar_line("Deterministic   ", report.deterministic_only_count, n),
        _bar_line("AI candidate    ", report.ai_conservation_count, n),
        _bar_line("Manual review   ", report.manual_review_count, n),
        "",
        "Consistency Scores (descriptive indicators)",
        "-" * 30,
        f"  Texture consistency:       {cs['texture_consistency']:.0f}",
        f"  Style consistency:         {cs['style_consistency']:.0f}",
        f"  Cleanup consistency:       {cs['cleanup_consistency']:.0f}",
        f"  Overall:                   {cs['overall_dataset_consistency']:.0f}",
        "",
        "Dataset Statistics",
        "-" * 30,
        f"  Avg microtexture:   {ts['average_microtexture']:.1f}",
        f"  Median microtexture:{ts['median_microtexture']:.1f}",
        f"  Std deviation:      {ts['stddev_microtexture']:.1f}",
        f"  Reference baseline: {ts['reference_baseline']:.1f}",
        f"  Gap from baseline:  {ts['gap_from_reference']:+.1f}",
        f"  Above-avg outliers: {ts['above_average_outlier_count']}",
        f"  Below-avg outliers: {ts['below_average_outlier_count']}",
    ]
    if report.resolution_stats is None:
        lines.append(
            "  Resolution:         not available "
            "(run quality analysis to include resolution statistics)"
        )
    lines += [
        "",
        "Export Guidance",
        "-" * 30,
        f"  Leave unchanged:     {eg['leave_unchanged']}",
        f"  Deterministic:       {eg['deterministic_cleanup']}",
        f"  AI conservation:     {eg['ai_conservation']}",
        f"  Manual review:       {eg['manual_review']}",
        f"  Recommended set:     {eg['recommended_training_set_size']} images",
        "",
        "LoRA Readiness Breakdown",
        "-" * 30,
    ]
    for k, v in pb.items():
        if k == "total_penalty":
            continue
        lines.append(f"  {k.replace('_', ' '):40s} {v:+.1f}")
    lines.append(f"  {'total':40s} {pb.get('total_penalty', 0.0):+.1f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_html(path: Path, report: DatasetHealthReport) -> None:
    cs = asdict(report.consistency_scores)
    ts = report.texture_stats
    eg = report.export_guidance
    n = report.analyzed_images or 1

    def _bar(count: int, label: str, color: str) -> str:
        pct = count / n * 100
        filled = round(pct / 2)
        empty = 50 - filled
        bar = f'<span style="color:{color}">{"█" * filled}</span><span style="color:#303b4b">{"░" * empty}</span>'
        return (
            f'<div class="bar-row">'
            f'<span class="bar-label">{pct:4.0f}%  {html.escape(label)}</span>'
            f'<span class="bar">{bar}</span>'
            f"</div>"
        )

    def _stat(label: str, value: object) -> str:
        return (
            f"<div><span>{html.escape(str(label))}</span>"
            f"<strong>{html.escape(str(value))}</strong></div>"
        )

    def _cons_row(label: str, value: object) -> str:
        val_str = f"{value:.0f}" if isinstance(value, float) else ("N/A" if value is None else str(value))
        return f"<tr><td>{html.escape(label)}</td><td><strong>{html.escape(val_str)}</strong></td></tr>"

    rec_items = "".join(
        f"<li>{html.escape(r)}</li>" for r in report.recommendations
    )
    pb = asdict(report.lora_readiness)["penalty_breakdown"]
    pb_rows = "".join(
        f"<tr><td>{html.escape(k.replace('_', ' '))}</td>"
        f"<td style='text-align:right'>{v:+.1f}</td></tr>"
        for k, v in pb.items()
        if k != "total_penalty"
    )
    pb_rows += (
        f"<tr style='font-weight:bold'><td>total</td>"
        f"<td style='text-align:right'>{pb.get('total_penalty', 0.0):+.1f}</td></tr>"
    )

    res_note = (
        "Not available. Run quality analysis to include resolution statistics."
        if report.resolution_stats is None
        else str(report.resolution_stats)
    )

    health_color = "#5ec47a" if report.dataset_health_score >= 80 else (
        "#f0c040" if report.dataset_health_score >= 60 else "#e06060"
    )
    ready_color = "#5ec47a" if report.lora_readiness_score >= 80 else (
        "#f0c040" if report.lora_readiness_score >= 60 else "#e06060"
    )

    cleanup_section: str
    if report.cleanup_status == "not_applied":
        cleanup_section = (
            "<p>Cleanup not yet applied.</p>"
            f"<p>Projected: <strong>{report.projected_images_to_clean}</strong> images "
            "for deterministic cleanup, "
            f"<strong>{report.projected_ai_candidates}</strong> AI conservation candidates, "
            f"<strong>{report.projected_manual_review}</strong> manual review.</p>"
        )
    else:
        d = report.cleanup_applied_details
        cleanup_section = (
            f"<p>Cleanup applied. "
            f"<strong>{d.get('images_cleaned', '?')}</strong> images cleaned, "
            f"<strong>{d.get('images_rejected', '?')}</strong> rejected by preservation checks.</p>"
        )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dataset Forge — Dataset Health Report</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui,sans-serif; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:#0f141b; color:#eef2f7 }}
header {{ position:sticky; top:0; z-index:2; padding:16px 24px;
  background:#171d28ee; backdrop-filter:blur(12px);
  display:flex; align-items:center; gap:32px; flex-wrap:wrap }}
header h1 {{ margin:0; font-size:1.2rem; color:#aeb8c7 }}
.score-pill {{ font-size:1.5rem; font-weight:700; padding:4px 14px;
  border-radius:8px; background:#1a212c }}
main {{ padding:24px; display:grid;
  grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:20px }}
.card {{ background:#1a212c; border:1px solid #303b4b; border-radius:12px;
  padding:18px }}
.card h2 {{ margin:0 0 14px; font-size:1rem; color:#aeb8c7; text-transform:uppercase;
  letter-spacing:.06em }}
.scores-grid {{ display:flex; flex-wrap:wrap; gap:8px }}
.scores-grid div {{ padding:8px 12px; background:#222b38; border-radius:7px; flex:1 1 110px }}
.scores-grid span {{ display:block; color:#aeb8c7; font-size:.74rem }}
.scores-grid strong {{ font-size:1rem }}
ul {{ margin:0; padding-left:18px; line-height:1.7 }}
.bar-row {{ display:flex; align-items:center; gap:10px; margin:4px 0;
  font-size:.85rem; font-family:monospace }}
.bar-label {{ width:200px; white-space:nowrap; color:#aeb8c7 }}
table {{ border-collapse:collapse; width:100% }}
td {{ padding:5px 8px; border-bottom:1px solid #303b4b; font-size:.87rem }}
.disclaimer {{ color:#9aa4b2; font-size:.8rem; font-style:italic; margin-top:8px }}
.full {{ grid-column:1/-1 }}
</style></head><body>
<header>
  <h1>Dataset Forge — Dataset Health Report</h1>
  <span class="score-pill" style="color:{health_color}">
    Health: {report.dataset_health_score:.0f}/100
  </span>
  <span class="score-pill" style="color:{ready_color}">
    LoRA Readiness: {report.lora_readiness_score}/100
  </span>
</header>
<main>

<div class="card">
  <h2>Executive Summary</h2>
  <div class="scores-grid">
    {_stat("Total images", report.total_images)}
    {_stat("Analyzed", report.analyzed_images)}
    {_stat("Errors", report.error_images)}
    {_stat("Health score", f"{report.dataset_health_score:.0f}/100")}
  </div>
  <br>
  <strong>{html.escape(report.headline)}</strong>
  <ul style="margin-top:10px">{rec_items}</ul>
</div>

<div class="card">
  <h2>Decision Engine Summary</h2>
  {_bar(report.leave_alone_count,       "Leave alone",    "#5ec47a")}
  {_bar(report.deterministic_only_count,"Deterministic",  "#60a0e0")}
  {_bar(report.ai_conservation_count,   "AI candidate",   "#c080e0")}
  {_bar(report.manual_review_count,     "Manual review",  "#e09040")}
  <p style="margin-top:12px;font-size:.84rem;color:#aeb8c7">
    High-confidence decisions: <strong>{report.high_confidence_decisions}</strong> &nbsp;
    Low-confidence: <strong>{report.low_confidence_decisions}</strong>
  </p>
</div>

<div class="card">
  <h2>Consistency Scores</h2>
  <p style="font-size:.78rem;color:#9aa4b2;margin:0 0 10px">
    Descriptive indicators — not scientific measurements.
  </p>
  <table>
    {_cons_row("Texture consistency",      cs["texture_consistency"])}
    {_cons_row("Style consistency",        cs["style_consistency"])}
    {_cons_row("Cleanup consistency",      cs["cleanup_consistency"])}
    {_cons_row("Resolution consistency",   cs["resolution_consistency"])}
    {_cons_row("Aspect ratio consistency", cs["aspect_ratio_consistency"])}
    {_cons_row("Overall consistency",      cs["overall_dataset_consistency"])}
  </table>
</div>

<div class="card">
  <h2>Dataset Statistics</h2>
  <div class="scores-grid">
    {_stat("Avg microtexture", f"{ts['average_microtexture']:.1f}")}
    {_stat("Median microtexture", f"{ts['median_microtexture']:.1f}")}
    {_stat("Std deviation", f"{ts['stddev_microtexture']:.1f}")}
    {_stat("Reference baseline", f"{ts['reference_baseline']:.1f}")}
    {_stat("Gap from baseline", f"{ts['gap_from_reference']:+.1f}")}
    {_stat("Above-avg outliers", ts['above_average_outlier_count'])}
    {_stat("Below-avg outliers", ts['below_average_outlier_count'])}
    {_stat("Exact duplicates", report.duplicate_stats['exact_duplicate_count'])}
    {_stat("Near duplicates", report.duplicate_stats['near_duplicate_count'])}
  </div>
  <p style="font-size:.8rem;color:#9aa4b2;margin-top:10px">
    Resolution: {html.escape(res_note)}
  </p>
</div>

<div class="card">
  <h2>Cleanup Summary</h2>
  {cleanup_section}
</div>

<div class="card">
  <h2>Export Guidance</h2>
  <table>
    <tr><td>Leave unchanged</td><td><strong>{eg['leave_unchanged']}</strong></td></tr>
    <tr><td>Deterministic cleanup</td><td><strong>{eg['deterministic_cleanup']}</strong></td></tr>
    <tr><td>AI conservation</td><td><strong>{eg['ai_conservation']}</strong></td></tr>
    <tr><td>Manual review</td><td><strong>{eg['manual_review']}</strong></td></tr>
    <tr><td>Recommended training set</td>
        <td><strong>{eg['recommended_training_set_size']} images</strong></td></tr>
  </table>
</div>

<div class="card full">
  <h2>Estimated LoRA Readiness: {report.lora_readiness_score}/100</h2>
  <p class="disclaimer">{html.escape(_DISCLAIMER)}</p>
  <table>
    {pb_rows}
  </table>
</div>

</main></body></html>"""
    path.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _count_engine(analyzed: list[TextureImageResult]) -> dict[str, int]:
    keys = ["LEAVE_ALONE", "DETERMINISTIC_ONLY", "AI_CONSERVATION_CANDIDATE", "MANUAL_REVIEW"]
    counts: dict[str, int] = {k: 0 for k in keys}
    for r in analyzed:
        if r.engine_recommendation in counts:
            counts[r.engine_recommendation] += 1
    return counts


def _texture_stats(
    analyzed: list[TextureImageResult],
    summary: TextureReportSummary,
    ref_baseline: float,
) -> dict[str, Any]:
    if not analyzed:
        return {
            "average_microtexture": 0.0,
            "median_microtexture": 0.0,
            "stddev_microtexture": 0.0,
            "texture_variance": 0.0,
            "reference_baseline": ref_baseline,
            "gap_from_reference": 0.0,
            "above_average_outlier_count": 0,
            "below_average_outlier_count": 0,
        }
    vals = [r.microtexture_density_score for r in analyzed]
    avg = summary.average_microtexture_density
    std = summary.microtexture_standard_deviation
    return {
        "average_microtexture": round(avg, 2),
        "median_microtexture": round(statistics.median(vals), 2),
        "stddev_microtexture": round(std, 2),
        "texture_variance": round(std ** 2, 2),
        "reference_baseline": ref_baseline,
        "gap_from_reference": round(avg - ref_baseline, 2),
        "above_average_outlier_count": len(summary.above_average_outliers),
        "below_average_outlier_count": len(summary.below_average_outliers),
    }


def _headline(
    health_score: float,
    readiness_score: int,
    leave_alone_count: int,
    n_analyzed: int,
) -> str:
    if n_analyzed == 0:
        return "No images could be analyzed."
    la_pct = leave_alone_count / n_analyzed * 100
    if health_score >= 85 and readiness_score >= 80:
        return "Dataset is well prepared."
    if la_pct >= 70:
        return f"{leave_alone_count} of {n_analyzed} images need no intervention."
    if readiness_score >= 70:
        return "Dataset is in good shape with targeted cleanup recommended."
    if readiness_score >= 50:
        return "Dataset requires cleanup before training."
    return "Dataset requires significant preparation before training."


def _mean_confidence(analyzed: list[TextureImageResult]) -> float:
    if not analyzed:
        return 0.0
    return statistics.mean(r.engine_confidence for r in analyzed)


def _cv(values: list[float]) -> float:
    """Coefficient of variation (stddev / mean), 0 when mean is near zero."""
    if not values:
        return 0.0
    mean = statistics.mean(values)
    if mean < 0.001:
        return 0.0
    std = statistics.pstdev(values)
    return std / mean


def _bar_line(label: str, count: int, n: int) -> str:
    pct = count / n * 100
    filled = round(pct / 2)
    empty = 50 - filled
    bar = "█" * filled + "░" * empty
    return f"{pct:4.0f}%  {label:<16s} {bar}"


def _load_rules() -> dict[str, Any]:
    try:
        return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


__all__ = [
    "ConsistencyScores",
    "DatasetHealthReport",
    "LoRAReadiness",
    "generate_health_report",
]
