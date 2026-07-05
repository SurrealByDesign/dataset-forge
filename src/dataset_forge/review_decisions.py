"""Internal review decision helpers for inspected datasets.

This module records human intent over existing inspection findings. It does not
run analyzers, change thresholds, modify images, or plan cleanup/export work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

REVIEW_DECISIONS_SCHEMA = "dataset-forge/review-decisions/v1"


class ReviewDecisionValue(str, Enum):
    CONFIRMED_ARTIFACT = "CONFIRMED_ARTIFACT"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ACCEPTABLE_STYLE = "ACCEPTABLE_STYLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IGNORE = "IGNORE"
    LOCKED = "LOCKED"


_DECISION_ORDER = tuple(value.value for value in ReviewDecisionValue)
_TOP_LEVEL_FIELDS = {"schema", "decisions"}
_DECISION_FIELDS = {
    "image_path",
    "decision",
    "category",
    "analyzer",
    "reason",
    "recommendation",
    "notes",
}
_EXCLUDE_FROM_FUTURE_ACTION = {
    ReviewDecisionValue.FALSE_POSITIVE.value,
    ReviewDecisionValue.ACCEPTABLE_STYLE.value,
    ReviewDecisionValue.IGNORE.value,
    ReviewDecisionValue.LOCKED.value,
}


@dataclass(frozen=True)
class ReviewDecision:
    image_path: str
    decision: str | None
    category: str | None = None
    analyzer: str | None = None
    recommendation: str | None = None
    notes: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, str | None]:
        payload = {
            "image_path": self.image_path,
            "decision": self.decision,
        }
        if self.category is not None:
            payload["category"] = self.category
        if self.analyzer is not None:
            payload["analyzer"] = self.analyzer
        if self.recommendation is not None:
            payload["recommendation"] = self.recommendation
        if self.notes:
            payload["notes"] = self.notes
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class ReviewDecisionSummary:
    total_decisions: int
    counts_by_decision: dict[str, int]
    counts_by_analyzer: dict[str, int]
    counts_by_category: dict[str, int]
    locked_image_count: int
    ignored_image_count: int
    unresolved_review_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "counts_by_decision": dict(self.counts_by_decision),
            "counts_by_analyzer": dict(self.counts_by_analyzer),
            "counts_by_category": dict(self.counts_by_category),
            "locked_image_count": self.locked_image_count,
            "ignored_image_count": self.ignored_image_count,
            "unresolved_review_count": self.unresolved_review_count,
        }


@dataclass(frozen=True)
class ReviewDecisionSet:
    schema: str
    decisions: tuple[ReviewDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "decisions": [decision.to_dict() for decision in self.decisions],
        }

    def summary(self) -> ReviewDecisionSummary:
        return summarize_review_decisions(self)

    def decision_for(
        self,
        image_path: str | Path,
        category: str | None = None,
    ) -> ReviewDecision | None:
        image = _normalize_path(str(image_path))
        by_scope = _decisions_by_scope(self.decisions)
        if category is not None:
            exact = by_scope.get((image, category))
            if exact is not None:
                return exact
        return by_scope.get((image, None))

    def decision_for_finding(self, finding: Any) -> ReviewDecision | None:
        image_path = _value_from_finding(finding, "image_path")
        category = _value_from_finding(finding, "category")
        return self.decision_for(image_path, category)

    def is_image_locked(self, image_path: str | Path) -> bool:
        image = _normalize_path(str(image_path))
        return any(
            decision.image_path == image
            and decision.decision == ReviewDecisionValue.LOCKED.value
            for decision in self.decisions
        )

    def is_finding_confirmed(
        self,
        image_path: str | Path,
        category: str,
    ) -> bool:
        decision = self.decision_for(image_path, category)
        return decision is not None and decision.decision == ReviewDecisionValue.CONFIRMED_ARTIFACT.value

    def is_finding_false_positive(
        self,
        image_path: str | Path,
        category: str,
    ) -> bool:
        decision = self.decision_for(image_path, category)
        return decision is not None and decision.decision == ReviewDecisionValue.FALSE_POSITIVE.value

    def should_exclude_from_future_action(
        self,
        image_path: str | Path,
        category: str | None = None,
    ) -> bool:
        if self.is_image_locked(image_path):
            return True
        decision = self.decision_for(image_path, category)
        return decision is not None and decision.decision in _EXCLUDE_FROM_FUTURE_ACTION


def load_review_decisions(path: Path) -> ReviewDecisionSet:
    """Load a schema-versioned review decision file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid review decision JSON: {path}") from exc
    return parse_review_decisions(data)


def parse_review_decisions(data: dict[str, Any]) -> ReviewDecisionSet:
    """Parse and validate review decisions."""
    if not isinstance(data, dict):
        raise ValueError("review decisions payload must be an object")
    _reject_unknown_fields(data, _TOP_LEVEL_FIELDS, "review decisions payload")

    schema = data.get("schema")
    if schema != REVIEW_DECISIONS_SCHEMA:
        raise ValueError(
            f"Unsupported review decision schema {schema!r}; "
            f"expected {REVIEW_DECISIONS_SCHEMA!r}"
        )

    raw_decisions = data.get("decisions")
    if not isinstance(raw_decisions, list):
        raise ValueError("review decisions must contain a 'decisions' list")

    seen: set[tuple[str, str | None]] = set()
    decisions: list[ReviewDecision] = []
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            raise ValueError("each review decision must be an object")
        _reject_unknown_fields(raw, _DECISION_FIELDS, "review decision")
        decision = _parse_decision(raw)
        scope = (decision.image_path, decision.category)
        if scope in seen:
            if decision.category is None:
                raise ValueError(f"duplicate review decision for image: {decision.image_path}")
            raise ValueError(
                "duplicate review decision for image/category: "
                f"{decision.image_path} / {decision.category}"
            )
        seen.add(scope)
        decisions.append(decision)

    return ReviewDecisionSet(
        schema=REVIEW_DECISIONS_SCHEMA,
        decisions=tuple(sorted(decisions, key=_decision_sort_key)),
    )


def summarize_review_decisions(
    decisions: ReviewDecisionSet | tuple[ReviewDecision, ...] | list[ReviewDecision],
) -> ReviewDecisionSummary:
    """Build deterministic counts over review decisions."""
    items = decisions.decisions if isinstance(decisions, ReviewDecisionSet) else tuple(decisions)
    counts_by_decision = {decision: 0 for decision in _DECISION_ORDER}
    counts_by_analyzer: dict[str, int] = {}
    counts_by_category: dict[str, int] = {}
    locked_images: set[str] = set()
    ignored_images: set[str] = set()
    unresolved_review_count = 0

    for decision in items:
        if decision.decision is None:
            continue
        counts_by_decision[decision.decision] += 1
        if decision.analyzer is not None:
            counts_by_analyzer[decision.analyzer] = counts_by_analyzer.get(decision.analyzer, 0) + 1
        if decision.category is not None:
            counts_by_category[decision.category] = counts_by_category.get(decision.category, 0) + 1
        if decision.decision == ReviewDecisionValue.LOCKED.value:
            locked_images.add(decision.image_path)
        if decision.decision == ReviewDecisionValue.IGNORE.value:
            ignored_images.add(decision.image_path)
        if decision.decision == ReviewDecisionValue.NEEDS_REVIEW.value:
            unresolved_review_count += 1

    return ReviewDecisionSummary(
        total_decisions=sum(1 for decision in items if decision.decision is not None),
        counts_by_decision=counts_by_decision,
        counts_by_analyzer=dict(sorted(counts_by_analyzer.items())),
        counts_by_category=dict(sorted(counts_by_category.items())),
        locked_image_count=len(locked_images),
        ignored_image_count=len(ignored_images),
        unresolved_review_count=unresolved_review_count,
    )


def write_review_decisions_json(
    decisions: ReviewDecisionSet,
    output_path: Path,
) -> None:
    """Write normalized review decisions JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(decisions.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_decision(raw: dict[str, Any]) -> ReviewDecision:
    decision = raw.get("decision")
    if decision is not None and decision not in _DECISION_ORDER:
        raise ValueError(f"unknown review decision value: {decision!r}")
    image_path = _normalize_path(raw.get("image_path"))
    category = _optional_non_empty_string(raw.get("category"), "category")
    analyzer = _optional_non_empty_string(raw.get("analyzer"), "analyzer")
    recommendation = _optional_non_empty_string(
        raw.get("recommendation"),
        "recommendation",
    )
    notes = raw.get("notes", "")
    if not isinstance(notes, str):
        raise ValueError("notes must be a string when provided")
    reason = raw.get("reason", "")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string when provided")
    return ReviewDecision(
        image_path=image_path,
        decision=decision,
        category=category,
        analyzer=analyzer,
        recommendation=recommendation,
        notes=notes,
        reason=reason,
    )


def _decisions_by_scope(
    decisions: tuple[ReviewDecision, ...],
) -> dict[tuple[str, str | None], ReviewDecision]:
    return {
        (decision.image_path, decision.category): decision
        for decision in decisions
    }


def _reject_unknown_fields(
    data: dict[str, Any],
    allowed: set[str],
    subject: str,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"unknown fields in {subject}: {unknown}")


def _optional_non_empty_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string when provided")
    return value


def _normalize_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("image_path must be a non-empty string")
    return value.replace("\\", "/")


def _value_from_finding(finding: Any, field: str) -> str:
    if isinstance(finding, dict):
        value = finding.get(field)
    else:
        value = getattr(finding, field)
    if isinstance(value, Path):
        return str(value)
    if not isinstance(value, str):
        raise ValueError(f"finding {field} must be a string")
    return value


def _decision_sort_key(decision: ReviewDecision) -> tuple[str, str, str, str]:
    return (
        decision.image_path,
        decision.category or "",
        decision.analyzer or "",
        decision.decision or "",
    )


__all__ = [
    "REVIEW_DECISIONS_SCHEMA",
    "ReviewDecision",
    "ReviewDecisionSet",
    "ReviewDecisionSummary",
    "ReviewDecisionValue",
    "load_review_decisions",
    "parse_review_decisions",
    "summarize_review_decisions",
    "write_review_decisions_json",
]
