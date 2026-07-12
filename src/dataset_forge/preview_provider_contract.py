"""Provider-neutral contracts for future Improvement Preview rendering.

This module contains immutable metadata, validation, and deterministic
capability matching only. It has no provider implementations, networking,
subprocess, image-processing, credential, or execution paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


PROVIDER_LOCAL_CLASSICAL = "LOCAL_CLASSICAL"
PROVIDER_COMFYUI = "COMFYUI"
PROVIDER_KREA = "KREA"
PROVIDER_MANUAL = "MANUAL"
PROVIDER_UNKNOWN = "UNKNOWN"
PROVIDER_TYPES = (
    PROVIDER_LOCAL_CLASSICAL,
    PROVIDER_COMFYUI,
    PROVIDER_KREA,
    PROVIDER_MANUAL,
    PROVIDER_UNKNOWN,
)

AVAILABILITY_DESCRIPTOR_ONLY = "descriptor_only"
AVAILABILITY_UNKNOWN = "unknown"
AVAILABILITY_STATES = (
    AVAILABILITY_DESCRIPTOR_ONLY,
    AVAILABILITY_UNKNOWN,
)

IMPLEMENTATION_NOT_IMPLEMENTED = "not_implemented"
IMPLEMENTATION_LOCAL_PREVIEW_AVAILABLE = "local_preview_available"
IMPLEMENTATION_STATUSES = (
    IMPLEMENTATION_NOT_IMPLEMENTED,
    IMPLEMENTATION_LOCAL_PREVIEW_AVAILABLE,
)

CAPABILITY_IMAGE_INPUT = "image_input"
CAPABILITY_MASK_INPUT = "mask_input"
CAPABILITY_SEED = "seed"
CAPABILITY_DETERMINISTIC_EXECUTION = "deterministic_execution"
CAPABILITY_PARAMETER_PROVENANCE = "parameter_provenance"
CAPABILITY_CANDIDATE_IMAGE_OUTPUT = "candidate_image_output"
CAPABILITY_DIFFERENCE_METADATA = "difference_metadata"
CAPABILITY_METADATA_ONLY_MANUAL_IMPORT = "metadata_only_manual_import"
CAPABILITY_IDS = (
    CAPABILITY_IMAGE_INPUT,
    CAPABILITY_MASK_INPUT,
    CAPABILITY_SEED,
    CAPABILITY_DETERMINISTIC_EXECUTION,
    CAPABILITY_PARAMETER_PROVENANCE,
    CAPABILITY_CANDIDATE_IMAGE_OUTPUT,
    CAPABILITY_DIFFERENCE_METADATA,
    CAPABILITY_METADATA_ONLY_MANUAL_IMPORT,
)

MATCH_COMPATIBLE = "compatible"
MATCH_INCOMPATIBLE = "incompatible"
MATCH_UNKNOWN_PROVIDER = "unknown_provider"
MATCH_STATUSES = (
    MATCH_COMPATIBLE,
    MATCH_INCOMPATIBLE,
    MATCH_UNKNOWN_PROVIDER,
)

RESULT_NOT_EXECUTED = "NOT_EXECUTED"
RESULT_SUCCEEDED = "SUCCEEDED"
RESULT_FAILED = "FAILED"
RESULT_REJECTED = "REJECTED"
RESULT_STATUSES = (
    RESULT_NOT_EXECUTED,
    RESULT_SUCCEEDED,
    RESULT_FAILED,
    RESULT_REJECTED,
)

ARTIFACT_SCOPE_ISOLATED_PREVIEW_OUTPUT = "isolated_preview_output"

CURRENT_OPERATIONS = (
    "KEEP",
    "MANUAL_CAPTION",
    "REMOVE_DUPLICATE",
    "REPLACE_SOURCE",
    "REDUCE_HALO",
    "REDUCE_ENCODING_ARTIFACTS",
    "NO_ACTION",
)

JsonScalar = str | int | float | bool | None


class PreviewProviderContractError(ValueError):
    """Raised when provider contract data violates the v1 contract."""


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise PreviewProviderContractError(f"{field_name} must be non-empty plain text")


def _require_known(value: str, allowed: tuple[str, ...], field_name: str) -> None:
    if value not in allowed:
        raise PreviewProviderContractError(
            f"Unsupported {field_name} {value!r}; expected one of {allowed!r}"
        )


def _stable_strings(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    for value in values:
        _require_nonempty(value, field_name)
    return tuple(sorted(set(values)))


def _stable_parameters(
    values: tuple[tuple[str, JsonScalar], ...],
    field_name: str,
) -> tuple[tuple[str, JsonScalar], ...]:
    keys: set[str] = set()
    normalized = []
    for key, value in values:
        _require_nonempty(key, field_name)
        if key in keys:
            raise PreviewProviderContractError(f"Duplicate {field_name} key: {key}")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise PreviewProviderContractError(
                f"{field_name} values must be JSON scalar values"
            )
        keys.add(key)
        normalized.append((key, value))
    return tuple(sorted(normalized, key=lambda item: item[0]))


@dataclass(frozen=True)
class PreviewProviderCapabilities:
    """Conservative capability claims for a future provider implementation."""

    image_input: bool = False
    mask_input: bool = False
    seed: bool = False
    deterministic_execution: bool = False
    parameter_provenance: bool = False
    candidate_image_output: bool = False
    difference_metadata: bool = False
    metadata_only_manual_import: bool = False

    def supported_ids(self) -> tuple[str, ...]:
        values = {
            CAPABILITY_IMAGE_INPUT: self.image_input,
            CAPABILITY_MASK_INPUT: self.mask_input,
            CAPABILITY_SEED: self.seed,
            CAPABILITY_DETERMINISTIC_EXECUTION: self.deterministic_execution,
            CAPABILITY_PARAMETER_PROVENANCE: self.parameter_provenance,
            CAPABILITY_CANDIDATE_IMAGE_OUTPUT: self.candidate_image_output,
            CAPABILITY_DIFFERENCE_METADATA: self.difference_metadata,
            CAPABILITY_METADATA_ONLY_MANUAL_IMPORT: self.metadata_only_manual_import,
        }
        return tuple(key for key in CAPABILITY_IDS if values[key])

    def to_dict(self) -> dict[str, bool]:
        return {
            "image_input": self.image_input,
            "mask_input": self.mask_input,
            "seed": self.seed,
            "deterministic_execution": self.deterministic_execution,
            "parameter_provenance": self.parameter_provenance,
            "candidate_image_output": self.candidate_image_output,
            "difference_metadata": self.difference_metadata,
            "metadata_only_manual_import": self.metadata_only_manual_import,
        }


@dataclass(frozen=True)
class PreviewProviderDescriptor:
    """Deterministic metadata for a provider type; never an executable hook."""

    provider_id: str
    display_name: str
    provider_version: str
    provider_type: str
    supported_operations: tuple[str, ...]
    availability_state: str
    deterministic: bool
    remote: bool
    requires_network: bool
    requires_credentials: bool
    supports_seed: bool
    supports_reproducible_parameters: bool
    supports_difference_metadata: bool
    implementation_status: str
    capabilities: PreviewProviderCapabilities

    def __post_init__(self) -> None:
        _require_nonempty(self.provider_id, "provider_id")
        _require_nonempty(self.display_name, "display_name")
        _require_nonempty(self.provider_version, "provider_version")
        _require_known(self.provider_type, PROVIDER_TYPES, "provider_type")
        _require_known(
            self.availability_state,
            AVAILABILITY_STATES,
            "availability_state",
        )
        _require_known(
            self.implementation_status,
            IMPLEMENTATION_STATUSES,
            "implementation_status",
        )
        operations = _stable_strings(self.supported_operations, "supported_operation")
        unknown = sorted(set(operations) - set(CURRENT_OPERATIONS))
        if unknown:
            raise PreviewProviderContractError(
                f"Unsupported provider operations: {', '.join(unknown)}"
            )
        object.__setattr__(self, "supported_operations", operations)
        if self.supports_seed != self.capabilities.seed:
            raise PreviewProviderContractError(
                "supports_seed must match capabilities.seed"
            )
        if (
            self.supports_reproducible_parameters
            != self.capabilities.parameter_provenance
        ):
            raise PreviewProviderContractError(
                "supports_reproducible_parameters must match "
                "capabilities.parameter_provenance"
            )
        if self.supports_difference_metadata != self.capabilities.difference_metadata:
            raise PreviewProviderContractError(
                "supports_difference_metadata must match "
                "capabilities.difference_metadata"
            )
        if self.deterministic and not self.capabilities.deterministic_execution:
            raise PreviewProviderContractError(
                "deterministic providers must claim deterministic_execution"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "provider_version": self.provider_version,
            "provider_type": self.provider_type,
            "supported_operations": list(self.supported_operations),
            "availability_state": self.availability_state,
            "deterministic": self.deterministic,
            "location": "remote" if self.remote else "local",
            "requires_network": self.requires_network,
            "requires_credentials": self.requires_credentials,
            "supports_seed": self.supports_seed,
            "supports_reproducible_parameters": self.supports_reproducible_parameters,
            "supports_difference_metadata": self.supports_difference_metadata,
            "implementation_status": self.implementation_status,
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass(frozen=True)
class ProviderExecutionPolicy:
    """Safety requirements for any separately scoped future execution layer."""

    source_dataset_writes_forbidden: bool = True
    source_image_overwrite_forbidden: bool = True
    isolated_output_required: bool = True
    human_approval_required: bool = True
    execution_available: bool = False
    remote_provider_disclosure_required: bool = True
    generative_provider_warning_required: bool = True
    provenance_required: bool = True

    def __post_init__(self) -> None:
        required_true = (
            self.source_dataset_writes_forbidden,
            self.source_image_overwrite_forbidden,
            self.isolated_output_required,
            self.human_approval_required,
            self.remote_provider_disclosure_required,
            self.generative_provider_warning_required,
            self.provenance_required,
        )
        if not all(required_true) or self.execution_available:
            raise PreviewProviderContractError(
                "v1.7 execution policy must preserve all safety requirements "
                "and keep execution unavailable"
            )

    def to_dict(self) -> dict[str, bool]:
        return {
            "source_dataset_writes_forbidden": self.source_dataset_writes_forbidden,
            "source_image_overwrite_forbidden": self.source_image_overwrite_forbidden,
            "isolated_output_required": self.isolated_output_required,
            "human_approval_required": self.human_approval_required,
            "execution_available": self.execution_available,
            "remote_provider_disclosure_required": self.remote_provider_disclosure_required,
            "generative_provider_warning_required": self.generative_provider_warning_required,
            "provenance_required": self.provenance_required,
        }


@dataclass(frozen=True)
class PreviewArtifactReference:
    """Reference to an artifact isolated from the source dataset."""

    relative_path: str
    media_type: str
    role: str = "candidate_preview"
    storage_scope: str = ARTIFACT_SCOPE_ISOLATED_PREVIEW_OUTPUT

    def __post_init__(self) -> None:
        _require_nonempty(self.relative_path, "relative_path")
        _require_nonempty(self.media_type, "media_type")
        _require_nonempty(self.role, "role")
        if self.storage_scope != ARTIFACT_SCOPE_ISOLATED_PREVIEW_OUTPUT:
            raise PreviewProviderContractError(
                "Preview artifacts must use isolated_preview_output storage"
            )
        posix_path = PurePosixPath(self.relative_path.replace("\\", "/"))
        windows_path = PureWindowsPath(self.relative_path)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or ":" in self.relative_path
            or ".." in posix_path.parts
        ):
            raise PreviewProviderContractError(
                "Preview artifact paths must be relative and cannot escape isolated output"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "relative_path": self.relative_path.replace("\\", "/"),
            "media_type": self.media_type,
            "role": self.role,
            "storage_scope": self.storage_scope,
        }


@dataclass(frozen=True)
class PreviewRequest:
    """Provider-neutral data for a separately scoped future renderer."""

    request_id: str
    source_image_reference: str
    source_image_hash: str
    planned_operation: str
    rationale: str
    source_findings: tuple[str, ...]
    requested_provider_type: str
    requested_capabilities: tuple[str, ...]
    parameters: tuple[tuple[str, JsonScalar], ...] = ()
    seed: int | None = None
    output_isolation_required: bool = True
    source_modification_prohibited: bool = True

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.source_image_reference, "source_image_reference"),
            (self.source_image_hash, "source_image_hash"),
            (self.rationale, "rationale"),
        ):
            _require_nonempty(value, name)
        _require_known(self.planned_operation, CURRENT_OPERATIONS, "planned_operation")
        _require_known(
            self.requested_provider_type,
            PROVIDER_TYPES,
            "requested_provider_type",
        )
        capabilities = _stable_strings(
            self.requested_capabilities,
            "requested_capability",
        )
        unknown = sorted(set(capabilities) - set(CAPABILITY_IDS))
        if unknown:
            raise PreviewProviderContractError(
                f"Unsupported requested capabilities: {', '.join(unknown)}"
            )
        object.__setattr__(
            self,
            "source_findings",
            _stable_strings(self.source_findings, "source_finding"),
        )
        object.__setattr__(self, "requested_capabilities", capabilities)
        object.__setattr__(
            self,
            "parameters",
            _stable_parameters(self.parameters, "parameter"),
        )
        if self.seed is not None and (not isinstance(self.seed, int) or self.seed < 0):
            raise PreviewProviderContractError("seed must be a non-negative integer")
        if not self.output_isolation_required or not self.source_modification_prohibited:
            raise PreviewProviderContractError(
                "Preview requests must require isolated output and prohibit source modification"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source_image_reference": self.source_image_reference,
            "source_image_hash": self.source_image_hash,
            "planned_operation": self.planned_operation,
            "rationale": self.rationale,
            "source_findings": list(self.source_findings),
            "requested_provider_type": self.requested_provider_type,
            "requested_capabilities": list(self.requested_capabilities),
            "parameters": {key: value for key, value in self.parameters},
            "seed": self.seed,
            "output_isolation_required": self.output_isolation_required,
            "source_modification_prohibited": self.source_modification_prohibited,
        }


@dataclass(frozen=True)
class PreviewResult:
    """Future result metadata; v1.7 creates no result instances or artifacts."""

    request_id: str
    provider_id: str
    status: str
    candidate_artifact: PreviewArtifactReference | None = None
    candidate_hash: str | None = None
    parameters_used: tuple[tuple[str, JsonScalar], ...] = ()
    seed_used: int | None = None
    reproducibility_notes: str = ""
    warnings: tuple[str, ...] = ()
    provenance: tuple[tuple[str, JsonScalar], ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.request_id, "request_id")
        _require_nonempty(self.provider_id, "provider_id")
        _require_known(self.status, RESULT_STATUSES, "result status")
        if (self.candidate_artifact is None) != (self.candidate_hash is None):
            raise PreviewProviderContractError(
                "candidate_artifact and candidate_hash must be provided together"
            )
        if self.status == RESULT_NOT_EXECUTED and self.candidate_artifact is not None:
            raise PreviewProviderContractError(
                "NOT_EXECUTED results cannot reference candidate artifacts"
            )
        if self.seed_used is not None and (
            not isinstance(self.seed_used, int) or self.seed_used < 0
        ):
            raise PreviewProviderContractError(
                "seed_used must be a non-negative integer"
            )
        object.__setattr__(
            self,
            "parameters_used",
            _stable_parameters(self.parameters_used, "parameter_used"),
        )
        object.__setattr__(self, "warnings", _stable_strings(self.warnings, "warning"))
        object.__setattr__(
            self,
            "provenance",
            _stable_parameters(self.provenance, "provenance"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "status": self.status,
            "candidate_artifact": (
                self.candidate_artifact.to_dict()
                if self.candidate_artifact is not None
                else None
            ),
            "candidate_hash": self.candidate_hash,
            "parameters_used": {key: value for key, value in self.parameters_used},
            "seed_used": self.seed_used,
            "reproducibility_notes": self.reproducibility_notes,
            "warnings": list(self.warnings),
            "provenance": {key: value for key, value in self.provenance},
            "error": (
                {"code": self.error_code, "message": self.error_message}
                if self.error_code or self.error_message
                else None
            ),
        }


@dataclass(frozen=True)
class ProviderCapabilityMatch:
    """Deterministic explanation of a plan/provider capability comparison."""

    status: str
    provider_type: str
    provider_id: str | None
    required_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    operation_supported: bool
    execution_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_type": self.provider_type,
            "provider_id": self.provider_id,
            "required_capabilities": list(self.required_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "operation_supported": self.operation_supported,
            "execution_available": self.execution_available,
        }


_LOCAL_CLASSICAL_CAPABILITIES = PreviewProviderCapabilities(
    image_input=True,
    deterministic_execution=True,
    parameter_provenance=True,
    candidate_image_output=True,
)
_IMAGE_PREVIEW_CAPABILITIES = PreviewProviderCapabilities(
    image_input=True,
    seed=True,
    parameter_provenance=True,
    candidate_image_output=True,
)
_MANUAL_CAPABILITIES = PreviewProviderCapabilities(
    parameter_provenance=True,
    candidate_image_output=True,
    metadata_only_manual_import=True,
)

BUILT_IN_PREVIEW_PROVIDER_DESCRIPTORS = (
    PreviewProviderDescriptor(
        provider_id="local_classical/contract-v1",
        display_name="Local Classical",
        provider_version="v1",
        provider_type=PROVIDER_LOCAL_CLASSICAL,
        supported_operations=("REDUCE_ENCODING_ARTIFACTS", "REDUCE_HALO"),
        availability_state=AVAILABILITY_DESCRIPTOR_ONLY,
        deterministic=True,
        remote=False,
        requires_network=False,
        requires_credentials=False,
        supports_seed=False,
        supports_reproducible_parameters=True,
        supports_difference_metadata=False,
        implementation_status=IMPLEMENTATION_LOCAL_PREVIEW_AVAILABLE,
        capabilities=_LOCAL_CLASSICAL_CAPABILITIES,
    ),
    PreviewProviderDescriptor(
        provider_id="comfyui/contract-v1",
        display_name="ComfyUI",
        provider_version="contract-v1",
        provider_type=PROVIDER_COMFYUI,
        supported_operations=("REDUCE_ENCODING_ARTIFACTS", "REDUCE_HALO"),
        availability_state=AVAILABILITY_DESCRIPTOR_ONLY,
        deterministic=False,
        remote=False,
        requires_network=True,
        requires_credentials=False,
        supports_seed=True,
        supports_reproducible_parameters=True,
        supports_difference_metadata=False,
        implementation_status=IMPLEMENTATION_NOT_IMPLEMENTED,
        capabilities=_IMAGE_PREVIEW_CAPABILITIES,
    ),
    PreviewProviderDescriptor(
        provider_id="krea/contract-v1",
        display_name="Krea",
        provider_version="contract-v1",
        provider_type=PROVIDER_KREA,
        supported_operations=("REDUCE_ENCODING_ARTIFACTS", "REDUCE_HALO"),
        availability_state=AVAILABILITY_DESCRIPTOR_ONLY,
        deterministic=False,
        remote=True,
        requires_network=True,
        requires_credentials=True,
        supports_seed=True,
        supports_reproducible_parameters=True,
        supports_difference_metadata=False,
        implementation_status=IMPLEMENTATION_NOT_IMPLEMENTED,
        capabilities=_IMAGE_PREVIEW_CAPABILITIES,
    ),
    PreviewProviderDescriptor(
        provider_id="manual/contract-v1",
        display_name="Manual Review",
        provider_version="contract-v1",
        provider_type=PROVIDER_MANUAL,
        supported_operations=(
            "KEEP",
            "MANUAL_CAPTION",
            "NO_ACTION",
            "REMOVE_DUPLICATE",
            "REPLACE_SOURCE",
        ),
        availability_state=AVAILABILITY_DESCRIPTOR_ONLY,
        deterministic=False,
        remote=False,
        requires_network=False,
        requires_credentials=False,
        supports_seed=False,
        supports_reproducible_parameters=True,
        supports_difference_metadata=False,
        implementation_status=IMPLEMENTATION_NOT_IMPLEMENTED,
        capabilities=_MANUAL_CAPABILITIES,
    ),
    PreviewProviderDescriptor(
        provider_id="unknown/contract-v1",
        display_name="Provider Not Selected",
        provider_version="contract-v1",
        provider_type=PROVIDER_UNKNOWN,
        supported_operations=(),
        availability_state=AVAILABILITY_UNKNOWN,
        deterministic=False,
        remote=False,
        requires_network=False,
        requires_credentials=False,
        supports_seed=False,
        supports_reproducible_parameters=False,
        supports_difference_metadata=False,
        implementation_status=IMPLEMENTATION_NOT_IMPLEMENTED,
        capabilities=PreviewProviderCapabilities(),
    ),
)

_DESCRIPTORS_BY_TYPE = {
    descriptor.provider_type: descriptor
    for descriptor in BUILT_IN_PREVIEW_PROVIDER_DESCRIPTORS
}


def preview_provider_descriptors() -> tuple[PreviewProviderDescriptor, ...]:
    """Return stable built-in descriptor metadata in provider-type order."""

    return BUILT_IN_PREVIEW_PROVIDER_DESCRIPTORS


def preview_provider_descriptor(
    provider_type: str,
) -> PreviewProviderDescriptor | None:
    """Return a descriptor by provider type without live availability checks."""

    return _DESCRIPTORS_BY_TYPE.get(provider_type)


def required_capabilities_for_operation(operation: str) -> tuple[str, ...]:
    """Return the deterministic capability requirements for a planning operation."""

    _require_known(operation, CURRENT_OPERATIONS, "planned_operation")
    if operation in {"REDUCE_HALO", "REDUCE_ENCODING_ARTIFACTS"}:
        return (
            CAPABILITY_IMAGE_INPUT,
            CAPABILITY_PARAMETER_PROVENANCE,
            CAPABILITY_CANDIDATE_IMAGE_OUTPUT,
        )
    if operation in {"MANUAL_CAPTION", "REMOVE_DUPLICATE", "REPLACE_SOURCE"}:
        return (CAPABILITY_METADATA_ONLY_MANUAL_IMPORT,)
    return ()


def match_preview_provider(
    provider_type: str,
    operation: str,
    required_capabilities: tuple[str, ...] | None = None,
) -> ProviderCapabilityMatch:
    """Match one plan to one descriptor without invoking a provider."""

    requirements = _stable_strings(
        required_capabilities
        if required_capabilities is not None
        else required_capabilities_for_operation(operation),
        "required_capability",
    )
    unknown = sorted(set(requirements) - set(CAPABILITY_IDS))
    if unknown:
        raise PreviewProviderContractError(
            f"Unsupported required capabilities: {', '.join(unknown)}"
        )
    descriptor = preview_provider_descriptor(provider_type)
    if descriptor is None or provider_type == PROVIDER_UNKNOWN:
        return ProviderCapabilityMatch(
            status=MATCH_UNKNOWN_PROVIDER,
            provider_type=provider_type,
            provider_id=descriptor.provider_id if descriptor else None,
            required_capabilities=requirements,
            missing_capabilities=requirements,
            operation_supported=False,
        )
    supported = set(descriptor.capabilities.supported_ids())
    missing = tuple(value for value in requirements if value not in supported)
    operation_supported = operation in descriptor.supported_operations
    return ProviderCapabilityMatch(
        status=(
            MATCH_COMPATIBLE
            if operation_supported and not missing
            else MATCH_INCOMPATIBLE
        ),
        provider_type=provider_type,
        provider_id=descriptor.provider_id,
        required_capabilities=requirements,
        missing_capabilities=missing,
        operation_supported=operation_supported,
    )


DEFAULT_PROVIDER_EXECUTION_POLICY = ProviderExecutionPolicy()


__all__ = [
    "ARTIFACT_SCOPE_ISOLATED_PREVIEW_OUTPUT",
    "BUILT_IN_PREVIEW_PROVIDER_DESCRIPTORS",
    "CAPABILITY_IDS",
    "CURRENT_OPERATIONS",
    "DEFAULT_PROVIDER_EXECUTION_POLICY",
    "IMPLEMENTATION_LOCAL_PREVIEW_AVAILABLE",
    "MATCH_COMPATIBLE",
    "MATCH_INCOMPATIBLE",
    "MATCH_UNKNOWN_PROVIDER",
    "PreviewArtifactReference",
    "PreviewProviderCapabilities",
    "PreviewProviderContractError",
    "PreviewProviderDescriptor",
    "PreviewRequest",
    "PreviewResult",
    "ProviderCapabilityMatch",
    "ProviderExecutionPolicy",
    "match_preview_provider",
    "preview_provider_descriptor",
    "preview_provider_descriptors",
    "required_capabilities_for_operation",
]
