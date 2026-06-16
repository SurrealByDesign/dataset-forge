from __future__ import annotations

import json
from pathlib import Path

from dataset_forge.evidence import evidence_from_rows
from dataset_forge.recommendations.engine import recommend_dataset


def build_dataset_report(
    rows: list[dict[str, object]],
    duplicate_count: int,
    probable_duplicate_count: int,
) -> dict[str, object]:
    valid = [row for row in rows if row.get("status") != "error"]
    total = len(valid)
    average_width = _average(valid, "image_width")
    average_height = _average(valid, "image_height")
    average_megapixels = _average(valid, "megapixels")
    average_texture = _average(valid, "texture_score")
    average_artifact = _average(valid, "artifact_score")

    highest_artifact = sorted(
        (
            {
                "path": str(row["original_path"]),
                "artifact_score": float(row["artifact_score"]),
            }
            for row in valid
        ),
        key=lambda item: item["artifact_score"],
        reverse=True,
    )[:5]

    evidence = evidence_from_rows(valid)
    evidence.dataset_metrics.update(
        {
            "average_artifact_score": round(average_artifact, 2),
            "average_texture_score": round(average_texture, 2),
            "duplicate_count": duplicate_count,
            "probable_duplicate_count": probable_duplicate_count,
        }
    )
    return {
        "total_images": total,
        "duplicate_count": duplicate_count,
        "probable_duplicate_count": probable_duplicate_count,
        "average_resolution": {
            "width": round(average_width, 2),
            "height": round(average_height, 2),
            "megapixels": round(average_megapixels, 4),
        },
        "average_texture_score": round(average_texture, 2),
        "average_artifact_score": round(average_artifact, 2),
        "images_with_highest_artifact_scores": highest_artifact,
        "recommendations": recommend_dataset(evidence),
    }


def write_dataset_report(path: Path, report: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")


def _average(rows: list[dict[str, object]], field: str) -> float:
    if not rows:
        return 0.0
    return sum(float(row[field]) for row in rows) / len(rows)
