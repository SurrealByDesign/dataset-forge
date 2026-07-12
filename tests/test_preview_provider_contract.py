from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from dataset_forge.preview_provider_contract import (
    CAPABILITY_CANDIDATE_IMAGE_OUTPUT,
    CAPABILITY_IMAGE_INPUT,
    CAPABILITY_METADATA_ONLY_MANUAL_IMPORT,
    CAPABILITY_PARAMETER_PROVENANCE,
    DEFAULT_PROVIDER_EXECUTION_POLICY,
    MATCH_COMPATIBLE,
    MATCH_INCOMPATIBLE,
    MATCH_UNKNOWN_PROVIDER,
    PROVIDER_KREA,
    PROVIDER_LOCAL_CLASSICAL,
    PROVIDER_MANUAL,
    PreviewArtifactReference,
    PreviewProviderCapabilities,
    PreviewProviderContractError,
    PreviewProviderDescriptor,
    PreviewRequest,
    PreviewResult,
    RESULT_NOT_EXECUTED,
    match_preview_provider,
    preview_provider_descriptor,
    preview_provider_descriptors,
    required_capabilities_for_operation,
)


class PreviewProviderContractTests(unittest.TestCase):
    def test_registry_is_deterministic_and_descriptor_only(self) -> None:
        first = [descriptor.to_dict() for descriptor in preview_provider_descriptors()]
        second = [descriptor.to_dict() for descriptor in preview_provider_descriptors()]

        self.assertEqual(first, second)
        self.assertEqual(
            [item["provider_type"] for item in first],
            ["LOCAL_CLASSICAL", "COMFYUI", "KREA", "MANUAL", "UNKNOWN"],
        )
        by_type = {item["provider_type"]: item for item in first}
        self.assertEqual(by_type["LOCAL_CLASSICAL"]["implementation_status"], "local_preview_available")
        self.assertTrue(by_type["LOCAL_CLASSICAL"]["deterministic"])
        self.assertTrue(by_type["LOCAL_CLASSICAL"]["capabilities"]["deterministic_execution"])
        self.assertTrue(
            all(
                item["implementation_status"] == "not_implemented"
                for item in first
                if item["provider_type"] != "LOCAL_CLASSICAL"
            )
        )
        self.assertEqual(json.loads(json.dumps(first, sort_keys=True)), first)

    def test_descriptor_validation_rejects_unknown_values_and_inconsistent_flags(self) -> None:
        with self.assertRaises(PreviewProviderContractError):
            PreviewProviderDescriptor(
                provider_id="broken/v1",
                display_name="Broken",
                provider_version="v1",
                provider_type="SHELL",
                supported_operations=(),
                availability_state="descriptor_only",
                deterministic=False,
                remote=False,
                requires_network=False,
                requires_credentials=False,
                supports_seed=False,
                supports_reproducible_parameters=False,
                supports_difference_metadata=False,
                implementation_status="not_implemented",
                capabilities=PreviewProviderCapabilities(),
            )

        with self.assertRaisesRegex(PreviewProviderContractError, "supports_seed"):
            PreviewProviderDescriptor(
                provider_id="broken/v1",
                display_name="Broken",
                provider_version="v1",
                provider_type=PROVIDER_MANUAL,
                supported_operations=("KEEP",),
                availability_state="descriptor_only",
                deterministic=False,
                remote=False,
                requires_network=False,
                requires_credentials=False,
                supports_seed=True,
                supports_reproducible_parameters=False,
                supports_difference_metadata=False,
                implementation_status="not_implemented",
                capabilities=PreviewProviderCapabilities(),
            )

    def test_capability_matching_is_explicit_and_deterministic(self) -> None:
        required = required_capabilities_for_operation("REDUCE_HALO")
        self.assertEqual(
            required,
            (
                CAPABILITY_IMAGE_INPUT,
                CAPABILITY_PARAMETER_PROVENANCE,
                CAPABILITY_CANDIDATE_IMAGE_OUTPUT,
            ),
        )
        local = match_preview_provider(PROVIDER_LOCAL_CLASSICAL, "REDUCE_HALO")
        manual = match_preview_provider(PROVIDER_MANUAL, "REDUCE_HALO")
        unknown = match_preview_provider("UNKNOWN", "REDUCE_HALO")

        self.assertEqual(local.status, MATCH_COMPATIBLE)
        self.assertFalse(local.execution_available)
        self.assertEqual(manual.status, MATCH_INCOMPATIBLE)
        self.assertEqual(
            manual.missing_capabilities,
            (CAPABILITY_IMAGE_INPUT,),
        )
        self.assertEqual(unknown.status, MATCH_UNKNOWN_PROVIDER)
        self.assertEqual(local, match_preview_provider(PROVIDER_LOCAL_CLASSICAL, "REDUCE_HALO"))

    def test_manual_metadata_operation_is_compatible_but_not_executable(self) -> None:
        match = match_preview_provider(PROVIDER_MANUAL, "REPLACE_SOURCE")
        descriptor = preview_provider_descriptor(PROVIDER_MANUAL)

        self.assertEqual(match.status, MATCH_COMPATIBLE)
        self.assertEqual(
            match.required_capabilities,
            (CAPABILITY_METADATA_ONLY_MANUAL_IMPORT,),
        )
        self.assertFalse(match.execution_available)
        assert descriptor is not None
        self.assertTrue(descriptor.capabilities.candidate_image_output)
        self.assertEqual(descriptor.implementation_status, "not_implemented")

    def test_local_remote_and_credential_flags_are_metadata_only(self) -> None:
        local = preview_provider_descriptor(PROVIDER_LOCAL_CLASSICAL)
        remote = preview_provider_descriptor(PROVIDER_KREA)

        self.assertIsNotNone(local)
        self.assertIsNotNone(remote)
        assert local is not None and remote is not None
        self.assertFalse(local.remote)
        self.assertFalse(local.requires_network)
        self.assertFalse(local.requires_credentials)
        self.assertEqual(local.implementation_status, "local_preview_available")
        self.assertTrue(remote.remote)
        self.assertTrue(remote.requires_network)
        self.assertTrue(remote.requires_credentials)
        self.assertEqual(remote.implementation_status, "not_implemented")

    def test_request_validation_and_serialization_are_stable(self) -> None:
        request = PreviewRequest(
            request_id="request-1",
            source_image_reference="dataset/image.png",
            source_image_hash="sha256:abc",
            planned_operation="REDUCE_HALO",
            rationale="Existing halo evidence supports a future isolated preview.",
            source_findings=("artifact.oversharpening_halo",),
            requested_provider_type=PROVIDER_LOCAL_CLASSICAL,
            requested_capabilities=(
                CAPABILITY_PARAMETER_PROVENANCE,
                CAPABILITY_IMAGE_INPUT,
            ),
            parameters=(("strength", 0.2), ("mode", "advisory")),
            seed=7,
        )

        self.assertEqual(
            request.to_dict()["requested_capabilities"],
            [CAPABILITY_IMAGE_INPUT, CAPABILITY_PARAMETER_PROVENANCE],
        )
        self.assertEqual(list(request.to_dict()["parameters"]), ["mode", "strength"])
        self.assertEqual(request.to_dict(), request.to_dict())

        with self.assertRaises(PreviewProviderContractError):
            PreviewRequest(
                request_id="request-2",
                source_image_reference="dataset/image.png",
                source_image_hash="sha256:abc",
                planned_operation="REDUCE_HALO",
                rationale="unsafe",
                source_findings=(),
                requested_provider_type=PROVIDER_LOCAL_CLASSICAL,
                requested_capabilities=(),
                source_modification_prohibited=False,
            )

    def test_artifact_references_are_isolated_and_cannot_overwrite_sources(self) -> None:
        artifact = PreviewArtifactReference(
            relative_path="request-1/candidate.png",
            media_type="image/png",
        )
        self.assertEqual(artifact.to_dict()["storage_scope"], "isolated_preview_output")

        for unsafe in (
            "../dataset/source.png",
            "C:\\dataset\\source.png",
            "C:dataset\\source.png",
            "source.png:alternate_stream",
            "/dataset/source.png",
        ):
            with self.subTest(path=unsafe):
                with self.assertRaises(PreviewProviderContractError):
                    PreviewArtifactReference(relative_path=unsafe, media_type="image/png")

    def test_result_contract_has_no_artifact_for_not_executed_state(self) -> None:
        result = PreviewResult(
            request_id="request-1",
            provider_id="local_classical/contract-v1",
            status=RESULT_NOT_EXECUTED,
            reproducibility_notes="Execution is unavailable in v1.7.",
            provenance=(("contract_version", "v1"),),
        )

        self.assertIsNone(result.to_dict()["candidate_artifact"])
        self.assertIsNone(result.to_dict()["candidate_hash"])
        with self.assertRaises(PreviewProviderContractError):
            PreviewResult(
                request_id="request-1",
                provider_id="local_classical/contract-v1",
                status=RESULT_NOT_EXECUTED,
                candidate_artifact=PreviewArtifactReference(
                    relative_path="request-1/candidate.png",
                    media_type="image/png",
                ),
                candidate_hash="sha256:def",
            )

    def test_execution_policy_keeps_v17_unavailable(self) -> None:
        policy = DEFAULT_PROVIDER_EXECUTION_POLICY.to_dict()

        self.assertFalse(policy["execution_available"])
        self.assertTrue(policy["source_dataset_writes_forbidden"])
        self.assertTrue(policy["source_image_overwrite_forbidden"])
        self.assertTrue(policy["isolated_output_required"])
        self.assertTrue(policy["human_approval_required"])

    def test_contract_module_has_no_execution_network_or_subprocess_imports(self) -> None:
        path = Path(__file__).parents[1] / "src" / "dataset_forge" / "preview_provider_contract.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )

        self.assertTrue(
            {"subprocess", "socket", "requests", "urllib", "http", "PIL", "cv2", "numpy"}
            .isdisjoint(imported)
        )


if __name__ == "__main__":
    unittest.main()
