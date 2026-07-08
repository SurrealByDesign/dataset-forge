from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.comparison import (
    COMPARISON_SUMMARY_SCHEMA,
    ComparisonError,
    build_comparison_summary,
    compare_inspect_outputs,
    render_comparison_markdown,
)
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA


def _finding(
    image_path: str,
    *,
    category: str = "artifact.texture",
    analyzer: str = "texture_analyzer/v1",
    severity: str = "LOW",
) -> dict[str, object]:
    return {
        "image_path": image_path,
        "analyzer": analyzer,
        "category": category,
        "severity": severity,
        "confidence": 0.4,
        "false_positive_rate": 0.2,
        "benchmark_version": "uncalibrated",
        "evidence": {"calibrated": False},
        "explanation": "test finding",
        "recommendation": "review",
    }


def _recommendation(
    image_path: str,
    recommendation: str,
    *,
    reason: str,
    refs: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    labels = {
        "READY_FOR_TRAINING": "No Findings Emitted",
        "NEEDS_REVIEW": "Needs Review",
        "PRIORITY_REVIEW": "Priority Review",
    }
    return {
        "image_path": image_path,
        "recommendation": recommendation,
        "display_label": labels[recommendation],
        "primary_reason": reason,
        "reason_codes": ["test"],
        "finding_refs": refs or [],
        "guidance": "review",
        "confidence_note": "advisory",
    }


def _write_output(
    root: Path,
    *,
    findings: list[dict[str, object]],
    recommendations: list[dict[str, object]],
    decisions: list[dict[str, object]] | None = None,
    manifest: dict[str, object] | None = None,
    report_schema: str = "dataset-forge/inspection/v1",
    recommendation_schema: str = "dataset-forge/recommendation-summary/v1",
) -> Path:
    root.mkdir()
    (root / "inspection_report.json").write_text(
        json.dumps({
            "schema": report_schema,
            "dataset_path": str(root / "dataset"),
            "tool_version": "0.test",
            "findings": findings,
            "summary": {"total_findings": len(findings)},
        }),
        encoding="utf-8",
    )
    counts = {
        "image_count": len(recommendations),
        "no_findings_emitted_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "READY_FOR_TRAINING"
        ),
        "ready_for_training_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "READY_FOR_TRAINING"
        ),
        "needs_review_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "NEEDS_REVIEW"
        ),
        "priority_review_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "PRIORITY_REVIEW"
        ),
        "analyzer_error_count": 0,
    }
    (root / "recommendation_summary.json").write_text(
        json.dumps({
            "schema": recommendation_schema,
            "source_report_schema": "dataset-forge/inspection/v1",
            "summary": counts,
            "recommendations": recommendations,
        }),
        encoding="utf-8",
    )
    if decisions is not None:
        (root / "review_decisions.json").write_text(
            json.dumps({
                "schema": REVIEW_DECISIONS_SCHEMA,
                "decisions": decisions,
            }),
            encoding="utf-8",
        )
    if manifest is not None:
        (root / "inspection_manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
    return root


def _manifest(
    *,
    schema: str = "dataset-forge/inspection-manifest/v1",
    tool_version: str = "0.23.0a0",
    profile_id: str = "default",
    profile_version: str = "v1",
    analyzers: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema": schema,
        "tool": {
            "name": "dataset-forge",
            "version": tool_version,
        },
        "inspection": {
            "profile": {
                "id": profile_id,
                "display_name": "Default Inspection",
                "version": profile_version,
            },
            "deterministic": True,
            "read_only": True,
        },
        "sidecars": {
            "inspection_report": {
                "path": "inspection_report.json",
                "schema": "dataset-forge/inspection/v1",
            },
            "recommendation_summary": {
                "path": "recommendation_summary.json",
                "schema": "dataset-forge/recommendation-summary/v1",
            },
        },
        "analyzers": analyzers if analyzers is not None else [_manifest_analyzer()],
        "disabled_analyzers": [],
        "compatibility": {
            "inspection_report_schema": "dataset-forge/inspection/v1",
            "recommendation_summary_schema": "dataset-forge/recommendation-summary/v1",
            "manifest_contract_version": 1,
        },
    }


def _manifest_analyzer(
    *,
    analyzer_id: str = "texture_analyzer",
    version: str = "v1",
    execution_policy: str = "enabled",
    executed: bool = True,
    display_policy: str = "visible",
    triage_policy: str = "included",
) -> dict[str, object]:
    return {
        "id": analyzer_id,
        "display_name": "Texture Analyzer",
        "version": version,
        "family": "Technical Quality",
        "categories_emitted": ["artifact.texture"],
        "calibration_status": "advisory",
        "execution": {
            "policy": execution_policy,
            "executed": executed,
        },
        "display": {
            "policy": display_policy,
        },
        "triage": {
            "policy": triage_policy,
        },
        "finding_count": 1,
        "image_count": 1,
    }


class ComparisonSummaryTests(unittest.TestCase):
    def _workspace(self, tmp: str) -> tuple[Path, Path]:
        root = Path(tmp)
        before = _write_output(
            root / "before",
            findings=[
                _finding("missing_source/changed.png", severity="LOW"),
                _finding("missing_source/resolved.png", category="artifact.oversharpening_halo", analyzer="oversharpening_halo_analyzer/v1", severity="MEDIUM"),
                _finding("missing_source/duplicate.png", severity="LOW"),
                _finding("missing_source/duplicate.png", severity="LOW"),
            ],
            recommendations=[
                _recommendation("missing_source/changed.png", "NEEDS_REVIEW", reason="Measurable finding detected."),
                _recommendation("missing_source/resolved.png", "NEEDS_REVIEW", reason="Measurable finding detected."),
                _recommendation("missing_source/steady.png", "READY_FOR_TRAINING", reason="No findings were emitted."),
            ],
            decisions=[
                {
                    "image_path": "missing_source/changed.png",
                    "decision": "UNDECIDED",
                    "workflow_state": "IN_DATASET",
                },
            ],
        )
        after = _write_output(
            root / "after",
            findings=[
                _finding("missing_source/changed.png", severity="HIGH"),
                _finding("missing_source/new.png", category="artifact.crystalline_faceting", analyzer="crystalline_faceting_analyzer/v1", severity="HIGH"),
                _finding("missing_source/duplicate.png", severity="LOW"),
            ],
            recommendations=[
                _recommendation("missing_source/changed.png", "PRIORITY_REVIEW", reason="High-severity finding detected."),
                _recommendation("missing_source/new.png", "PRIORITY_REVIEW", reason="High-severity finding detected."),
                _recommendation("missing_source/steady.png", "READY_FOR_TRAINING", reason="No findings were emitted."),
            ],
        )
        return before, after

    def test_valid_comparison_builds_json_serializable_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            summary = build_comparison_summary(before, after)

        self.assertEqual(summary["schema"], COMPARISON_SUMMARY_SCHEMA)
        self.assertIn("inspection_compatibility", summary)
        self.assertEqual(summary["recommendation_counts"]["priority_review_count"]["delta"], 2)
        self.assertEqual(json.loads(json.dumps(summary)), summary)

    def test_matching_manifests_are_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _write_output(
                root / "before",
                findings=[],
                recommendations=[],
                manifest=_manifest(),
            )
            after = _write_output(
                root / "after",
                findings=[],
                recommendations=[],
                manifest=_manifest(),
            )

            compatibility = build_comparison_summary(before, after)["inspection_compatibility"]

        self.assertEqual(compatibility["status"], "compatible")
        self.assertTrue(compatibility["before_manifest_available"])
        self.assertTrue(compatibility["after_manifest_available"])
        self.assertEqual(compatibility["warnings"], [])
        self.assertEqual(compatibility["differences"], [])
        self.assertEqual(
            compatibility["manifest_schemas"],
            {
                "before": "dataset-forge/inspection-manifest/v1",
                "after": "dataset-forge/inspection-manifest/v1",
            },
        )
        self.assertEqual(
            compatibility["profiles"],
            {
                "before": {"id": "default", "version": "v1"},
                "after": {"id": "default", "version": "v1"},
            },
        )

    def test_missing_manifests_are_advisory_not_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            compatibility = build_comparison_summary(before, after)["inspection_compatibility"]

        self.assertEqual(compatibility["status"], "provenance_unavailable")
        self.assertFalse(compatibility["before_manifest_available"])
        self.assertFalse(compatibility["after_manifest_available"])
        self.assertIn("provenance compatibility could not be verified", compatibility["warnings"][0])

    def test_one_missing_manifest_is_advisory_not_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _write_output(
                root / "before",
                findings=[],
                recommendations=[],
                manifest=_manifest(),
            )
            after = _write_output(root / "after", findings=[], recommendations=[])

            compatibility = build_comparison_summary(before, after)["inspection_compatibility"]

        self.assertEqual(compatibility["status"], "provenance_unavailable")
        self.assertTrue(compatibility["before_manifest_available"])
        self.assertFalse(compatibility["after_manifest_available"])

    def test_different_manifest_schema_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(),
            _manifest(schema="dataset-forge/inspection-manifest/v2"),
        )

        self.assertEqual(compatibility["status"], "different_manifest_schema")
        self.assertEqual(compatibility["differences"][0]["kind"], "manifest_schema")

    def test_different_tool_version_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(tool_version="0.23.0a0"),
            _manifest(tool_version="0.24.0a0"),
        )

        self.assertEqual(compatibility["status"], "different_tool_version")
        self.assertEqual(compatibility["differences"][0]["kind"], "tool_version")

    def test_different_profile_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(),
            _manifest(profile_id="technical_quality", profile_version="v1"),
        )

        self.assertEqual(compatibility["status"], "different_profile")
        self.assertEqual(compatibility["differences"][0]["kind"], "profile")

    def test_analyzer_participation_difference_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(analyzers=[_manifest_analyzer()]),
            _manifest(analyzers=[]),
        )

        self.assertEqual(compatibility["status"], "different_analyzer_participation")
        self.assertEqual(compatibility["differences"][0]["kind"], "analyzer_participation")

    def test_analyzer_execution_policy_difference_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(analyzers=[_manifest_analyzer()]),
            _manifest(analyzers=[_manifest_analyzer(execution_policy="disabled", executed=False)]),
        )

        self.assertEqual(compatibility["status"], "different_analyzer_participation")
        self.assertEqual(compatibility["differences"][0]["kind"], "analyzer_participation")

    def test_analyzer_version_difference_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(analyzers=[_manifest_analyzer(version="v1")]),
            _manifest(analyzers=[_manifest_analyzer(version="v2")]),
        )

        self.assertEqual(compatibility["status"], "different_analyzer_versions")
        self.assertEqual(compatibility["differences"][0]["kind"], "analyzer_version")

    def test_display_policy_difference_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(analyzers=[_manifest_analyzer(display_policy="visible")]),
            _manifest(analyzers=[_manifest_analyzer(display_policy="hidden")]),
        )

        self.assertEqual(compatibility["status"], "different_display_policy")
        self.assertEqual(compatibility["differences"][0]["kind"], "display_policy")

    def test_triage_policy_difference_warns(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(analyzers=[_manifest_analyzer(triage_policy="included")]),
            _manifest(analyzers=[_manifest_analyzer(triage_policy="excluded")]),
        )

        self.assertEqual(compatibility["status"], "different_triage_policy")
        self.assertEqual(compatibility["differences"][0]["kind"], "triage_policy")

    def test_status_uses_highest_priority_difference(self) -> None:
        compatibility = self._compatibility_for(
            _manifest(profile_id="default", tool_version="0.23.0a0"),
            _manifest(profile_id="other", tool_version="0.24.0a0"),
        )

        self.assertEqual(compatibility["status"], "different_profile")
        self.assertEqual(
            {item["kind"] for item in compatibility["differences"]},
            {"profile", "tool_version"},
        )

    def _compatibility_for(
        self,
        before_manifest: dict[str, object],
        after_manifest: dict[str, object],
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _write_output(
                root / "before",
                findings=[],
                recommendations=[],
                manifest=before_manifest,
            )
            after = _write_output(
                root / "after",
                findings=[],
                recommendations=[],
                manifest=after_manifest,
            )

            return build_comparison_summary(before, after)["inspection_compatibility"]

    def test_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before, after = self._workspace(tmp)
            output = root / "comparison"

            json_path, markdown_path = compare_inspect_outputs(before, after, output)

            self.assertEqual(json_path.name, "comparison_summary.json")
            self.assertEqual(markdown_path.name, "comparison_summary.md")
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8"))["schema"],
                COMPARISON_SUMMARY_SCHEMA,
            )
            self.assertIn(
                "## Images With Changed Recommendations",
                markdown_path.read_text(encoding="utf-8"),
            )

    def test_missing_required_sidecars_fail_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            after.mkdir()

            with self.assertRaisesRegex(ComparisonError, "Missing before inspection report"):
                build_comparison_summary(before, after)

    def test_missing_recommendation_summary_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            (before / "inspection_report.json").write_text(
                json.dumps({"schema": "dataset-forge/inspection/v1"}),
                encoding="utf-8",
            )
            after.mkdir()

            with self.assertRaisesRegex(ComparisonError, "Missing before recommendation summary"):
                build_comparison_summary(before, after)

    def test_malformed_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before"
            before.mkdir()
            (before / "inspection_report.json").write_text("{", encoding="utf-8")
            (before / "recommendation_summary.json").write_text(
                json.dumps({
                    "schema": "dataset-forge/recommendation-summary/v1",
                    "source_report_schema": "dataset-forge/inspection/v1",
                    "summary": {},
                    "recommendations": [],
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ComparisonError, "Malformed JSON"):
                build_comparison_summary(before, root / "after")

    def test_unsupported_schema_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _write_output(
                root / "before",
                findings=[],
                recommendations=[],
                report_schema="dataset-forge/inspection/v99",
            )
            after = _write_output(root / "after", findings=[], recommendations=[])

            with self.assertRaisesRegex(ComparisonError, "Unsupported before inspection report schema"):
                build_comparison_summary(before, after)

    def test_changed_recommendations_are_reported_without_better_worse_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            summary = build_comparison_summary(before, after)
            text = json.dumps(summary).lower()

        self.assertEqual(len(summary["changed_recommendations"]), 1)
        change = summary["changed_recommendations"][0]
        self.assertEqual(change["filename"], "changed.png")
        self.assertEqual(change["before_recommendation"], "Needs Review")
        self.assertEqual(change["after_recommendation"], "Priority Review")
        self.assertNotIn("better", text)
        self.assertNotIn("worse", text)

    def test_new_and_resolved_findings_use_multiset_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            summary = build_comparison_summary(before, after)

        new_keys = [
            (item["filename"], item["category"], item["severity"])
            for item in summary["new_findings"]
        ]
        resolved_keys = [
            (item["filename"], item["category"], item["severity"])
            for item in summary["resolved_findings"]
        ]
        self.assertIn(("new.png", "artifact.crystalline_faceting", "HIGH"), new_keys)
        self.assertIn(("changed.png", "artifact.texture", "HIGH"), new_keys)
        self.assertIn(("changed.png", "artifact.texture", "LOW"), resolved_keys)
        self.assertEqual(resolved_keys.count(("duplicate.png", "artifact.texture", "LOW")), 1)

    def test_category_and_analyzer_deltas_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            summary = build_comparison_summary(before, after)

        categories = {
            item["category"]: item
            for item in summary["finding_category_counts"]
        }
        analyzers = {
            item["analyzer"]: item
            for item in summary["analyzer_output_counts"]
        }
        self.assertEqual(categories["artifact.crystalline_faceting"]["delta"], 1)
        self.assertEqual(categories["artifact.oversharpening_halo"]["delta"], -1)
        self.assertEqual(analyzers["crystalline_faceting_analyzer/v1"]["after"], 1)

    def test_review_decisions_are_summary_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            summary = build_comparison_summary(before, after)

        self.assertEqual(
            summary["review_decisions"],
            {
                "before_available": True,
                "after_available": False,
                "before_decision_count": 1,
                "after_decision_count": 0,
            },
        )
        self.assertNotIn("changed_decisions", summary)

    def test_markdown_order_starts_with_human_review_sections_before_count_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)
            markdown = render_comparison_markdown(build_comparison_summary(before, after))

        self.assertLess(
            markdown.index("## Dataset Summary"),
            markdown.index("## Inspection Compatibility"),
        )
        self.assertLess(
            markdown.index("## Inspection Compatibility"),
            markdown.index("## Images With Changed Recommendations"),
        )
        self.assertLess(
            markdown.index("## Images With Changed Recommendations"),
            markdown.index("## Images With New Findings"),
        )
        self.assertLess(
            markdown.index("## Images With Resolved Findings"),
            markdown.index("## Recommendation Count Changes"),
        )
        self.assertIn("changed.png", markdown)
        self.assertIn("Primary reason:", markdown)

    def test_markdown_renders_manifest_compatibility_warning_near_top(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)
            markdown = render_comparison_markdown(build_comparison_summary(before, after))

        self.assertIn("## Inspection Compatibility", markdown)
        self.assertIn("Status: provenance_unavailable", markdown)
        self.assertIn("provenance compatibility could not be verified", markdown)

    def test_deterministic_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)

            first = build_comparison_summary(before, after)
            second = build_comparison_summary(before, after)

        self.assertEqual(first, second)

    def test_comparison_does_not_modify_inputs_or_read_source_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before, after = self._workspace(tmp)
            before_report = before / "inspection_report.json"
            before_summary = before / "recommendation_summary.json"
            after_report = after / "inspection_report.json"
            after_summary = after / "recommendation_summary.json"
            originals = {
                before_report: before_report.read_text(encoding="utf-8"),
                before_summary: before_summary.read_text(encoding="utf-8"),
                after_report: after_report.read_text(encoding="utf-8"),
                after_summary: after_summary.read_text(encoding="utf-8"),
            }

            compare_inspect_outputs(before, after, Path(tmp) / "comparison")

            self.assertFalse((Path(tmp) / "missing_source").exists())
            for path, content in originals.items():
                self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
