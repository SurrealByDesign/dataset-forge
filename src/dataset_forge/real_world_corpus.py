"""Validation helpers for the optional real-world validation corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.calibration_evidence import load_calibration_labels


REAL_WORLD_CORPUS_SCHEMA = "dataset-forge/real-world-validation-corpus/v1"
REAL_WORLD_CORPUS_VALIDATION_SCHEMA = (
    "dataset-forge/real-world-validation-corpus-result/v1"
)

_MANIFEST_KEYS = {"schema", "corpus_name", "version", "description", "groups"}
_GROUP_KEYS = {
    "id",
    "title",
    "visibility",
    "fixture_kind",
    "description",
    "labels_path",
    "review_decisions_path",
    "expected_dossier_path",
    "cases",
}
_CASE_KEYS = {
    "image_id",
    "image_path",
    "license",
    "source",
    "committed",
    "optional",
}
_VISIBILITIES = {"public", "private"}
_FIXTURE_KINDS = {"real_world", "placeholder_synthetic"}


@dataclass(frozen=True)
class RealWorldCorpusCase:
    image_id: str
    image_path: str
    license: str
    source: str
    committed: bool
    optional: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "image_path": self.image_path,
            "license": self.license,
            "source": self.source,
            "committed": self.committed,
            "optional": self.optional,
        }


@dataclass(frozen=True)
class RealWorldCorpusGroup:
    id: str
    title: str
    visibility: str
    fixture_kind: str
    description: str
    labels_path: str
    review_decisions_path: str | None
    expected_dossier_path: str | None
    cases: tuple[RealWorldCorpusCase, ...]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "visibility": self.visibility,
            "fixture_kind": self.fixture_kind,
            "description": self.description,
            "labels_path": self.labels_path,
            "cases": [case.to_dict() for case in self.cases],
        }
        if self.review_decisions_path is not None:
            payload["review_decisions_path"] = self.review_decisions_path
        if self.expected_dossier_path is not None:
            payload["expected_dossier_path"] = self.expected_dossier_path
        return payload


@dataclass(frozen=True)
class RealWorldCorpusManifest:
    schema: str
    corpus_name: str
    version: str
    description: str
    groups: tuple[RealWorldCorpusGroup, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "corpus_name": self.corpus_name,
            "version": self.version,
            "description": self.description,
            "groups": [group.to_dict() for group in self.groups],
        }


@dataclass(frozen=True)
class RealWorldCorpusValidationResult:
    manifest_path: str
    group_count: int
    case_count: int
    existing_committed_case_count: int
    skipped_optional_case_count: int
    label_file_count: int
    expected_file_count: int
    missing_required_paths: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_required_paths

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REAL_WORLD_CORPUS_VALIDATION_SCHEMA,
            "manifest_path": self.manifest_path,
            "group_count": self.group_count,
            "case_count": self.case_count,
            "existing_committed_case_count": self.existing_committed_case_count,
            "skipped_optional_case_count": self.skipped_optional_case_count,
            "label_file_count": self.label_file_count,
            "expected_file_count": self.expected_file_count,
            "missing_required_paths": list(self.missing_required_paths),
            "is_valid": self.is_valid,
        }


def load_real_world_corpus_manifest(path: Path) -> RealWorldCorpusManifest:
    """Load and validate a real-world corpus manifest JSON file."""

    with path.open("r", encoding="utf-8") as f:
        return parse_real_world_corpus_manifest(json.load(f))


def parse_real_world_corpus_manifest(data: dict[str, Any]) -> RealWorldCorpusManifest:
    """Parse a schema-versioned validation corpus manifest."""

    _reject_unknown_keys(data, _MANIFEST_KEYS, "manifest")
    if data.get("schema") != REAL_WORLD_CORPUS_SCHEMA:
        raise ValueError(
            f"Unsupported real-world corpus schema {data.get('schema')!r}; "
            f"expected {REAL_WORLD_CORPUS_SCHEMA!r}"
        )

    corpus_name = _required_str(data, "corpus_name", "manifest")
    version = _required_str(data, "version", "manifest")
    description = _required_str(data, "description", "manifest")
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ValueError("manifest groups must be a non-empty list")

    groups = tuple(_parse_group(raw_group, index) for index, raw_group in enumerate(raw_groups))
    return RealWorldCorpusManifest(
        schema=REAL_WORLD_CORPUS_SCHEMA,
        corpus_name=corpus_name,
        version=version,
        description=description,
        groups=groups,
    )


def validate_real_world_corpus(manifest_path: Path) -> RealWorldCorpusValidationResult:
    """Validate committed corpus paths and skip optional private fixtures cleanly."""

    manifest = load_real_world_corpus_manifest(manifest_path)
    root = manifest_path.parent
    missing: list[str] = []
    existing_committed = 0
    skipped_optional = 0
    label_files = 0
    expected_files = 0

    for group in manifest.groups:
        group_required = group.visibility == "public"
        labels_path = _resolve(root, group.labels_path)
        if labels_path.exists():
            load_calibration_labels(labels_path)
            label_files += 1
        elif group_required:
            missing.append(group.labels_path)
        else:
            skipped_optional += 1

        for optional_path in (
            group.review_decisions_path,
            group.expected_dossier_path,
        ):
            if optional_path is None:
                continue
            resolved = _resolve(root, optional_path)
            if resolved.exists():
                if optional_path == group.expected_dossier_path:
                    expected_files += 1
            elif group_required:
                missing.append(optional_path)
            else:
                skipped_optional += 1

        for case in group.cases:
            resolved = _resolve(root, case.image_path)
            if resolved.exists():
                if case.committed:
                    existing_committed += 1
            elif case.optional or group.visibility == "private":
                skipped_optional += 1
            else:
                missing.append(case.image_path)

    return RealWorldCorpusValidationResult(
        manifest_path=str(manifest_path),
        group_count=len(manifest.groups),
        case_count=sum(len(group.cases) for group in manifest.groups),
        existing_committed_case_count=existing_committed,
        skipped_optional_case_count=skipped_optional,
        label_file_count=label_files,
        expected_file_count=expected_files,
        missing_required_paths=tuple(sorted(missing)),
    )


def _parse_group(data: Any, index: int) -> RealWorldCorpusGroup:
    context = f"group[{index}]"
    if not isinstance(data, dict):
        raise ValueError(f"{context} must be an object")
    _reject_unknown_keys(data, _GROUP_KEYS, context)

    visibility = _required_str(data, "visibility", context)
    if visibility not in _VISIBILITIES:
        raise ValueError(f"{context}.visibility must be one of {sorted(_VISIBILITIES)}")
    fixture_kind = _required_str(data, "fixture_kind", context)
    if fixture_kind not in _FIXTURE_KINDS:
        raise ValueError(
            f"{context}.fixture_kind must be one of {sorted(_FIXTURE_KINDS)}"
        )

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{context}.cases must be a non-empty list")

    return RealWorldCorpusGroup(
        id=_required_str(data, "id", context),
        title=_required_str(data, "title", context),
        visibility=visibility,
        fixture_kind=fixture_kind,
        description=_required_str(data, "description", context),
        labels_path=_required_str(data, "labels_path", context),
        review_decisions_path=_optional_str(data, "review_decisions_path", context),
        expected_dossier_path=_optional_str(data, "expected_dossier_path", context),
        cases=tuple(_parse_case(raw_case, context, i) for i, raw_case in enumerate(raw_cases)),
    )


def _parse_case(data: Any, group_context: str, index: int) -> RealWorldCorpusCase:
    context = f"{group_context}.cases[{index}]"
    if not isinstance(data, dict):
        raise ValueError(f"{context} must be an object")
    _reject_unknown_keys(data, _CASE_KEYS, context)

    return RealWorldCorpusCase(
        image_id=_required_str(data, "image_id", context),
        image_path=_required_str(data, "image_path", context),
        license=_required_str(data, "license", context),
        source=_required_str(data, "source", context),
        committed=_required_bool(data, "committed", context),
        optional=_required_bool(data, "optional", context),
    )


def _reject_unknown_keys(
    data: dict[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def _required_str(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _optional_str(data: dict[str, Any], key: str, context: str) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"{context}.{key} must be a non-empty string or null")
    return value


def _required_bool(data: dict[str, Any], key: str, context: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path
