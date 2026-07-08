"""Inspection Manifest sidecar for deterministic inspect provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from dataset_forge import __version__
from dataset_forge.analyzer_descriptors import (
    AnalyzerDescriptor,
    descriptor_for_analyzer,
)
from dataset_forge.analyzers.base import Analyzer
from dataset_forge.finding import Finding
from dataset_forge.recommendation_summary import RECOMMENDATION_SUMMARY_SCHEMA
from dataset_forge.report import REPORT_SCHEMA
from dataset_forge.triage_dossier import TRIAGE_DOSSIER_SCHEMA

INSPECTION_MANIFEST_SCHEMA = "dataset-forge/inspection-manifest/v1"
INSPECTION_MANIFEST_FILENAME = "inspection_manifest.json"
MANIFEST_CONTRACT_VERSION = 1


@dataclass(frozen=True)
class InspectionProfile:
    id: str
    display_name: str
    version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "version": self.version,
        }


DEFAULT_INSPECTION_PROFILE = InspectionProfile(
    id="default",
    display_name="Default Inspection",
    version="v1",
)


def utc_now() -> str:
    """Return a UTC timestamp suitable for manifest provenance."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_inspection_manifest(
    *,
    dataset_path: Path,
    recursive: bool,
    limit: int | None,
    image_count: int,
    analyzed_count: int,
    error_count: int,
    analyzers: Iterable[Analyzer],
    findings: Iterable[Finding],
    started_at: str,
    completed_at: str,
    inspection_report_path: Path,
    recommendation_summary_path: Path,
    triage_dossiers_path: Path,
    profile: InspectionProfile = DEFAULT_INSPECTION_PROFILE,
) -> dict[str, Any]:
    """Build a deterministic Inspection Manifest payload."""

    finding_counts, finding_image_counts = _analyzer_finding_counts(findings)
    analyzer_rows = [
        _analyzer_manifest_row(
            descriptor_for_analyzer(analyzer),
            finding_counts,
            finding_image_counts,
        )
        for analyzer in analyzers
    ]

    return {
        "schema": INSPECTION_MANIFEST_SCHEMA,
        "tool": {
            "name": "dataset-forge",
            "version": __version__,
        },
        "inspection": {
            "profile": profile.to_dict(),
            "started_at": started_at,
            "completed_at": completed_at,
            "deterministic": True,
            "read_only": True,
        },
        "dataset": {
            "path": str(dataset_path),
            "recursive": recursive,
            "limit": limit,
            "image_count": image_count,
            "analyzed_count": analyzed_count,
            "error_count": error_count,
        },
        "sidecars": {
            "inspection_report": {
                "path": inspection_report_path.name,
                "schema": REPORT_SCHEMA,
            },
            "recommendation_summary": {
                "path": recommendation_summary_path.name,
                "schema": RECOMMENDATION_SUMMARY_SCHEMA,
            },
            "triage_dossiers": {
                "path": triage_dossiers_path.name,
                "schema": TRIAGE_DOSSIER_SCHEMA,
            },
        },
        "analyzers": analyzer_rows,
        "disabled_analyzers": [],
        "compatibility": {
            "inspection_report_schema": REPORT_SCHEMA,
            "recommendation_summary_schema": RECOMMENDATION_SUMMARY_SCHEMA,
            "manifest_contract_version": MANIFEST_CONTRACT_VERSION,
        },
    }


def write_inspection_manifest(
    output_dir: Path,
    manifest: Mapping[str, Any],
) -> Path:
    """Write inspection_manifest.json."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / INSPECTION_MANIFEST_FILENAME
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _analyzer_manifest_row(
    descriptor: AnalyzerDescriptor,
    finding_counts: Mapping[str, int],
    finding_image_counts: Mapping[str, int],
) -> dict[str, Any]:
    analyzer_id = f"{descriptor.id}/{descriptor.version}"
    return {
        "id": descriptor.id,
        "display_name": descriptor.display_name,
        "version": descriptor.version,
        "family": descriptor.family,
        "categories_emitted": list(descriptor.categories_emitted),
        "calibration_status": descriptor.calibration_status,
        "execution": {
            "policy": descriptor.default_execution_policy,
            "executed": True,
        },
        "display": {
            "policy": descriptor.default_display_policy,
        },
        "triage": {
            "policy": descriptor.default_triage_policy,
        },
        "finding_count": finding_counts.get(analyzer_id, 0),
        "image_count": finding_image_counts.get(analyzer_id, 0),
    }


def _analyzer_finding_counts(
    findings: Iterable[Finding],
) -> tuple[dict[str, int], dict[str, int]]:
    counts: dict[str, int] = {}
    images_by_analyzer: dict[str, set[str]] = {}
    for finding in findings:
        counts[finding.analyzer] = counts.get(finding.analyzer, 0) + 1
        images_by_analyzer.setdefault(finding.analyzer, set()).add(str(finding.image_path))
    image_counts = {
        analyzer: len(paths)
        for analyzer, paths in images_by_analyzer.items()
    }
    return counts, image_counts


__all__ = [
    "AnalyzerDescriptor",
    "DEFAULT_INSPECTION_PROFILE",
    "INSPECTION_MANIFEST_FILENAME",
    "INSPECTION_MANIFEST_SCHEMA",
    "InspectionProfile",
    "build_inspection_manifest",
    "descriptor_for_analyzer",
    "utc_now",
    "write_inspection_manifest",
]
