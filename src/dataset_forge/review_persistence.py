"""Persistent human review state helpers.

The review decision file is human-authored state. Inspect may read it and may
create a starter template, but it must never overwrite existing human review
decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dataset_forge.recommendation_summary import ImageRecommendation, RecommendationSummary
from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    ReviewDecision,
    ReviewDecisionSet,
    ReviewWorkflowState,
    load_review_decisions,
)

REVIEW_DECISIONS_FILENAME = "review_decisions.json"
REVIEW_DECISIONS_TEMPLATE_FILENAME = "review_decisions_template.json"


@dataclass(frozen=True)
class ReviewStatus:
    status: str
    decisions: tuple[str, ...] = ()

    @property
    def is_reviewed(self) -> bool:
        return self.status == "Already Reviewed"


def load_review_decisions_if_present(output_dir: Path) -> ReviewDecisionSet | None:
    """Load review_decisions.json from an inspect output folder when present."""

    path = output_dir / REVIEW_DECISIONS_FILENAME
    if not path.exists():
        return None
    return load_review_decisions(path)


def review_status_by_image(
    summary: RecommendationSummary,
    decisions: ReviewDecisionSet | None,
) -> dict[str, ReviewStatus]:
    """Map recommendation image paths to display-only review status."""

    if decisions is None:
        return {
            item.image_path: ReviewStatus(status="Pending Review")
            for item in summary.recommendations
        }

    status: dict[str, ReviewStatus] = {}
    for item in summary.recommendations:
        matching = _matching_decisions(item, decisions)
        if not matching:
            status[item.image_path] = ReviewStatus(status="Pending Review")
            continue
        status[item.image_path] = ReviewStatus(
            status="Already Reviewed",
            decisions=tuple(
                _display_decision(value)
                for value in sorted(
                    {
                        decision.decision
                        for decision in matching
                        if decision.decision is not None
                    }
                )
            ),
        )
    return status


def write_review_decisions_template_if_absent(
    summary: RecommendationSummary,
    output_dir: Path,
) -> Path | None:
    """Create a review decisions template without overwriting existing files."""

    path = output_dir / REVIEW_DECISIONS_TEMPLATE_FILENAME
    if path.exists():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_template_payload(summary), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _template_payload(summary: RecommendationSummary) -> dict[str, object]:
    return {
        "schema": REVIEW_DECISIONS_SCHEMA,
        "decisions": [
            _template_decision(item)
            for item in summary.recommendations
        ],
    }


def _template_decision(item: ImageRecommendation) -> dict[str, str | None]:
    payload = {
        "image_path": item.image_path,
        "recommendation": item.display_label,
        "decision": None,
        "workflow_state": ReviewWorkflowState.IN_DATASET.value,
        "notes": "",
    }
    return payload


def _matching_decisions(
    item: ImageRecommendation,
    decisions: ReviewDecisionSet,
) -> list[ReviewDecision]:
    categories = {ref.category for ref in item.finding_refs}
    matches: list[ReviewDecision] = []
    for decision in decisions.decisions:
        if decision.image_path != item.image_path:
            continue
        if decision.decision is None:
            continue
        if decision.category is None or decision.category in categories:
            matches.append(decision)
    return sorted(matches, key=lambda decision: (decision.category or "", decision.decision))


def _display_decision(value: str) -> str:
    labels = {
        "KEEP": "Keep",
        "ACCEPTED_STYLE_FALSE_POSITIVE": "Accepted Style / False Positive",
        "IMPROVEMENT_CANDIDATE": "Improvement Candidate",
        "REMOVAL_CANDIDATE": "Removal Candidate",
        "UNDECIDED": "Undecided",
    }
    return labels.get(value, value.replace("_", " ").title())


def review_status_lines(
    image_path: str,
    review_statuses: Mapping[str, ReviewStatus] | None,
) -> tuple[str, str]:
    """Return human-facing status and decision text for Markdown/HTML output."""

    status = (
        review_statuses.get(image_path)
        if review_statuses is not None
        else None
    )
    if status is None:
        return ("Pending Review", "None recorded")
    if not status.decisions:
        return (status.status, "None recorded")
    return (status.status, "; ".join(status.decisions))


__all__ = [
    "REVIEW_DECISIONS_FILENAME",
    "REVIEW_DECISIONS_TEMPLATE_FILENAME",
    "ReviewStatus",
    "load_review_decisions_if_present",
    "review_status_by_image",
    "review_status_lines",
    "write_review_decisions_template_if_absent",
]
