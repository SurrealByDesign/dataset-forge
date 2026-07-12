"""Improvement Preview artifact storage and read helpers.

This module stores manual imports or provider-generated candidate bytes in an
isolated inspect-output workspace and records transparent provenance. Image
processing belongs to providers; this module never modifies source images,
executes improvements, or exports datasets.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from dataset_forge import __version__
from dataset_forge.improvement_preview import IMPROVEMENT_PREVIEW_SCHEMA
from dataset_forge.preview_provider_contract import PreviewArtifactReference


PREVIEW_ARTIFACT_SCHEMA = "dataset-forge/preview-artifact/v1"
PREVIEW_ARTIFACTS_FILENAME = "preview_artifacts.json"
PREVIEW_ARTIFACTS_DIRECTORY = "preview_artifacts"

_SUPPORTED_FORMATS = {
    "BMP": ".bmp",
    "JPEG": ".jpg",
    "PNG": ".png",
    "TIFF": ".tiff",
    "WEBP": ".webp",
}


class PreviewArtifactError(ValueError):
    """Raised when a manual candidate cannot be safely imported."""


def import_manual_preview_candidate(
    inspect_output: Path,
    image_reference: Path | str,
    candidate_image: Path | str,
) -> dict[str, Any]:
    """Import one user-supplied candidate into an isolated preview workspace."""

    root = inspect_output.expanduser().resolve()
    preview_path = root / "improvement_preview.json"
    preview_before = _read_json_text(preview_path, "improvement_preview.json")
    preview = _parse_json_object(preview_before, "improvement_preview.json")
    _require_schema(preview, IMPROVEMENT_PREVIEW_SCHEMA, "improvement_preview.json")

    source_path = _resolve_existing_file(image_reference, "image reference")
    candidate_path = _resolve_existing_file(candidate_image, "candidate image")
    if candidate_path == source_path:
        raise PreviewArtifactError("candidate image must not be the source image itself")
    _reject_candidate_inside_artifact_root(root, candidate_path)

    plan_record = _find_plan_record(preview, source_path)
    preview_record_id = preview_plan_record_id(plan_record)
    source_metadata = _image_metadata(source_path, "source image")
    candidate_metadata = _image_metadata(candidate_path, "candidate image")
    if source_metadata["sha256"] == candidate_metadata["sha256"]:
        raise PreviewArtifactError(
            "candidate image has the same SHA-256 as the source image and provides no A/B value"
        )

    artifact_id = _artifact_id(preview_record_id, candidate_metadata["sha256"])
    artifact_reference = _artifact_reference(
        preview_record_id,
        candidate_metadata["sha256"],
        candidate_metadata["format"],
    )
    artifact_path = _artifact_path(root, artifact_reference)
    artifact_record = _artifact_record(
        artifact_id=artifact_id,
        preview_record_id=preview_record_id,
        source_path=source_path,
        source_metadata=source_metadata,
        candidate_original_filename=candidate_path.name,
        candidate_metadata=candidate_metadata,
        artifact_reference=artifact_reference,
        provider=_manual_provider_metadata(),
        event_key="imported_at",
        event_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        importer={"tool": "dataset-forge", "version": __version__},
    )

    artifacts_path = root / PREVIEW_ARTIFACTS_FILENAME
    artifacts_before = artifacts_path.read_bytes() if artifacts_path.is_file() else None
    artifacts = _load_artifact_sidecar(root)
    existing = _artifact_for_plan(artifacts["artifacts"], preview_record_id)

    copied = False
    if not artifact_path.is_file():
        _copy_candidate(candidate_path, artifact_path, candidate_metadata["sha256"], root)
        copied = True
    elif _sha256_file(artifact_path) != candidate_metadata["sha256"]:
        raise PreviewArtifactError("existing isolated artifact does not match candidate hash")

    if existing is not None and existing.get("candidate", {}).get("sha256") == candidate_metadata["sha256"]:
        return {
            "artifact": existing,
            "artifact_path": artifact_path,
            "imported": False,
            "idempotent": True,
        }

    next_artifacts = [
        item
        for item in artifacts["artifacts"]
        if item.get("preview_plan_record_id") != preview_record_id
    ]
    next_artifacts.append(artifact_record)
    next_artifacts.sort(key=lambda item: str(item.get("preview_plan_record_id", "")))
    next_payload = _artifact_sidecar(next_artifacts)
    next_preview = _update_preview_record(
        preview,
        preview_record_id,
        preview_status="READY",
        approval_state="NOT_REQUESTED",
    )

    try:
        _atomic_write_json(artifacts_path, next_payload)
        _atomic_write_json(preview_path, next_preview)
    except Exception:
        _restore_bytes(artifacts_path, artifacts_before)
        _atomic_write_bytes(preview_path, preview_before.encode("utf-8"))
        if copied:
            _remove_isolated_artifact(root, artifact_path)
        raise

    if existing is not None:
        _remove_prior_artifact(root, existing, artifact_path)

    return {
        "artifact": artifact_record,
        "artifact_path": artifact_path,
        "imported": True,
        "idempotent": False,
    }


def write_generated_preview_candidate(
    inspect_output: Path,
    image_reference: Path | str,
    candidate_bytes: bytes,
    *,
    candidate_filename: str,
    provider: Mapping[str, Any],
    generation: Mapping[str, Any],
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Store one generated candidate as an isolated preview artifact."""

    root = inspect_output.expanduser().resolve()
    preview_path = root / "improvement_preview.json"
    preview_before = _read_json_text(preview_path, "improvement_preview.json")
    preview = _parse_json_object(preview_before, "improvement_preview.json")
    _require_schema(preview, IMPROVEMENT_PREVIEW_SCHEMA, "improvement_preview.json")

    source_path = _resolve_existing_file(image_reference, "image reference")
    plan_record = _find_plan_record(preview, source_path)
    preview_record_id = preview_plan_record_id(plan_record)
    source_metadata = _image_metadata(source_path, "source image")
    candidate_metadata = _image_metadata_from_bytes(candidate_bytes, "generated candidate")
    if source_metadata["sha256"] == candidate_metadata["sha256"]:
        raise PreviewArtifactError(
            "generated candidate has the same SHA-256 as the source image and provides no A/B value"
        )

    artifact_id = _artifact_id(preview_record_id, candidate_metadata["sha256"])
    artifact_reference = _artifact_reference(
        preview_record_id,
        candidate_metadata["sha256"],
        candidate_metadata["format"],
    )
    artifact_path = _artifact_path(root, artifact_reference)
    artifact_record = _artifact_record(
        artifact_id=artifact_id,
        preview_record_id=preview_record_id,
        source_path=source_path,
        source_metadata=source_metadata,
        candidate_original_filename=candidate_filename,
        candidate_metadata=candidate_metadata,
        artifact_reference=artifact_reference,
        provider=provider,
        generation=generation,
    )

    artifacts_path = root / PREVIEW_ARTIFACTS_FILENAME
    artifacts_before = artifacts_path.read_bytes() if artifacts_path.is_file() else None
    artifacts = _load_artifact_sidecar(root)
    existing = _artifact_for_plan(artifacts["artifacts"], preview_record_id)
    if (
        existing is not None
        and existing.get("candidate", {}).get("sha256") == candidate_metadata["sha256"]
        and not replace_existing
    ):
        return {
            "artifact": existing,
            "artifact_path": artifact_path,
            "generated": False,
            "idempotent": True,
        }
    if existing is not None and not replace_existing:
        raise PreviewArtifactError(
            "a preview artifact already exists for this plan; pass --replace to replace it"
        )

    wrote_candidate = False
    if not artifact_path.is_file():
        _write_candidate_bytes(candidate_bytes, artifact_path, candidate_metadata["sha256"], root)
        wrote_candidate = True
    elif _sha256_file(artifact_path) != candidate_metadata["sha256"]:
        raise PreviewArtifactError("existing isolated artifact does not match generated candidate hash")

    next_artifacts = [
        item
        for item in artifacts["artifacts"]
        if item.get("preview_plan_record_id") != preview_record_id
    ]
    next_artifacts.append(artifact_record)
    next_artifacts.sort(key=lambda item: str(item.get("preview_plan_record_id", "")))
    next_payload = _artifact_sidecar(next_artifacts)
    next_preview = _update_preview_record(
        preview,
        preview_record_id,
        preview_status="READY",
        approval_state="NOT_REQUESTED",
    )

    try:
        _atomic_write_json(artifacts_path, next_payload)
        _atomic_write_json(preview_path, next_preview)
    except Exception:
        _restore_bytes(artifacts_path, artifacts_before)
        _atomic_write_bytes(preview_path, preview_before.encode("utf-8"))
        if wrote_candidate:
            _remove_isolated_artifact(root, artifact_path)
        raise

    if existing is not None:
        _remove_prior_artifact(root, existing, artifact_path)

    return {
        "artifact": artifact_record,
        "artifact_path": artifact_path,
        "generated": True,
        "idempotent": False,
    }


def load_preview_artifacts(inspect_output: Path) -> dict[str, Any]:
    """Load a validated artifact sidecar or return an empty optional payload."""

    root = inspect_output.expanduser().resolve()
    path = root / PREVIEW_ARTIFACTS_FILENAME
    if not path.is_file():
        return {
            "available": False,
            "schema": PREVIEW_ARTIFACT_SCHEMA,
            "artifacts": [],
        }
    try:
        payload = _load_artifact_sidecar(root)
    except PreviewArtifactError as exc:
        return {
            "available": True,
            "schema": None,
            "artifacts": [],
            "error": str(exc),
        }
    return {
        "available": True,
        "schema": PREVIEW_ARTIFACT_SCHEMA,
        "artifacts": payload["artifacts"],
    }


def resolve_preview_artifact(inspect_output: Path, artifact_id: str) -> Path | None:
    """Resolve one allow-listed candidate artifact without accepting a file path."""

    if not _is_artifact_id(artifact_id):
        return None
    root = inspect_output.expanduser().resolve()
    try:
        payload = _load_artifact_sidecar(root)
    except PreviewArtifactError:
        return None
    for artifact in payload["artifacts"]:
        if artifact.get("artifact_id") != artifact_id:
            continue
        return preview_artifact_path(root, artifact)
    return None


def preview_artifact_path(inspect_output: Path, artifact: Mapping[str, Any]) -> Path | None:
    """Return a verified isolated candidate path from already-loaded metadata."""

    root = inspect_output.expanduser().resolve()
    candidate = artifact.get("candidate")
    if not isinstance(candidate, Mapping):
        return None
    reference = candidate.get("artifact_reference")
    if not isinstance(reference, Mapping):
        return None
    try:
        path = _artifact_path(root, str(reference.get("relative_path", "")))
    except PreviewArtifactError:
        return None
    if not path.is_file() or _sha256_file(path) != candidate.get("sha256"):
        return None
    return path


def preview_plan_record_id(record: Mapping[str, Any]) -> str:
    """Return a stable identifier derived from one existing preview-plan record."""

    image_path = _record_image_path(record)
    if not image_path:
        raise PreviewArtifactError("preview-plan record is missing an image reference")
    normalized = {
        "image_path": _canonical_path_text(Path(image_path)),
        "recommended_operation": str(
            record.get("recommended_operation") or record.get("suggested_improvement") or ""
        ),
        "current_findings": _normalized_findings(record),
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "preview-" + hashlib.sha256(encoded).hexdigest()[:24]


def _find_plan_record(preview: Mapping[str, Any], source_path: Path) -> Mapping[str, Any]:
    records = _preview_records(preview)
    matches = []
    for record in records:
        image_path = _record_image_path(record)
        if image_path and _canonical_path_text(Path(image_path)) == _canonical_path_text(source_path):
            matches.append(record)
    if not matches:
        raise PreviewArtifactError("no Improvement Preview record matches the requested image reference")
    if len(matches) != 1:
        raise PreviewArtifactError(
            "multiple Improvement Preview records match this image reference; import is ambiguous"
        )
    return matches[0]


def _preview_records(preview: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = preview.get("preview_records")
    if not isinstance(records, list):
        records = preview.get("preview_entries", [])
    if not isinstance(records, list):
        raise PreviewArtifactError("improvement_preview.json records must be a list")
    return [item for item in records if isinstance(item, Mapping)]


def _record_image_path(record: Mapping[str, Any]) -> str:
    image = record.get("image")
    if isinstance(image, Mapping) and isinstance(image.get("path"), str):
        return str(image["path"])
    value = record.get("image_path")
    return str(value) if isinstance(value, str) else ""


def _normalized_findings(record: Mapping[str, Any]) -> list[dict[str, str]]:
    findings = record.get("current_findings")
    if not isinstance(findings, list):
        findings = record.get("triggering_findings", [])
    values = []
    for finding in findings if isinstance(findings, list) else []:
        if isinstance(finding, Mapping):
            values.append({
                "analyzer": str(finding.get("analyzer", "")),
                "category": str(finding.get("category", "")),
                "severity": str(finding.get("severity", "")),
            })
    return sorted(values, key=lambda item: (item["category"], item["analyzer"], item["severity"]))


def _artifact_id(preview_record_id: str, candidate_hash: str) -> str:
    value = f"{preview_record_id}:{candidate_hash}".encode("ascii")
    return "artifact-" + hashlib.sha256(value).hexdigest()[:24]


def _artifact_reference(preview_record_id: str, candidate_hash: str, image_format: str) -> str:
    extension = _SUPPORTED_FORMATS[image_format]
    reference = f"{PREVIEW_ARTIFACTS_DIRECTORY}/{preview_record_id}/candidate-{candidate_hash[:16]}{extension}"
    PreviewArtifactReference(relative_path=reference, media_type=f"image/{extension[1:]}")
    return reference


def _artifact_path(root: Path, relative_path: str) -> Path:
    try:
        reference = PreviewArtifactReference(
            relative_path=relative_path,
            media_type="application/octet-stream",
        )
    except ValueError as exc:
        raise PreviewArtifactError(str(exc)) from exc
    artifact_root_path = root / PREVIEW_ARTIFACTS_DIRECTORY
    logical_path = root / reference.relative_path
    _ensure_no_link_ancestor(logical_path.parent, root)
    artifact_root = artifact_root_path.resolve()
    path = logical_path.resolve()
    if not path.is_relative_to(artifact_root):
        raise PreviewArtifactError("preview artifact destination must remain inside preview_artifacts")
    return path


def _artifact_record(
    *,
    artifact_id: str,
    preview_record_id: str,
    source_path: Path,
    source_metadata: Mapping[str, Any],
    candidate_original_filename: str,
    candidate_metadata: Mapping[str, Any],
    artifact_reference: str,
    provider: Mapping[str, Any],
    event_key: str | None = None,
    event_timestamp: str | None = None,
    importer: Mapping[str, Any] | None = None,
    generation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "artifact_id": artifact_id,
        "preview_plan_record_id": preview_record_id,
        "image_reference": _canonical_path_text(source_path),
        "provider": dict(provider),
        "status": "READY",
        "candidate": {
            "original_filename": candidate_original_filename,
            "artifact_reference": PreviewArtifactReference(
                relative_path=artifact_reference,
                media_type=f"image/{candidate_metadata['format'].lower()}",
            ).to_dict(),
            **candidate_metadata,
        },
        "source": dict(source_metadata),
        "warnings": _warnings(source_metadata, candidate_metadata),
    }
    if event_key and event_timestamp:
        record[event_key] = event_timestamp
    if importer is not None:
        record["importer"] = dict(importer)
    if generation is not None:
        record["generation"] = dict(generation)
    return record


def _manual_provider_metadata() -> dict[str, Any]:
    return {
        "type": "MANUAL",
        "display_name": "Manual Import",
        "execution_available": False,
        "network_access": False,
        "credentials_required": False,
        "generative": False,
        "provenance_available": True,
    }


def _warnings(source: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[str]:
    warnings = []
    if (source["width"], source["height"]) != (candidate["width"], candidate["height"]):
        warnings.append("Candidate dimensions differ from the source image.")
    source_ratio = round(source["width"] / source["height"], 6)
    candidate_ratio = round(candidate["width"] / candidate["height"], 6)
    if source_ratio != candidate_ratio:
        warnings.append("Candidate aspect ratio differs from the source image.")
    if source["format"] != candidate["format"]:
        warnings.append("Candidate image format differs from the source image.")
    source_pixels = source["width"] * source["height"]
    candidate_pixels = candidate["width"] * candidate["height"]
    if source_pixels and (candidate_pixels / source_pixels > 1.5 or source_pixels / candidate_pixels > 1.5):
        warnings.append("Candidate pixel count differs substantially from the source image.")
    return warnings


def _image_metadata(path: Path, label: str) -> dict[str, Any]:
    if path.stat().st_size <= 0:
        raise PreviewArtifactError(f"{label} is empty: {path.name}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise PreviewArtifactError(f"{label} is not a readable supported image: {path.name}") from exc
    if image_format not in _SUPPORTED_FORMATS or width <= 0 or height <= 0:
        raise PreviewArtifactError(f"{label} has an unsupported image format: {path.name}")
    return {
        "sha256": _sha256_file(path),
        "byte_size": path.stat().st_size,
        "width": width,
        "height": height,
        "format": image_format,
    }


def _image_metadata_from_bytes(payload: bytes, label: str) -> dict[str, Any]:
    if not payload:
        raise PreviewArtifactError(f"{label} is empty")
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
        with Image.open(BytesIO(payload)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise PreviewArtifactError(f"{label} is not a readable supported image") from exc
    if image_format not in _SUPPORTED_FORMATS or width <= 0 or height <= 0:
        raise PreviewArtifactError(f"{label} has an unsupported image format")
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_size": len(payload),
        "width": width,
        "height": height,
        "format": image_format,
    }


def _resolve_existing_file(value: Path | str, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_file():
        raise PreviewArtifactError(f"{label} must be an existing file: {path}")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise PreviewArtifactError(f"{label} could not be resolved safely: {path}") from exc


def _canonical_path_text(path: Path) -> str:
    return str(path.expanduser().resolve()).replace("\\", "/")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_candidate(candidate: Path, destination: Path, expected_hash: str, root: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _ensure_no_link_ancestor(destination.parent, root)
    fd: int | None = None
    temporary = ""
    try:
        fd, temporary = tempfile.mkstemp(prefix=".candidate-", suffix=".tmp", dir=destination.parent)
        with os.fdopen(fd, "wb") as output, candidate.open("rb") as source:
            fd = None
            shutil.copyfileobj(source, output, length=1024 * 1024)
        temporary_path = Path(temporary)
        if _sha256_file(temporary_path) != expected_hash:
            raise PreviewArtifactError("candidate changed while it was being imported")
        os.replace(temporary_path, destination)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _write_candidate_bytes(payload: bytes, destination: Path, expected_hash: str, root: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _ensure_no_link_ancestor(destination.parent, root)
    fd: int | None = None
    temporary = ""
    try:
        fd, temporary = tempfile.mkstemp(prefix=".candidate-", suffix=".tmp", dir=destination.parent)
        with os.fdopen(fd, "wb") as output:
            fd = None
            output.write(payload)
        temporary_path = Path(temporary)
        if _sha256_file(temporary_path) != expected_hash:
            raise PreviewArtifactError("generated candidate changed while it was being stored")
        os.replace(temporary_path, destination)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _load_artifact_sidecar(root: Path) -> dict[str, Any]:
    path = root / PREVIEW_ARTIFACTS_FILENAME
    if not path.is_file():
        return _artifact_sidecar([])
    text = _read_json_text(path, PREVIEW_ARTIFACTS_FILENAME)
    payload = _parse_json_object(text, PREVIEW_ARTIFACTS_FILENAME)
    _require_schema(payload, PREVIEW_ARTIFACT_SCHEMA, PREVIEW_ARTIFACTS_FILENAME)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise PreviewArtifactError("preview_artifacts.json artifacts must be a list")
    normalized = []
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise PreviewArtifactError("preview_artifacts.json artifacts must be objects")
        normalized.append(dict(item))
    normalized.sort(key=lambda item: str(item.get("preview_plan_record_id", "")))
    return _artifact_sidecar(normalized)


def _artifact_sidecar(artifacts: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema": PREVIEW_ARTIFACT_SCHEMA,
        "tool_version": __version__,
        "deterministic_identity": True,
        "scope": {
            "isolated_preview_artifacts": True,
            "does_not_modify_source_images": True,
            "does_not_execute_improvements": True,
            "does_not_export_datasets": True,
            "candidate_artifacts_are_disposable": True,
        },
        "artifacts": [dict(item) for item in artifacts],
    }


def _artifact_for_plan(artifacts: list[Mapping[str, Any]], preview_record_id: str) -> dict[str, Any] | None:
    matches = [item for item in artifacts if item.get("preview_plan_record_id") == preview_record_id]
    if len(matches) > 1:
        raise PreviewArtifactError("preview_artifacts.json has duplicate records for one preview plan")
    return dict(matches[0]) if matches else None


def _update_preview_record(
    preview: Mapping[str, Any],
    preview_record_id: str,
    *,
    preview_status: str,
    approval_state: str,
) -> dict[str, Any]:
    next_preview = dict(preview)
    matched = False
    for key in ("preview_records", "preview_entries"):
        records = preview.get(key)
        if not isinstance(records, list):
            continue
        next_records = []
        for raw_record in records:
            if not isinstance(raw_record, Mapping):
                next_records.append(raw_record)
                continue
            next_record = dict(raw_record)
            if preview_plan_record_id(next_record) == preview_record_id:
                next_record["preview_status"] = preview_status
                next_record["approval_state"] = approval_state
                matched = True
            next_records.append(next_record)
        next_preview[key] = next_records
    if not matched:
        raise PreviewArtifactError("matched preview plan record could not be updated")
    summary = dict(next_preview.get("summary", {})) if isinstance(next_preview.get("summary"), Mapping) else {}
    summary["approval_state_counts"] = _approval_counts(_preview_records(next_preview))
    summary["preview_status_counts"] = _status_counts(_preview_records(next_preview))
    next_preview["summary"] = summary
    return next_preview


def _approval_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get("approval_state", ""))
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _status_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get("preview_status") or record.get("planning_status") or "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _remove_prior_artifact(root: Path, existing: Mapping[str, Any], current_path: Path) -> None:
    candidate = existing.get("candidate")
    if not isinstance(candidate, Mapping):
        return
    reference = candidate.get("artifact_reference")
    if not isinstance(reference, Mapping):
        return
    try:
        prior = _artifact_path(root, str(reference.get("relative_path", "")))
    except PreviewArtifactError:
        return
    if prior != current_path and prior.is_file():
        prior.unlink()


def _remove_isolated_artifact(root: Path, path: Path) -> None:
    artifact_root = (root / PREVIEW_ARTIFACTS_DIRECTORY).resolve()
    if path.is_relative_to(artifact_root) and path.is_file():
        path.unlink()


def _read_json_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise PreviewArtifactError(f"missing required {label}: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PreviewArtifactError(f"could not read {label}: {path}") from exc


def _parse_json_object(text: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreviewArtifactError(f"malformed JSON in {label}") from exc
    if not isinstance(payload, dict):
        raise PreviewArtifactError(f"{label} must be a JSON object")
    return payload


def _require_schema(payload: Mapping[str, Any], expected: str, label: str) -> None:
    if payload.get("schema") != expected:
        raise PreviewArtifactError(
            f"unsupported {label} schema {payload.get('schema')!r}; expected {expected!r}"
        )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_bytes(
        path,
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    temporary = ""
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _restore_bytes(path: Path, payload: bytes | None) -> None:
    if payload is None:
        if path.exists():
            path.unlink()
        return
    _atomic_write_bytes(path, payload)


def _reject_candidate_inside_artifact_root(root: Path, candidate: Path) -> None:
    artifact_root = root / PREVIEW_ARTIFACTS_DIRECTORY
    if not artifact_root.exists():
        return
    _ensure_no_link_ancestor(artifact_root, root)
    if candidate.resolve(strict=True).is_relative_to(artifact_root.resolve()):
        raise PreviewArtifactError("candidate image must be outside the isolated preview artifact workspace")


def _ensure_no_link_ancestor(path: Path, root: Path) -> None:
    root = root.resolve()
    current = path.absolute()
    candidates = []
    while True:
        candidates.append(current)
        if current == root or current.parent == current:
            break
        current = current.parent
    for candidate in reversed(candidates):
        if _is_link_or_junction(candidate):
            raise PreviewArtifactError(
                "preview artifact paths must not pass through symlinks or junctions"
            )


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _is_artifact_id(value: str) -> bool:
    return (
        value.startswith("artifact-")
        and len(value) == len("artifact-") + 24
        and all(character in "0123456789abcdef" for character in value[len("artifact-"):])
    )


__all__ = [
    "PREVIEW_ARTIFACT_SCHEMA",
    "PREVIEW_ARTIFACTS_DIRECTORY",
    "PREVIEW_ARTIFACTS_FILENAME",
    "PreviewArtifactError",
    "import_manual_preview_candidate",
    "load_preview_artifacts",
    "preview_artifact_path",
    "preview_plan_record_id",
    "resolve_preview_artifact",
    "write_generated_preview_candidate",
]
