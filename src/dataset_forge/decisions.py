"""Decision engine: converts per-image evidence into a single conservative recommendation.

All public functions are pure — no I/O, no side effects.  The only entry point
callers need is ``evaluate_decision``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

OUTCOMES = (
    "LEAVE_ALONE",
    "DETERMINISTIC_ONLY",
    "AI_CONSERVATION_CANDIDATE",
    "MANUAL_REVIEW",
)


@dataclass(frozen=True)
class EngineDecision:
    """The engine's single recommendation for one image."""

    recommendation: str
    confidence: int
    deciding_factor: str
    net_score: float
    conflicting: bool
    signals: dict[str, float]
    dataset_context: dict[str, float]
    uncertainty_sources: list[str]
    counterfactual: str
    human_readable: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_decision(
    *,
    microtexture: float,
    highlight_speck: float,
    watercolor_smoothness: float,
    texture_consistency: float,
    dataset_average: float,
    dataset_stddev: float,
    is_reference_image: bool = False,
    ai_backend_configured: bool = False,
    rules: dict[str, Any] | None = None,
) -> EngineDecision:
    """Return a single conservative recommendation for one image.

    Args:
        microtexture: ``microtexture_density_score`` from texture analysis.
        highlight_speck: ``highlight_speck_score`` from texture analysis.
        watercolor_smoothness: ``watercolor_smoothness_score`` from texture analysis.
        texture_consistency: ``texture_consistency_score`` from texture analysis.
        dataset_average: mean ``microtexture_density_score`` across the dataset.
        dataset_stddev: standard deviation of microtexture across the dataset.
        is_reference_image: True for confirmed exemplar/reference images.
        ai_backend_configured: True when an AI conservation backend is available.
        rules: raw dict from ``cleanup_rules.json``; ``decision_engine`` sub-key
               is consumed.  Defaults apply when absent.
    """
    r = _Rules(rules or {})

    # ------------------------------------------------------------------ #
    # Rule 0 — hard gate: reference / exemplar images are never modified  #
    # ------------------------------------------------------------------ #
    if is_reference_image:
        return _decision(
            recommendation="LEAVE_ALONE",
            confidence=99,
            deciding_factor="is_reference_image",
            net_score=0.0,
            conflicting=False,
            signals={},
            dataset_context={"is_reference_image": 1.0},
            uncertainty_sources=[],
            counterfactual="Reference images are never modified.",
            human_readable="Image is a confirmed reference exemplar and must not be modified.",
        )

    # ------------------------------------------------------------------ #
    # Signal extraction                                                    #
    # ------------------------------------------------------------------ #
    micro_delta = microtexture - r.reference_baseline

    speck_signal = _clamp((highlight_speck - 30.0) / 70.0)
    microtexture_signal = _clamp((micro_delta - r.neutral_zone) / 30.0)
    smoothness_signal = _clamp((70.0 - watercolor_smoothness) / 40.0)
    consistency_signal = _clamp((50.0 - texture_consistency) / 50.0)

    signals: dict[str, float] = {
        "speck_signal": round(speck_signal, 3),
        "microtexture_signal": round(microtexture_signal, 3),
        "smoothness_signal": round(smoothness_signal, 3),
        "consistency_signal": round(consistency_signal, 3),
    }

    # ------------------------------------------------------------------ #
    # Dataset context                                                      #
    # ------------------------------------------------------------------ #
    centroid_distance = abs(microtexture - dataset_average) / max(1.0, dataset_stddev)
    dataset_context: dict[str, float] = {
        "microtexture_delta_from_reference": round(micro_delta, 2),
        "centroid_distance": round(centroid_distance, 3),
        "is_reference_image": 0.0,
    }

    # ------------------------------------------------------------------ #
    # Conflict detection                                                   #
    # High microtexture + high watercolor_smoothness: texture may be      #
    # intentional painted grain rather than a GPT artifact.               #
    # ------------------------------------------------------------------ #
    conflicting = microtexture_signal > 0.4 and watercolor_smoothness > 65.0

    # ------------------------------------------------------------------ #
    # Uncertainty sources (accumulated across rules)                       #
    # ------------------------------------------------------------------ #
    uncertainty_sources: list[str] = []
    if conflicting:
        uncertainty_sources.append("conflicting_signals")
    if centroid_distance < 0.5:
        uncertainty_sources.append("near_dataset_centroid")

    # ------------------------------------------------------------------ #
    # Rule 0b — all signals below noise floor → LEAVE_ALONE               #
    # ------------------------------------------------------------------ #
    if all(v < 0.05 for v in signals.values()):
        return _decision(
            recommendation="LEAVE_ALONE",
            confidence=_conf(95, uncertainty_sources, centroid_distance),
            deciding_factor="all_signals_minimal",
            net_score=0.0,
            conflicting=False,
            signals=signals,
            dataset_context=dataset_context,
            uncertainty_sources=[],
            counterfactual="No signal exceeds the natural variance threshold.",
            human_readable=(
                "All texture signals are within natural variance of the reference art. "
                "No intervention is warranted."
            ),
        )

    # ------------------------------------------------------------------ #
    # Benefit / cost estimates                                             #
    # ------------------------------------------------------------------ #
    det_benefit = 0.9 * speck_signal  # texture benefit ~0 (empirically proven)
    det_cost_norm = _clamp(speck_signal * 15.0 + microtexture_signal * 8.0) / 100.0
    det_net = det_benefit - det_cost_norm

    # ------------------------------------------------------------------ #
    # Rule 1 — LEAVE_ALONE: cost-benefit unfavourable, modest signals     #
    # ------------------------------------------------------------------ #
    if det_net < 0.10 and microtexture_signal < 0.25:
        return _decision(
            recommendation="LEAVE_ALONE",
            confidence=_conf(88, uncertainty_sources, centroid_distance),
            deciding_factor="low_net_benefit",
            net_score=round(det_net, 3),
            conflicting=conflicting,
            signals=signals,
            dataset_context=dataset_context,
            uncertainty_sources=uncertainty_sources,
            counterfactual=(
                "If speck signal exceeded 0.30, would recommend DETERMINISTIC_ONLY. "
                "If microtexture signal exceeded 0.40, would consider AI."
            ),
            human_readable=_leave_alone_reason(micro_delta, speck_signal, r),
        )

    # Near-centroid + no meaningful specks → image is typical; leave alone
    if centroid_distance < 0.5 and speck_signal < 0.30:
        return _decision(
            recommendation="LEAVE_ALONE",
            confidence=_conf(80, uncertainty_sources, centroid_distance),
            deciding_factor="near_dataset_centroid",
            net_score=round(det_net, 3),
            conflicting=conflicting,
            signals=signals,
            dataset_context=dataset_context,
            uncertainty_sources=uncertainty_sources,
            counterfactual="If speck signal exceeded 0.30, would consider DETERMINISTIC_ONLY.",
            human_readable=(
                f"Image is close to the dataset centroid (z-score {centroid_distance:.2f}) "
                "with no significant speck artifacts. "
                "Cleaning this image risks removing texture that defines the dataset style. "
                "Leave unchanged."
            ),
        )

    # ------------------------------------------------------------------ #
    # Rule 2 — DETERMINISTIC_ONLY                                         #
    # ------------------------------------------------------------------ #
    # 2a: clear speck artifact, low microtexture excess
    if speck_signal >= 0.30 and det_net > 0.15 and microtexture_signal < 0.40:
        return _decision(
            recommendation="DETERMINISTIC_ONLY",
            confidence=_conf(91, uncertainty_sources, centroid_distance),
            deciding_factor="speck_signal",
            net_score=round(det_net, 3),
            conflicting=conflicting,
            signals=signals,
            dataset_context=dataset_context,
            uncertainty_sources=uncertainty_sources,
            counterfactual=(
                "If microtexture signal exceeded 0.40, would escalate to "
                "AI_CONSERVATION_CANDIDATE."
            ),
            human_readable=(
                f"Speck or glitter signal is elevated "
                f"(highlight_speck_score {highlight_speck:.1f}). "
                "Deterministic speck removal provides meaningful improvement at low cost. "
                "Microtexture excess is within the acceptable range for deterministic-only "
                "treatment."
            ),
        )

    # 2b: mild microtexture excess (not severe enough for AI, or AI unavailable)
    if 0.15 <= microtexture_signal < 0.40:
        counterfactual = (
            "If microtexture signal exceeded 0.40 and an AI backend were configured, "
            "would recommend AI_CONSERVATION_CANDIDATE."
            if not ai_backend_configured
            else "If microtexture signal exceeded 0.40, would recommend AI_CONSERVATION_CANDIDATE."
        )
        return _decision(
            recommendation="DETERMINISTIC_ONLY",
            confidence=_conf(80, uncertainty_sources, centroid_distance),
            deciding_factor="mild_microtexture_signal",
            net_score=round(det_net, 3),
            conflicting=conflicting,
            signals=signals,
            dataset_context=dataset_context,
            uncertainty_sources=uncertainty_sources,
            counterfactual=counterfactual,
            human_readable=(
                f"Mild excess microtexture ({microtexture:.1f} vs reference baseline "
                f"{r.reference_baseline:.1f}, delta={micro_delta:+.1f}). "
                "Conservative deterministic cleanup is appropriate. "
                "Recursive GPT structure is not severe enough to warrant AI intervention."
            ),
        )

    # ------------------------------------------------------------------ #
    # Rule 3 — AI_CONSERVATION_CANDIDATE                                  #
    # ------------------------------------------------------------------ #
    if microtexture_signal >= 0.40 and not conflicting and ai_backend_configured:
        gap_fraction = _clamp(micro_delta / 40.0)
        ai_benefit = gap_fraction * r.model_confidence_factor
        ai_cost_est = _sigmoid((micro_delta - 20.0) / 15.0) * 70.0
        ai_net = ai_benefit - (ai_cost_est / 100.0)

        if ai_net > 0.15:
            ai_uncertainty = list(uncertainty_sources)
            if r.model_confidence_factor < 0.6:
                ai_uncertainty.append("limited_ai_track_record")
            return _decision(
                recommendation="AI_CONSERVATION_CANDIDATE",
                confidence=_conf(87, ai_uncertainty, centroid_distance),
                deciding_factor="microtexture_signal",
                net_score=round(ai_net, 3),
                conflicting=False,
                signals=signals,
                dataset_context=dataset_context,
                uncertainty_sources=ai_uncertainty,
                counterfactual=(
                    "If microtexture fell below the 0.40 signal threshold after "
                    "deterministic cleanup, would route to DETERMINISTIC_ONLY."
                ),
                human_readable=(
                    f"Significant recursive GPT microfacet structure detected "
                    f"({microtexture:.1f} vs reference baseline {r.reference_baseline:.1f}, "
                    f"delta={micro_delta:+.1f}). "
                    "Deterministic cleanup will run first; an AI conservation candidate "
                    "will be proposed if recursive structure persists. "
                    "Human review required before any AI result is accepted."
                ),
            )

    # ------------------------------------------------------------------ #
    # Rule 4 — MANUAL_REVIEW: conflicting signals, near-threshold, or    #
    # AI unavailable despite high microtexture signal                     #
    # ------------------------------------------------------------------ #
    manual_uncertainty = list(uncertainty_sources)
    if microtexture_signal >= 0.40 and not ai_backend_configured:
        manual_uncertainty.append("ai_backend_not_configured")
    conf = min(59, _conf(55, manual_uncertainty, centroid_distance))
    return _decision(
        recommendation="MANUAL_REVIEW",
        confidence=conf,
        deciding_factor="conflicting_or_uncertain",
        net_score=round(det_net, 3),
        conflicting=conflicting,
        signals=signals,
        dataset_context=dataset_context,
        uncertainty_sources=manual_uncertainty,
        counterfactual=(
            "Resolving conflicting signals through manual inspection may clarify "
            "whether texture is intentional or a GPT artifact."
        ),
        human_readable=_manual_review_reason(
            conflicting, microtexture_signal, micro_delta, ai_backend_configured, r
        ),
    )


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #


class _Rules:
    """Thin wrapper around the ``decision_engine`` section of cleanup_rules.json."""

    def __init__(self, raw: dict[str, Any]) -> None:
        engine: dict[str, Any] = raw.get("decision_engine", {}) if raw else {}
        self.reference_baseline = float(
            engine.get("reference_baseline_microtexture", 26.86)
        )
        self.neutral_zone = float(engine.get("microtexture_neutral_zone", 10.0))
        self.model_confidence_factor = float(
            engine.get("ai_model_confidence_factor", 0.5)
        )


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))


def _conf(base: int, uncertainty_sources: list[str], centroid_distance: float) -> int:
    penalty = 0
    if "conflicting_signals" in uncertainty_sources:
        penalty += 20
    if "near_dataset_centroid" in uncertainty_sources:
        penalty += 10
    if "limited_ai_track_record" in uncertainty_sources:
        penalty += 10
    if "ai_backend_not_configured" in uncertainty_sources:
        penalty += 5
    if centroid_distance < 0.5:
        penalty += 5
    return max(0, min(100, base - penalty))


def _leave_alone_reason(micro_delta: float, speck_signal: float, r: _Rules) -> str:
    if micro_delta < r.neutral_zone and speck_signal < 0.10:
        return (
            f"Image microtexture is close to the reference art baseline "
            f"({r.reference_baseline:.1f}). "
            "Expected benefit of cleanup is negligible. Leave unchanged."
        )
    return (
        "Expected cleanup benefit does not outweigh intervention cost. "
        f"Microtexture excess is {micro_delta:+.1f} above the reference baseline "
        f"({r.reference_baseline:.1f}). "
        "Image is within acceptable range for LoRA training."
    )


def _manual_review_reason(
    conflicting: bool,
    micro_signal: float,
    micro_delta: float,
    ai_configured: bool,
    r: _Rules,
) -> str:
    if conflicting:
        return (
            "Microtexture signal is elevated but watercolor smoothness is also high. "
            "Cannot determine whether excess texture is a GPT artifact or intentional "
            "painted grain. Manual inspection required."
        )
    if micro_signal >= 0.40 and not ai_configured:
        return (
            f"Significant microtexture excess detected (delta={micro_delta:+.1f} vs "
            f"reference baseline {r.reference_baseline:.1f}). "
            "Deterministic filters cannot address recursive GPT structure at this level. "
            "An AI conservation backend is not configured. Manual review required."
        )
    return (
        "Conflicting or weak signals prevent a confident recommendation. "
        f"Microtexture excess: {micro_delta:+.1f} vs reference. "
        "Manual inspection required to determine whether intervention is appropriate."
    )


def _decision(**kwargs: Any) -> EngineDecision:
    return EngineDecision(**kwargs)


__all__ = [
    "OUTCOMES",
    "EngineDecision",
    "evaluate_decision",
]
