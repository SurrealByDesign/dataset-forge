import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dataset_forge.cleanup import (
    ApprovalRequiredError,
    PlanControlError,
    PlanControlManager,
    SelectionFilter,
    require_approved_plan,
    review_plan,
)
from dataset_forge.cleanup.controls import (
    APPROVED_PLAN_CSV,
    APPROVED_PLAN_JSON,
    AUDIT_LOG,
    OVERRIDES_JSON,
)
from dataset_forge.cli import main


class PlanControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.output = Path(self.temp.name)
        _write_plan(self.output)
        _write_manifest(self.output)
        _write_recommendations(self.output)
        self.manager = PlanControlManager(self.output)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_single_override_is_separate_and_persistent(self) -> None:
        self.manager.override(
            "castle.png",
            "KEEP",
            reason="Good target style already",
        )
        raw = json.loads(
            (self.output / "cleanup_plan.json").read_text(encoding="utf-8")
        )
        controls = self.manager.load_controls()
        approved = json.loads(
            (self.output / APPROVED_PLAN_JSON).read_text(encoding="utf-8")
        )
        self.assertEqual(raw["decisions"][0]["action"], "CLEAN_STRONG")
        self.assertEqual(controls["castle-id"]["override_action"], "KEEP")
        self.assertEqual(approved["decisions"][0]["status"], "overridden")
        self.assertTrue((self.output / APPROVED_PLAN_CSV).is_file())

    def test_lock_prevents_changes_until_unlock(self) -> None:
        self.manager.lock("castle.png", "KEEP")
        with self.assertRaises(PlanControlError):
            self.manager.override("castle.png", "EXCLUDE")
        self.manager.unlock("castle.png")
        decision = self.manager.override("castle.png", "EXCLUDE")[0]
        self.assertEqual(decision["action"], "EXCLUDE")
        self.assertFalse(decision["locked"])

    def test_approval_rejection_and_plan_completion(self) -> None:
        self.manager.approve("castle.png")
        self.manager.reject("banana.png")
        approved = self.manager.effective_plan()
        self.assertTrue(approved["approval_complete"])
        self.assertTrue(approved["decisions"][0]["execution_eligible"])
        self.assertFalse(approved["decisions"][1]["execution_eligible"])
        self.assertEqual(approved["decisions"][1]["status"], "rejected")

    def test_bulk_filters_use_manifest_recommendations_and_action(self) -> None:
        changed = self.manager.override(
            None,
            "CLEAN_LIGHT",
            filters=(SelectionFilter("artifact_score_gt", "70"),),
        )
        approved = self.manager.approve(
            None,
            filters=(SelectionFilter("severity", "WARNING"),),
        )
        locked = self.manager.lock(
            None,
            filters=(SelectionFilter("action", "KEEP"),),
        )
        self.manager.approve_all()
        self.assertEqual([item["filename"] for item in changed], ["castle.png"])
        self.assertEqual([item["filename"] for item in approved], ["castle.png"])
        self.assertEqual([item["filename"] for item in locked], ["banana.png"])
        banana = self.manager.effective_plan()["decisions"][1]
        self.assertTrue(banana["locked"])
        self.assertFalse(banana["override_status"])

    def test_audit_log_records_actions_and_reasons(self) -> None:
        self.manager.override("castle.png", "KEEP", reason="Already clean")
        record = json.loads(
            (self.output / AUDIT_LOG).read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(record["previous_action"], "CLEAN_STRONG")
        self.assertEqual(record["new_action"], "KEEP")
        self.assertEqual(record["user_command"], "override")
        self.assertEqual(record["reason"], "Already clean")
        self.assertTrue(record["timestamp"])

    def test_safety_gate_requires_a_complete_approved_plan(self) -> None:
        with self.assertRaises(ApprovalRequiredError):
            require_approved_plan(self.output)
        self.manager.approve_all()
        self.assertEqual(
            require_approved_plan(self.output),
            self.output / APPROVED_PLAN_JSON,
        )
        self.assertIsNone(require_approved_plan(self.output, force=True))

    def test_reset_removes_controls_without_changing_raw_plan(self) -> None:
        self.manager.override("castle.png", "KEEP")
        self.manager.reset()
        self.assertFalse((self.output / OVERRIDES_JSON).exists())
        approved = self.manager.effective_plan()
        self.assertEqual(approved["decisions"][0]["action"], "CLEAN_STRONG")
        self.assertEqual(approved["decisions"][0]["status"], "proposed")

    def test_review_mode_can_override_approve_and_reject(self) -> None:
        answers = iter(["l", "r"])
        output: list[str] = []
        reviewed = review_plan(
            self.manager,
            input_func=lambda _prompt: next(answers),
            output_func=output.append,
        )
        plan = self.manager.effective_plan()
        self.assertEqual(reviewed, 2)
        self.assertEqual(plan["decisions"][0]["action"], "CLEAN_LIGHT")
        self.assertEqual(plan["decisions"][0]["approval_status"], "approved")
        self.assertEqual(plan["decisions"][1]["approval_status"], "rejected")
        self.assertIn("Artifact score: 85", output[0])

    def test_cli_override_approve_and_show(self) -> None:
        output = str(self.output)
        self.assertEqual(
            main(
                [
                    "override",
                    "castle.png",
                    "--action",
                    "KEEP",
                    "--reason",
                    "Looks right",
                    "--output",
                    output,
                ]
            ),
            0,
        )
        self.assertEqual(
            main(["approve", "castle.png", "--output", output]),
            0,
        )
        self.assertEqual(main(["show-overrides", "--output", output]), 0)


def _write_plan(output: Path) -> None:
    decisions = [
        _decision("castle-id", "castle.png", "CLEAN_STRONG"),
        _decision("banana-id", "banana.png", "KEEP"),
    ]
    (output / "cleanup_plan.json").write_text(
        json.dumps(
            {
                "version": 1,
                "total_images": 2,
                "action_counts": {"CLEAN_STRONG": 1, "KEEP": 1},
                "decisions": decisions,
            }
        ),
        encoding="utf-8",
    )


def _decision(image_id: str, filename: str, action: str) -> dict[str, object]:
    return {
        "image_id": image_id,
        "filename": filename,
        "action": action,
        "confidence": 90,
        "explanation": "Measured evidence supports this decision.",
        "expected_benefit": "+10 quality points",
        "before_quality_score": 50,
        "estimated_after_quality_score": 60,
        "estimated_quality_delta": 10,
        "recommended_plugin": "cleanup.placeholder",
        "recommended_preset": "general_ai_artifact_cleanup",
        "recommended_strength": "medium",
        "estimated_runtime": "seconds",
        "estimated_disk_write": 0,
        "estimated_gpu_required": False,
        "warnings": [],
    }


def _write_manifest(output: Path) -> None:
    path = output / "manifest_v3.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "filename",
                "artifact_score",
                "overall_quality_score",
                "texture_score",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "filename": "castle.png",
                "artifact_score": 85,
                "overall_quality_score": 45,
                "texture_score": 70,
            }
        )
        writer.writerow(
            {
                "filename": "banana.png",
                "artifact_score": 10,
                "overall_quality_score": 90,
                "texture_score": 20,
            }
        )
    (output / "manifest_latest.json").write_text(
        '{"path": "manifest_v3.csv"}',
        encoding="utf-8",
    )


def _write_recommendations(output: Path) -> None:
    with (output / "recommendations.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "severity"])
        writer.writeheader()
        writer.writerow({"filename": "castle.png", "severity": "WARNING"})
        writer.writerow({"filename": "banana.png", "severity": "INFO"})


if __name__ == "__main__":
    unittest.main()
