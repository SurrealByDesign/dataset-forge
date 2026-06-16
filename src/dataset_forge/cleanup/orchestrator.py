from __future__ import annotations

import hashlib
import statistics
from collections import Counter
from typing import Any, Iterable, Mapping

from dataset_forge.cleanup.models import (
    CleanupAction,
    CleanupDecision,
    CleanupPlan,
)
from dataset_forge.cleanup.rules import CleanupRules, load_cleanup_rules
from dataset_forge.evidence import evidence_from_rows
from dataset_forge.recommendations.engine import (
    EvidenceRecommendation,
    recommend_evidence,
)

CLEANUP_ACTIONS = {
    CleanupAction.CLEAN_LIGHT,
    CleanupAction.CLEAN_MEDIUM,
    CleanupAction.CLEAN_STRONG,
    CleanupAction.TEXTURE_NORMALIZE_LIGHT,
    CleanupAction.TEXTURE_NORMALIZE_MEDIUM,
}


class CleanupOrchestrator:
    def __init__(self, rules: CleanupRules | None = None) -> None:
        self.rules = rules or load_cleanup_rules()

    def create_plan(
        self,
        manifest_data: Iterable[Mapping[str, Any]],
        *,
        analysis_results: Mapping[str, Any] | None = None,
        health_report: Mapping[str, Any] | None = None,
        recommendations: Iterable[Mapping[str, Any]] = (),
        plugin_metadata: Iterable[Mapping[str, Any]] = (),
        resource_profile: Mapping[str, Any] | Any | None = None,
        user_config: Mapping[str, Any] | None = None,
    ) -> CleanupPlan:
        rows = [dict(row) for row in manifest_data]
        health = dict(health_report or analysis_results or {})
        recommendation_map = {
            str(item.get("filename", "")): dict(item)
            for item in recommendations
        }
        plugins = [dict(plugin) for plugin in plugin_metadata if plugin.get("enabled", True)]
        preferences = dict(user_config or {})
        resource_values = _profile_values(resource_profile)
        valid_rows = [row for row in rows if str(row.get("status", "")) != "error"]
        artifacts = [_number(row, "artifact_score") for row in valid_rows]
        average_artifact = (
            statistics.mean(artifacts)
            if artifacts
            else float(health.get("average_artifact_score", 0) or 0)
        )
        evidence = evidence_from_rows(rows)
        evidence.dataset_metrics.update(
            {
                "average_artifact_score": average_artifact,
                "dataset_health_score": float(
                    health.get("dataset_health_score", 0) or 0
                ),
            }
        )
        authoritative = {
            item.filename: item
            for item in recommend_evidence(evidence, rules=self.rules)
        }
        decisions = tuple(
            self._decide(
                row,
                authoritative[str(row.get("filename", ""))],
                recommendation_map.get(str(row.get("filename", "")), {}),
                plugins,
                preferences,
                resource_values,
            )
            for row in rows
        )
        counts = Counter(decision.action.value for decision in decisions)
        for action in CleanupAction:
            counts.setdefault(action.value, 0)
        before_health = round(float(health.get("dataset_health_score", 0) or 0), 2)
        projected = _projected_health(before_health, decisions)
        artifact_reduction = _artifact_reduction(rows, decisions)
        disk_usage = sum(decision.estimated_disk_write for decision in decisions)
        gpu_required = any(decision.estimated_gpu_required for decision in decisions)
        profile_name = _profile_name(resource_profile)
        runtimes = sorted(
            {
                decision.estimated_runtime
                for decision in decisions
                if decision.action in CLEANUP_ACTIONS
                or decision.action == CleanupAction.CAPTION_ONLY
            }
        )
        warnings: list[str] = []
        if any(
            decision.action in CLEANUP_ACTIONS and not decision.recommended_plugin
            for decision in decisions
        ):
            warnings.append(
                "One or more cleanup decisions have no enabled matching plugin."
            )
        return CleanupPlan(
            version=1,
            dataset_health_score=before_health,
            projected_dataset_health=projected,
            estimated_artifact_leakage_reduction=artifact_reduction,
            estimated_runtime=", ".join(runtimes) if runtimes else "no automated work",
            estimated_disk_usage=disk_usage,
            estimated_gpu_required=gpu_required,
            resource_profile=profile_name,
            total_images=len(decisions),
            action_counts=dict(counts),
            decisions=decisions,
            warnings=tuple(warnings),
        )

    def _decide(
        self,
        row: Mapping[str, Any],
        authoritative: EvidenceRecommendation,
        recommendation: Mapping[str, Any],
        plugins: list[dict[str, Any]],
        preferences: dict[str, Any],
        resource_profile: dict[str, Any],
    ) -> CleanupDecision:
        filename = authoritative.filename
        quality = _number(row, "overall_quality_score")
        warnings: list[str] = []
        action = CleanupAction(authoritative.action)
        confidence = authoritative.confidence
        explanation = authoritative.explanation

        preset = _recommended_preset(
            action,
            recommendation,
            preferences,
            self.rules,
            filename,
        )
        capability = _required_capability(
            action,
            preset,
            preferences,
            self.rules,
            filename,
        )
        plugin = _rank_plugin(
            plugins,
            action,
            capability,
            preset,
            preferences,
            resource_profile,
        )
        if action in CLEANUP_ACTIONS and plugin is None:
            warnings.append(
                f"No enabled plugin advertises capability '{capability}'."
            )
        gain = _quality_gain(action, self.rules)
        if plugin is not None:
            gain = max(gain, float(plugin.get("estimated_quality_gain", 0) or 0))
        if action == CleanupAction.REGENERATE:
            gain = max(20.0, self.rules.healthy_quality - quality)
        after = min(100.0, quality + gain)
        if action in {
            CleanupAction.EXCLUDE,
            CleanupAction.DUPLICATE_REVIEW,
            CleanupAction.MANUAL_REVIEW,
        }:
            after = quality
            gain = 0.0
        strength = _strength(action)
        expected_benefit = (
            f"+{gain:.1f} estimated quality points"
            if gain > 0
            else "No automatic quality gain estimated"
        )
        estimated_disk = (
            int(_number(row, "file_size"))
            if action in CLEANUP_ACTIONS or action == CleanupAction.REGENERATE
            else 0
        )
        return CleanupDecision(
            image_id=_image_id(row),
            filename=filename,
            action=action,
            confidence=max(0, min(100, int(round(confidence)))),
            explanation=explanation,
            expected_benefit=expected_benefit,
            before_quality_score=round(quality, 2),
            estimated_after_quality_score=round(after, 2),
            estimated_quality_delta=round(gain, 2),
            recommended_plugin=str(plugin.get("id", "")) if plugin else "",
            recommended_preset=preset,
            recommended_strength=strength,
            estimated_runtime=(
                str(plugin.get("estimated_runtime", "unknown"))
                if plugin
                else "manual" if action in {
                    CleanupAction.MANUAL_REVIEW,
                    CleanupAction.DUPLICATE_REVIEW,
                } else "none"
            ),
            estimated_disk_write=estimated_disk,
            estimated_gpu_required=bool(
                plugin and int(plugin.get("estimated_gpu", 0) or 0) > 0
            ),
            warnings=tuple(warnings),
        )


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key, 0)
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _recommended_preset(
    action: CleanupAction,
    recommendation: Mapping[str, Any],
    preferences: Mapping[str, Any],
    rules: CleanupRules,
    filename: str,
) -> str:
    per_image = preferences.get("preset_by_image", {})
    if isinstance(per_image, Mapping) and filename in per_image:
        return str(per_image[filename])
    suggested = recommendation.get("suggested_preset")
    if suggested:
        return str(suggested)
    default_preset = preferences.get("default_preset")
    if default_preset and action in CLEANUP_ACTIONS:
        return str(default_preset)
    capability = rules.capabilities.get(action.value, "")
    return rules.presets.get(capability, "")


def _required_capability(
    action: CleanupAction,
    preset: str,
    preferences: Mapping[str, Any],
    rules: CleanupRules,
    filename: str,
) -> str:
    per_image = preferences.get("capability_by_image", {})
    if isinstance(per_image, Mapping) and filename in per_image:
        return str(per_image[filename])
    if "watercolor" in preset:
        return "watercolor_cleanup"
    if "anime" in preset or "lineart" in preset:
        return "anime_lineart_cleanup"
    if "photoreal" in preset:
        return "photoreal_cleanup"
    return rules.capabilities.get(action.value, "")


def _rank_plugin(
    plugins: list[dict[str, Any]],
    action: CleanupAction,
    capability: str,
    preset: str,
    preferences: Mapping[str, Any],
    resource_profile: Mapping[str, Any],
) -> dict[str, Any] | None:
    category = "captioner" if action == CleanupAction.CAPTION_ONLY else "transform"
    if action not in CLEANUP_ACTIONS and action != CleanupAction.CAPTION_ONLY:
        return None
    preferred = preferences.get("preferred_plugins", [])
    preferred_ids = (
        [str(item) for item in preferred]
        if isinstance(preferred, (list, tuple))
        else []
    )
    candidates: list[tuple[float, dict[str, Any]]] = []
    for plugin in plugins:
        if plugin.get("category") != category:
            continue
        capabilities = set(plugin.get("capabilities", ())) | set(plugin.get("tags", ()))
        if capability and capability not in capabilities:
            continue
        score = 50.0 if capability in capabilities else 0.0
        if preset and preset in plugin.get("compatible_presets", ()):
            score += 25.0
        score += min(20.0, float(plugin.get("estimated_quality_gain", 0) or 0))
        estimated_gpu = int(plugin.get("estimated_gpu", 0) or 0)
        estimated_memory = int(plugin.get("estimated_memory", 0) or 0)
        score -= min(10.0, estimated_gpu / 1024**3 * 2)
        score -= min(5.0, estimated_memory / 1024**3)
        ram_limit = int(resource_profile.get("ram_limit_mb", 0) or 0) * 1024**2
        if ram_limit and estimated_memory > ram_limit:
            score -= 50.0
        if estimated_gpu and not preferences.get("allow_gpu", True):
            score -= 40.0
        if plugin.get("id") in preferred_ids:
            score += 30.0 - preferred_ids.index(plugin["id"])
        candidates.append((score, plugin))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], str(item[1].get("id"))))[1]


def _quality_gain(action: CleanupAction, rules: CleanupRules) -> float:
    return {
        CleanupAction.CLEAN_LIGHT: rules.quality_gain_light,
        CleanupAction.CLEAN_MEDIUM: rules.quality_gain_medium,
        CleanupAction.CLEAN_STRONG: rules.quality_gain_strong,
        CleanupAction.TEXTURE_NORMALIZE_LIGHT: rules.quality_gain_light,
        CleanupAction.TEXTURE_NORMALIZE_MEDIUM: rules.quality_gain_medium,
        CleanupAction.CAPTION_ONLY: rules.quality_gain_caption,
    }.get(action, 0.0)


def _strength(action: CleanupAction) -> str:
    return {
        CleanupAction.CLEAN_LIGHT: "light",
        CleanupAction.CLEAN_MEDIUM: "medium",
        CleanupAction.CLEAN_STRONG: "strong",
        CleanupAction.TEXTURE_NORMALIZE_LIGHT: "light",
        CleanupAction.TEXTURE_NORMALIZE_MEDIUM: "medium",
    }.get(action, "")


def _image_id(row: Mapping[str, Any]) -> str:
    file_hash = str(row.get("file_hash", "") or "")
    if file_hash:
        return file_hash[:16]
    identity = str(row.get("original_path") or row.get("filename") or "unknown")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _projected_health(
    before: float,
    decisions: tuple[CleanupDecision, ...],
) -> float:
    if not decisions:
        return before
    gain = sum(decision.estimated_quality_delta for decision in decisions) / len(decisions)
    exclusions = sum(
        decision.action == CleanupAction.EXCLUDE for decision in decisions
    )
    return round(min(100.0, before + gain * 0.55 + exclusions / len(decisions) * 8), 2)


def _artifact_reduction(
    rows: list[dict[str, Any]],
    decisions: tuple[CleanupDecision, ...],
) -> float:
    total = sum(_number(row, "artifact_score") for row in rows)
    if total <= 0:
        return 0.0
    factors = {
        CleanupAction.CLEAN_LIGHT: 0.25,
        CleanupAction.CLEAN_MEDIUM: 0.5,
        CleanupAction.CLEAN_STRONG: 0.7,
        CleanupAction.EXCLUDE: 1.0,
        CleanupAction.REGENERATE: 0.8,
    }
    reduced = sum(
        _number(row, "artifact_score") * factors.get(decision.action, 0.0)
        for row, decision in zip(rows, decisions, strict=True)
    )
    return round(min(100.0, reduced / total * 100), 2)


def _profile_name(profile: Mapping[str, Any] | Any | None) -> str:
    if profile is None:
        return "balanced"
    if isinstance(profile, Mapping):
        return str(profile.get("name", "custom"))
    if hasattr(profile, "name"):
        return str(profile.name)
    if hasattr(profile, "profile") and hasattr(profile.profile, "name"):
        return str(profile.profile.name)
    return "custom"


def _profile_values(profile: Mapping[str, Any] | Any | None) -> dict[str, Any]:
    if profile is None:
        return {"name": "balanced"}
    if isinstance(profile, Mapping):
        return dict(profile)
    if hasattr(profile, "to_dict"):
        return dict(profile.to_dict())
    if hasattr(profile, "profile") and hasattr(profile.profile, "to_dict"):
        return dict(profile.profile.to_dict())
    return {"name": _profile_name(profile)}
