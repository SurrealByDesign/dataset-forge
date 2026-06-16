from __future__ import annotations

import csv
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataset_forge.cleanup.controls import APPROVED_PLAN_JSON, _latest_manifest
from dataset_forge.cleanup.models import CleanupAction
from dataset_forge.cleanup.profiles import CleanupProfile, load_cleanup_profile
from dataset_forge.cleanup.safety import require_approved_plan
from dataset_forge.cleanup.traditional import (
    generate_comparison_sheet,
    process_traditional_cleanup,
)
from dataset_forge.core.structured import load_structured_file
from dataset_forge.plugins.builtin.traditional_cleanup import (
    TraditionalCleanupTransform,
    write_traditional_cleanup_sidecar,
)
from dataset_forge.resources import ResourceManager
from dataset_forge.transforms.base import Transform

EXECUTION_REPORT_JSON = "execution_report.json"
EXECUTION_REPORT_CSV = "execution_report.csv"
PROCESSED_DIR = "processed"
PRECLEANUP_DIR = "precleanup"
TRANSFORMS = ("placeholder", "traditional_cleanup")

ELIGIBLE_ACTIONS = {
    CleanupAction.CLEAN_LIGHT.value: "clean_light",
    CleanupAction.CLEAN_MEDIUM.value: "clean_medium",
    CleanupAction.CLEAN_STRONG.value: "clean_strong",
    CleanupAction.CAPTION_ONLY.value: "caption_only",
}

REPORT_FIELDS = (
    "image_id",
    "filename",
    "action",
    "source_path",
    "output_path",
    "plugin_id",
    "status",
    "started_at",
    "completed_at",
    "duration",
    "skipped_reason",
    "error",
)


class PlaceholderCleanupTransform(Transform):
    """Safety-test transform that copies the source image unchanged."""

    name = "placeholder_cleanup"
    description = (
        "Safety-test placeholder transform. Copies the source image "
        "unchanged into the output folder and records that no real "
        "cleanup, captioning, or model processing was performed."
    )
    input_requirements = ("source_image",)
    output_type = "image"
    parameters: dict[str, Any] = {}

    def run(
        self,
        input_path: Path,
        output_path: Path,
        **parameters: Any,
    ) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, output_path)
        metadata_path = output_path.with_name(output_path.name + ".json")
        metadata = {
            "transform": self.name,
            "placeholder": True,
            "note": (
                "This file is an unmodified copy of the source image. "
                "No cleanup, captioning, or model processing was performed."
            ),
            "source_path": str(input_path),
            "action": parameters.get("action"),
            "image_id": parameters.get("image_id"),
            "filename": parameters.get("filename"),
        }
        metadata_path.write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        return {
            "output_path": output_path,
            "metadata_path": metadata_path,
            "bytes_written": output_path.stat().st_size,
        }


def _run_traditional_cleanup(
    input_path: Path,
    output_path: Path,
    profile: CleanupProfile,
) -> dict[str, Any]:
    if profile.acceptance_checks:
        return process_traditional_cleanup(input_path, output_path, profile)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_path)
    metadata_path = write_traditional_cleanup_sidecar(input_path, output_path, profile)
    return {
        "output_path": output_path,
        "metadata_path": metadata_path,
        "bytes_written": output_path.stat().st_size,
    }


@dataclass(frozen=True)
class ExecutionSummary:
    approved_items: int
    executed: int
    skipped: int
    failed: int
    processed_dir: Path
    total_disk_written: int
    records: tuple[dict[str, Any], ...]
    dry_run: bool
    transform: str = "placeholder"
    cleanup_profile: str | None = None
    requested_operations: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved_items": self.approved_items,
            "executed": self.executed,
            "skipped": self.skipped,
            "failed": self.failed,
            "processed_dir": str(self.processed_dir),
            "output_location": str(self.processed_dir),
            "total_disk_written": self.total_disk_written,
            "transform": self.transform,
            "cleanup_profile": self.cleanup_profile,
            "requested_operations": list(self.requested_operations),
            "placeholder_execution": True,
            "records": list(self.records),
        }


def execute_plan(
    output_path: Path,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool = False,
    profile: str = "balanced",
    profile_config: Path | None = None,
    resume: bool = True,
    transform: str = "placeholder",
    cleanup_profile: str | Path = "watercolor_light",
) -> ExecutionSummary:
    resolved = output_path.expanduser().resolve()

    if transform not in TRANSFORMS:
        raise ValueError(
            f"Unknown transform: {transform}. Expected one of: {', '.join(TRANSFORMS)}."
        )

    # Safety gate: refuses to proceed unless every decision is resolved.
    require_approved_plan(resolved)

    plan = load_structured_file(resolved / APPROVED_PLAN_JSON)

    # Reserved for future parallel execution; currently processed sequentially.
    resource_manager = ResourceManager.from_profile(
        profile, profile_config=profile_config
    )
    _ = resource_manager.worker_count

    loaded_profile: CleanupProfile | None = None
    if transform == "traditional_cleanup":
        loaded_profile = load_cleanup_profile(cleanup_profile)

    source_paths = _load_source_paths(resolved)
    processed_dir = resolved / (
        PRECLEANUP_DIR if transform == "traditional_cleanup" else PROCESSED_DIR
    )
    plugin_id = (
        TraditionalCleanupTransform.id
        if transform == "traditional_cleanup"
        else PlaceholderCleanupTransform.name
    )
    previous_records = (
        {} if force or not resume else _load_previous_records(resolved)
    )

    records: list[dict[str, Any]] = []
    approved_items = 0
    executed = 0
    total_disk_written = 0

    for decision in plan.get("decisions", []):
        image_id = str(decision.get("image_id", ""))
        filename = str(decision.get("filename", ""))
        action = str(decision.get("action", ""))
        approval_status = str(decision.get("approval_status", "proposed"))
        execution_eligible = bool(decision.get("execution_eligible", False))

        record: dict[str, Any] = {
            "image_id": image_id,
            "filename": filename,
            "action": action,
            "source_path": "",
            "output_path": "",
            "plugin_id": plugin_id,
            "status": "skipped",
            "started_at": "",
            "completed_at": "",
            "duration": 0.0,
            "skipped_reason": "",
            "error": "",
        }

        if action not in ELIGIBLE_ACTIONS:
            record["skipped_reason"] = f"action not eligible for execution: {action}"
            records.append(record)
            continue
        if approval_status == "rejected":
            record["skipped_reason"] = "decision rejected"
            records.append(record)
            continue
        if not execution_eligible:
            record["skipped_reason"] = "decision not approved or locked"
            records.append(record)
            continue

        approved_items += 1
        suffix = ELIGIBLE_ACTIONS[action]

        source_path = source_paths.get(filename)
        if source_path is None:
            record.update(
                {
                    "status": "failed",
                    "error": f"Source image not found in manifest: {filename}",
                    "started_at": _timestamp(),
                    "completed_at": _timestamp(),
                }
            )
            records.append(record)
            continue
        record["source_path"] = str(source_path)

        previous = previous_records.get((image_id, action))
        if (
            previous
            and previous.get("status") == "completed"
            and previous.get("output_path")
            and Path(str(previous["output_path"])).is_file()
        ):
            record.update(
                {
                    "output_path": str(previous["output_path"]),
                    "status": "skipped",
                    "skipped_reason": "already completed (resume)",
                }
            )
            records.append(record)
            continue

        target_path = _resolve_output_path(processed_dir, source_path, suffix)
        record["output_path"] = str(target_path)

        if limit is not None and executed >= limit:
            record["skipped_reason"] = "execution limit reached"
            records.append(record)
            continue

        if dry_run:
            record.update(
                {
                    "status": "dry-run",
                    "skipped_reason": "dry-run: no files written",
                }
            )
            records.append(record)
            executed += 1
            continue

        started = _timestamp()
        start_perf = time.perf_counter()
        try:
            if transform == "traditional_cleanup":
                assert loaded_profile is not None
                result = _run_traditional_cleanup(
                    source_path, target_path, loaded_profile
                )
            else:
                result = PlaceholderCleanupTransform().run(
                    source_path,
                    target_path,
                    action=action,
                    image_id=image_id,
                    filename=filename,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            record.update(
                {
                    "status": "failed",
                    "started_at": started,
                    "completed_at": _timestamp(),
                    "duration": round(time.perf_counter() - start_perf, 6),
                    "error": str(exc),
                }
            )
            records.append(record)
            continue

        accepted = result.get("accepted", True)
        record.update(
            {
                "output_path": (
                    str(result["output_path"])
                    if accepted and result.get("output_path")
                    else ""
                ),
                "status": "completed" if accepted else "rejected",
                "started_at": started,
                "completed_at": _timestamp(),
                "duration": round(time.perf_counter() - start_perf, 6),
                "skipped_reason": (
                    "" if accepted else str(result.get("rejection_reason", ""))
                ),
            }
        )
        total_disk_written += int(result.get("bytes_written", 0))
        executed += 1
        records.append(record)

    skipped = sum(1 for item in records if item["status"] == "skipped")
    failed = sum(1 for item in records if item["status"] == "failed")
    executed_total = sum(
        1
        for item in records
        if item["status"] in {"completed", "rejected", "dry-run"}
    )

    summary = ExecutionSummary(
        approved_items=approved_items,
        executed=executed_total,
        skipped=skipped,
        failed=failed,
        processed_dir=processed_dir,
        total_disk_written=total_disk_written,
        records=tuple(records),
        dry_run=dry_run,
        transform=transform,
        cleanup_profile=loaded_profile.name if loaded_profile else None,
        requested_operations=(
            tuple(op.to_dict() for op in loaded_profile.operations)
            if loaded_profile
            else ()
        ),
    )

    if not dry_run:
        if (
            transform == "traditional_cleanup"
            and loaded_profile is not None
            and loaded_profile.acceptance_checks
        ):
            generate_comparison_sheet(processed_dir)
        _write_execution_report(resolved, summary)

    return summary


def _resolve_output_path(processed_dir: Path, source_path: Path, suffix: str) -> Path:
    stem = source_path.stem
    ext = source_path.suffix
    candidate = processed_dir / f"{stem}_{suffix}{ext}"
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = processed_dir / f"{stem}_{suffix}_{counter}{ext}"
    return candidate


def _load_source_paths(output_path: Path) -> dict[str, Path]:
    manifest_path = _latest_manifest(output_path)
    if manifest_path is None:
        return {}
    mapping: dict[str, Path] = {}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            filename = str(row.get("filename", ""))
            original = str(row.get("original_path", ""))
            if filename and original:
                mapping[filename] = Path(original)
    return mapping


def _load_previous_records(output_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    path = output_path / EXECUTION_REPORT_JSON
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    records = data.get("records", [])
    if not isinstance(records, list):
        return {}
    return {
        (str(item.get("image_id")), str(item.get("action"))): item
        for item in records
        if isinstance(item, dict)
    }


def _write_execution_report(
    output_path: Path, summary: ExecutionSummary
) -> tuple[Path, Path]:
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / EXECUTION_REPORT_JSON
    csv_path = output_path / EXECUTION_REPORT_CSV
    json_path.write_text(
        json.dumps(summary.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for record in summary.records:
            writer.writerow({field: record.get(field, "") for field in REPORT_FIELDS})
    return json_path, csv_path


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
