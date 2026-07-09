"""End-to-end tests for the v1 inspect pipeline.

Creates real synthetic images in temporary directories so the full
DatasetContext → TextureAnalyzer → Finding → Report chain runs
against actual pixel data, not stubs.
"""

from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analyzers.registry import analyzer_versions
from dataset_forge.analyzer_descriptors import descriptor_for_id
from dataset_forge.inspection_profiles import DEFAULT_INSPECTION_PROFILE
from dataset_forge.inspection_manifest import INSPECTION_MANIFEST_SCHEMA
from dataset_forge.inspect import InspectResult, run_inspect
from dataset_forge.finding import Finding, Severity
from dataset_forge.measurements import measure_image as real_measure_image
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA
from dataset_forge.review_signal_policy import (
    ResolvedReviewSignalPolicy,
    ReviewSignalPolicy,
)


# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------

def _write_smooth(path: Path, n: int = 1) -> list[Path]:
    """Write n solid images. Near-zero microtexture, but not duplicates."""
    written = []
    for i in range(n):
        p = path / f"smooth_{i:03d}.png"
        value = 96 + (i % 64)
        arr = np.full((256, 256, 3), value, dtype=np.uint8)
        Image.fromarray(arr).save(p)
        p.with_suffix(".txt").write_text(
            f"smooth fixture image {i} neutral caption",
            encoding="utf-8",
        )
        written.append(p)
    return written


def _write_noisy(path: Path, n: int = 1) -> list[Path]:
    """Write n random-noise images. Very high microtexture."""
    written = []
    rng = np.random.default_rng(99)
    for i in range(n):
        p = path / f"noisy_{i:03d}.png"
        arr = rng.integers(0, 255, size=(256, 256, 3), dtype=np.uint8)
        Image.fromarray(arr).save(p)
        p.with_suffix(".txt").write_text(
            f"noisy fixture image {i} neutral caption",
            encoding="utf-8",
        )
        written.append(p)
    return written


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunInspectBasic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_inspect_result(self):
        _write_smooth(self.dataset, n=3)
        result = run_inspect(self.dataset, self.output)
        self.assertIsInstance(result, InspectResult)

    def test_image_count(self):
        _write_smooth(self.dataset, n=5)
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 5)

    def test_no_errors_on_valid_images(self):
        _write_smooth(self.dataset, n=3)
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.error_count, 0)

    def test_json_report_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.json_report.exists())

    def test_txt_report_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.txt_report.exists())

    def test_recommendation_json_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.recommendation_json.exists())

    def test_recommendation_markdown_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.recommendation_markdown.exists())

    def test_triage_dossiers_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.triage_dossier_json.read_text(encoding="utf-8"))

        self.assertTrue(result.triage_dossier_json.exists())
        self.assertTrue(result.triage_dossier_markdown.exists())
        self.assertEqual(data["schema"], "dataset-forge/triage-dossiers/v1")
        self.assertEqual(data["summary"]["no_findings_emitted_count"], 2)
        self.assertEqual(
            data["policy_semantics"],
            {
                "dossier_basis": "triage_included_findings",
                "visible_findings_basis": "display_visible_findings",
                "executed_findings_source": "inspection_report.json",
                "policy_source": "inspection_manifest.json",
                "all_current_findings_visible": True,
                "all_current_findings_triage_included": True,
            },
        )
        self.assertEqual(data["scope"]["execution"], "out_of_scope")
        self.assertEqual(data["scope"]["cleanup"], "out_of_scope")
        self.assertEqual(data["scope"]["export"], "out_of_scope")
        self.assertEqual(len(data["dossiers"]), 2)

    def test_inspection_manifest_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.inspection_manifest.read_text(encoding="utf-8"))

        self.assertTrue(result.inspection_manifest.exists())
        self.assertEqual(result.inspection_manifest.name, "inspection_manifest.json")
        self.assertEqual(data["schema"], INSPECTION_MANIFEST_SCHEMA)
        self.assertEqual(data["tool"]["name"], "dataset-forge")
        self.assertEqual(data["inspection"]["profile"]["id"], "default")
        self.assertEqual(
            data["inspection"]["profile"]["display_name"],
            "Default Inspection",
        )
        self.assertEqual(
            data["inspection"]["profile"]["description"],
            "Default Dataset Forge inspection profile.",
        )
        self.assertEqual(data["inspection"]["profile"]["version"], "v1")
        self.assertEqual(data["inspection"]["profile"]["analyzer_policy_overrides"], [])
        self.assertTrue(data["inspection"]["deterministic"])
        self.assertTrue(data["inspection"]["read_only"])
        self.assertEqual(
            data["inspection"]["profile"],
            DEFAULT_INSPECTION_PROFILE.to_dict(),
        )

    def test_inspection_manifest_records_dataset_and_sidecars(self):
        _write_smooth(self.dataset, n=3)
        result = run_inspect(self.dataset, self.output, recursive=True, limit=3)
        data = json.loads(result.inspection_manifest.read_text(encoding="utf-8"))

        self.assertEqual(data["dataset"]["path"], str(self.dataset.resolve()))
        self.assertTrue(data["dataset"]["recursive"])
        self.assertEqual(data["dataset"]["limit"], 3)
        self.assertEqual(data["dataset"]["image_count"], result.image_count)
        self.assertEqual(data["dataset"]["analyzed_count"], result.analyzed_count)
        self.assertEqual(data["dataset"]["error_count"], result.error_count)
        self.assertEqual(
            data["sidecars"]["inspection_report"],
            {
                "path": "inspection_report.json",
                "schema": "dataset-forge/inspection/v1",
            },
        )
        self.assertEqual(
            data["sidecars"]["recommendation_summary"],
            {
                "path": "recommendation_summary.json",
                "schema": "dataset-forge/recommendation-summary/v1",
            },
        )
        self.assertEqual(
            data["sidecars"]["triage_dossiers"],
            {
                "path": "triage_dossiers.json",
                "schema": "dataset-forge/triage-dossiers/v1",
            },
        )
        self.assertEqual(data["compatibility"]["manifest_contract_version"], 1)

    def test_inspection_manifest_records_current_analyzers_and_policies(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.inspection_manifest.read_text(encoding="utf-8"))

        analyzers = {item["id"]: item for item in data["analyzers"]}
        self.assertEqual(set(analyzers), set(analyzer_versions()))
        for analyzer_id, version in analyzer_versions().items():
            descriptor = descriptor_for_id(analyzer_id)
            self.assertIsNotNone(descriptor)
            row = analyzers[analyzer_id]
            self.assertEqual(row["display_name"], descriptor.display_name)
            self.assertEqual(row["version"], version)
            self.assertEqual(row["family"], descriptor.family)
            self.assertEqual(row["calibration_status"], descriptor.calibration_status)
            self.assertEqual(row["categories_emitted"], list(descriptor.categories_emitted))
            self.assertEqual(row["execution"], {"policy": "enabled", "executed": True})
            self.assertEqual(row["display"], {"policy": "visible"})
            self.assertEqual(row["triage"], {"policy": "included"})
            self.assertEqual(
                set(row),
                {
                    "id",
                    "display_name",
                    "version",
                    "family",
                    "categories_emitted",
                    "calibration_status",
                    "execution",
                    "display",
                    "triage",
                    "finding_count",
                    "image_count",
                },
            )
        self.assertEqual(data["disabled_analyzers"], [])

    def test_inspection_manifest_finding_counts_are_deterministic(self):
        class FindingAnalyzer:
            name = "recording_analyzer"
            version = "v1"
            supported_categories = ("artifact.recording",)

            @property
            def analyzer_id(self):
                return f"{self.name}/{self.version}"

            def analyze(self, image_path, context, measurements=None):
                del context, measurements
                return [
                    Finding(
                        image_path=image_path,
                        analyzer=self.analyzer_id,
                        category="artifact.recording",
                        severity=Severity.MEDIUM,
                        confidence=0.5,
                        false_positive_rate=0.1,
                        benchmark_version="fixture",
                        evidence={"fixture": True},
                        explanation="fixture finding",
                        recommendation="review fixture finding",
                    )
                ]

        _write_smooth(self.dataset, n=2)
        with patch(
            "dataset_forge.inspect.create_analyzers",
            return_value=[FindingAnalyzer()],
        ):
            result = run_inspect(self.dataset, self.output)
        data = json.loads(result.inspection_manifest.read_text(encoding="utf-8"))

        self.assertEqual(len(data["analyzers"]), 1)
        self.assertEqual(data["analyzers"][0]["id"], "recording_analyzer")
        self.assertEqual(data["analyzers"][0]["version"], "v1")
        self.assertEqual(data["analyzers"][0]["finding_count"], 2)
        self.assertEqual(data["analyzers"][0]["image_count"], 2)

    def test_inspection_manifest_policy_values_are_resolver_derived(self):
        _write_smooth(self.dataset, n=1)

        def fake_resolution(descriptor, *, profile):
            return type(
                "Resolution",
                (),
                {
                    "effective_policy": ResolvedReviewSignalPolicy(
                        analyzer_id=descriptor.id,
                        policy=ReviewSignalPolicy(
                            execution="disabled",
                            display="hidden",
                            triage="excluded",
                        ),
                        source="test_override",
                    )
                },
            )()

        with patch(
            "dataset_forge.inspection_manifest.resolve_review_signal_policy",
            side_effect=fake_resolution,
        ):
            result = run_inspect(self.dataset, self.output)
        data = json.loads(result.inspection_manifest.read_text(encoding="utf-8"))

        for row in data["analyzers"]:
            self.assertEqual(row["execution"], {"policy": "disabled", "executed": True})
            self.assertEqual(row["display"], {"policy": "hidden"})
            self.assertEqual(row["triage"], {"policy": "excluded"})

    def test_review_decisions_template_written_when_absent(self):
        _write_smooth(self.dataset, n=2)
        run_inspect(self.dataset, self.output)
        template = self.output / "review_decisions_template.json"
        data = json.loads(template.read_text(encoding="utf-8"))

        self.assertTrue(template.exists())
        self.assertEqual(data["schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(len(data["decisions"]), 2)
        self.assertIsNone(data["decisions"][0]["decision"])
        self.assertIn("recommendation", data["decisions"][0])
        self.assertIn("notes", data["decisions"][0])

    def test_existing_review_decisions_template_is_not_overwritten(self):
        _write_smooth(self.dataset, n=1)
        template = self.output / "review_decisions_template.json"
        self.output.mkdir()
        template.write_text("human draft\n", encoding="utf-8")

        run_inspect(self.dataset, self.output)

        self.assertEqual(template.read_text(encoding="utf-8"), "human draft\n")

    def test_existing_review_decisions_file_is_not_overwritten(self):
        images = _write_smooth(self.dataset, n=1)
        self.output.mkdir()
        decisions = self.output / "review_decisions.json"
        original = json.dumps({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": [
                {
                    "image_path": str(images[0]),
                    "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                    "workflow_state": "REVIEWED",
                    "notes": "human checked this one",
                },
            ],
        }, indent=2)
        decisions.write_text(original, encoding="utf-8")

        run_inspect(self.dataset, self.output)

        self.assertEqual(decisions.read_text(encoding="utf-8"), original)

    def test_existing_review_decisions_do_not_change_recommendation_json(self):
        images = _write_smooth(self.dataset, n=1)
        baseline_output = Path(self.tmp.name) / "baseline"
        baseline = run_inspect(self.dataset, baseline_output)

        self.output.mkdir()
        decisions = self.output / "review_decisions.json"
        decisions.write_text(
            json.dumps({
                "schema": REVIEW_DECISIONS_SCHEMA,
                "decisions": [
                    {
                        "image_path": str(images[0]),
                        "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                        "workflow_state": "REVIEWED",
                    },
                ],
            }),
            encoding="utf-8",
        )

        with_decisions = run_inspect(self.dataset, self.output)

        self.assertEqual(
            json.loads(with_decisions.recommendation_json.read_text(encoding="utf-8")),
            json.loads(baseline.recommendation_json.read_text(encoding="utf-8")),
        )

    def test_existing_inspection_outputs_remain_present(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)

        self.assertTrue(result.json_report.exists())
        self.assertTrue(result.txt_report.exists())
        self.assertTrue(result.recommendation_json.exists())
        self.assertTrue(result.recommendation_markdown.exists())
        self.assertTrue(result.inspection_manifest.exists())

    def test_review_gallery_not_written_by_default(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)

        self.assertIsNone(result.review_gallery_path)
        self.assertFalse((self.output / "review_gallery.html").exists())

    def test_review_gallery_written_when_requested(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output, review_gallery=True)

        self.assertIsNotNone(result.review_gallery_path)
        assert result.review_gallery_path is not None
        self.assertTrue(result.review_gallery_path.exists())
        self.assertEqual(result.review_gallery_path.name, "review_gallery.html")

    def test_contact_sheets_not_written_by_default(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)

        self.assertIsNone(result.priority_review_contact_sheet)
        self.assertIsNone(result.needs_review_contact_sheet)
        self.assertFalse((self.output / "priority_review_contact_sheet.png").exists())
        self.assertFalse((self.output / "needs_review_contact_sheet.png").exists())

    def test_contact_sheets_written_when_requested(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output, contact_sheets=True)

        self.assertIsNotNone(result.priority_review_contact_sheet)
        self.assertIsNotNone(result.needs_review_contact_sheet)
        assert result.priority_review_contact_sheet is not None
        assert result.needs_review_contact_sheet is not None
        self.assertTrue(result.priority_review_contact_sheet.exists())
        self.assertTrue(result.needs_review_contact_sheet.exists())
        self.assertEqual(
            result.priority_review_contact_sheet.name,
            "priority_review_contact_sheet.png",
        )
        self.assertEqual(
            result.needs_review_contact_sheet.name,
            "needs_review_contact_sheet.png",
        )

    def test_json_report_valid(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertIn("schema", data)
        self.assertIn("findings", data)
        self.assertIn("summary", data)

    def test_json_report_includes_oversharpening_analyzer_version(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        versions = data["context"]["analyzer_versions"]
        self.assertEqual(versions["oversharpening_halo_analyzer"], "v1")

    def test_json_report_includes_high_frequency_isolated_analyzer_version(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        versions = data["context"]["analyzer_versions"]
        self.assertEqual(
            versions["high_frequency_isolated_artifact_analyzer"],
            "v1",
        )

    def test_json_report_includes_complete_analyzer_versions(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))

        self.assertEqual(
            data["context"]["analyzer_versions"],
            analyzer_versions(),
        )

    def test_inspection_report_schema_is_unchanged(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))

        self.assertEqual(data["schema"], "dataset-forge/inspection/v1")
        self.assertEqual(
            data["finding_policy_semantics"],
            {
                "findings_scope": "executed_findings",
                "policy_source": "inspection_manifest.analyzers",
                "all_current_findings_visible": True,
                "all_current_findings_triage_included": True,
            },
        )
        self.assertNotIn("recommendation_summary", data)
        self.assertNotIn("review_gallery", data)
        self.assertNotIn("contact_sheets", data)
        self.assertNotIn("review_decisions", data)
        self.assertNotIn("inspection_manifest", data)

    def test_existing_sidecar_schemas_are_unchanged_by_manifest(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)

        inspection = json.loads(result.json_report.read_text(encoding="utf-8"))
        recommendations = json.loads(
            result.recommendation_json.read_text(encoding="utf-8")
        )
        dossiers = json.loads(result.triage_dossier_json.read_text(encoding="utf-8"))

        self.assertEqual(inspection["schema"], "dataset-forge/inspection/v1")
        self.assertEqual(
            recommendations["schema"],
            "dataset-forge/recommendation-summary/v1",
        )
        self.assertEqual(dossiers["schema"], "dataset-forge/triage-dossiers/v1")

    def test_inspect_uses_analyzer_registry(self):
        class RecordingAnalyzer:
            name = "recording_analyzer"
            version = "v1"

            def analyze(self, image_path, context, measurements=None):
                del image_path, context, measurements
                return []

        _write_smooth(self.dataset, n=1)
        with patch(
            "dataset_forge.inspect.create_analyzers",
            return_value=[RecordingAnalyzer()],
        ) as create_mock:
            result = run_inspect(self.dataset, self.output)

        self.assertEqual(result.total_findings, 0)
        create_mock.assert_called_once_with()

    def test_invalid_path_raises(self):
        with self.assertRaises(ValueError):
            run_inspect(Path("/nonexistent/path"), self.output)

    def test_empty_dataset_runs_without_error(self):
        # No images — discovery returns nothing, pipeline handles gracefully
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 0)
        self.assertEqual(result.total_findings, 0)


    def test_texture_measurements_are_computed_once_per_image(self):
        paths = _write_smooth(self.dataset, n=4)
        with (
            patch(
                "dataset_forge.context_builder.measure_image",
                wraps=real_measure_image,
            ) as measure_mock,
            patch(
                "dataset_forge.analyzers.texture.evaluate_texture",
                side_effect=AssertionError("TextureAnalyzer remeasured image"),
            ),
            patch(
                "dataset_forge.analyzers.crystalline.evaluate_texture",
                side_effect=AssertionError("CrystallineAnalyzer remeasured image"),
            ),
        ):
            result = run_inspect(self.dataset, self.output)

        self.assertEqual(result.image_count, len(paths))
        self.assertEqual(measure_mock.call_count, len(paths))


class TestRunInspectCleanDataset(unittest.TestCase):
    """Smooth images should produce few or no texture findings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        _write_smooth(self.dataset, n=10)

    def tearDown(self):
        self.tmp.cleanup()

    def test_images_clean_count(self):
        result = run_inspect(self.dataset, self.output)
        # Smooth images score very low — all should be below dataset mean
        self.assertEqual(result.images_clean, result.image_count)

    def test_total_findings_zero_for_uniform_smooth(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.total_findings, 0)

    def test_images_with_findings_zero(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.images_with_findings, 0)

    def test_json_images_clean_matches(self):
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["images_clean"], result.image_count)


class TestRunInspectDuplicateDataset(unittest.TestCase):
    """Duplicate findings should flow through inspect sidecars read-only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        self.first = _write_smooth(self.dataset, n=1)[0]
        self.second = self.dataset / "duplicate.png"
        shutil.copyfile(self.first, self.second)
        self.before_hashes = {
            self.first: _sha256(self.first),
            self.second: _sha256(self.second),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_findings_are_written_without_modifying_sources(self):
        result = run_inspect(self.dataset, self.output)
        report = json.loads(result.json_report.read_text(encoding="utf-8"))
        summary = json.loads(result.recommendation_json.read_text(encoding="utf-8"))
        manifest = json.loads(result.inspection_manifest.read_text(encoding="utf-8"))

        duplicate_findings = [
            finding for finding in report["findings"]
            if finding["category"] == "dataset.duplicate.exact"
        ]
        self.assertEqual(len(duplicate_findings), 2)
        self.assertEqual(
            {finding["evidence"]["group_id"] for finding in duplicate_findings},
            {"duplicate-group-0001"},
        )
        self.assertEqual(
            {finding["evidence"]["duplicate_kind"] for finding in duplicate_findings},
            {"file_sha256"},
        )
        self.assertIn(
            "dataset.duplicate.exact",
            {
                ref["category"]
                for item in summary["recommendations"]
                for ref in item["finding_refs"]
            },
        )
        self.assertIn(
            "duplicate_detection_analyzer",
            {row["id"] for row in manifest["analyzers"]},
        )
        self.assertEqual(
            {path: _sha256(path) for path in self.before_hashes},
            self.before_hashes,
        )


class TestRunInspectNoisyDataset(unittest.TestCase):
    """Mixed dataset: mostly smooth + a few noisy outliers → findings on noisy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        # 8 smooth + 2 very noisy — noisy images should be outliers
        _write_smooth(self.dataset, n=8)
        _write_noisy(self.dataset, n=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_image_count(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 10)

    def test_findings_present(self):
        result = run_inspect(self.dataset, self.output)
        self.assertGreater(result.total_findings, 0)

    def test_noisy_images_flagged(self):
        result = run_inspect(self.dataset, self.output)
        self.assertGreater(result.images_with_findings, 0)

    def test_clean_images_present(self):
        result = run_inspect(self.dataset, self.output)
        self.assertGreater(result.images_clean, 0)

    def test_clean_plus_affected_equals_total(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(
            result.images_clean + result.images_with_findings,
            result.image_count,
        )

    def test_json_findings_have_required_fields(self):
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        if data["findings"]:
            f = data["findings"][0]
            for field in ("image_path", "analyzer", "category", "severity",
                          "confidence", "explanation", "recommendation"):
                self.assertIn(field, f)

    def test_txt_report_nonempty(self):
        result = run_inspect(self.dataset, self.output)
        txt = result.txt_report.read_text(encoding="utf-8")
        self.assertIn("Dataset Forge Inspection Report", txt)


class TestRunInspectDuplicates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_duplicates_detected_in_context(self):
        # Write the same image content under two names
        arr = np.full((64, 64, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)
        img.save(self.dataset / "copy_a.png")
        img.save(self.dataset / "copy_b.png")

        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertGreater(data["context"]["exact_duplicate_count"], 0)


class TestInspectResultFields(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        _write_smooth(self.dataset, n=3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_result_dataset_path(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.dataset_path, self.dataset)

    def test_result_output_dir(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.output_dir, self.output)

    def test_result_is_frozen(self):
        result = run_inspect(self.dataset, self.output)
        with self.assertRaises(Exception):
            result.image_count = 999  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
