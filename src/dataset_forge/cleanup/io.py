from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from dataset_forge.cleanup.models import CleanupPlan
from dataset_forge.core.structured import load_structured_file

PLAN_JSON = "cleanup_plan.json"
PLAN_CSV = "cleanup_plan.csv"


def write_cleanup_plan(output_path: Path, plan: CleanupPlan) -> tuple[Path, Path]:
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / PLAN_JSON
    csv_path = output_path / PLAN_CSV
    json_path.write_text(
        json.dumps(plan.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    decisions = [decision.to_dict() for decision in plan.decisions]
    fieldnames = list(decisions[0]) if decisions else [
        "image_id",
        "filename",
        "action",
        "confidence",
        "explanation",
        "expected_benefit",
        "before_quality_score",
        "estimated_after_quality_score",
        "estimated_quality_delta",
        "recommended_plugin",
        "recommended_preset",
        "recommended_strength",
        "estimated_runtime",
        "estimated_disk_write",
        "estimated_gpu_required",
        "warnings",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for decision in decisions:
            decision["warnings"] = " | ".join(decision["warnings"])
            writer.writerow(decision)
    return json_path, csv_path


def load_cleanup_plan(output_path: Path) -> dict[str, Any]:
    return load_structured_file(output_path.expanduser().resolve() / PLAN_JSON)

