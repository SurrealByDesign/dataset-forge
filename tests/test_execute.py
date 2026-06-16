import csv
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dataset_forge.cleanup import (
    ApprovalRequiredError,
    ExecutionSummary,
    PlanControlManager,
    execute_plan,
)
from dataset_forge.cleanup.execute import (
    EXECUTION_REPORT_CSV,
    EXECUTION_REPORT_JSON,
    PROCESSED_DIR,
)
from dataset_forge.cli import main


class ExecutePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.output = Path(self.temp.name) / "output"
        self.output.mkdir(parents=True)
        self.images = Path(self.temp.name) / "images"
        self.images.mkdir(parents=True)

        self.sources = {
            "img_a.png": _write_source(self.images / "img_a.png", b"alpha"),
            "img_b.png": _write_source(self.images / "img_b.png", b"bravo"),
            "img_c.png": _write_source(self.images / "img_c.png", b"charlie"),
            "img_d.png": _write_source(self.images / "img_d.png", b"delta"),
            "img_e.png": _write_source(self.images / "img_e.png", b"echo"),
            "img_f.png": _write_source(self.images / "img_f.png", b"foxtrot"),
        }

        _write_plan(self.output)
        _write_manifest(self.output, self.sources)
        self.manager = PlanControlManager(self.output)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _approve_full_plan(self) -> None:
        self.manager.approve("img_a.png")
        self.manager.lock("img_b.png")
        self.manager.approve("img_c.png")
        self.manager.approve("img_d.png")
        self.manager.reject("img_e.png")
        self.manager.approve("img_f.png")

    def test_blocked_without_approved_plan(self) -> None:
        with self.assertRaises(ApprovalRequiredError):
            execute_plan(self.output)

    def test_blocked_with_incomplete_approved_plan(self) -> None:
        self.manager.approve("img_a.png")
        with self.assertRaises(ApprovalRequiredError):
            execute_plan(self.output)

    def test_dry_run_writes_nothing(self) -> None:
        self._approve_full_plan()
        summary = execute_plan(self.output, dry_run=True)
        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.approved_items, 3)
        self.assertEqual(summary.executed, 3)
        self.assertFalse((self.output / PROCESSED_DIR).exists())
        self.assertFalse((self.output / EXECUTION_REPORT_JSON).exists())
        self.assertFalse((self.output / EXECUTION_REPORT_CSV).exists())

    def test_only_approved_eligible_actions_execute(self) -> None:
        self._approve_full_plan()
        summary = execute_plan(self.output)
        executed_filenames = {
            record["filename"]
            for record in summary.records
            if record["status"] == "completed"
        }
        self.assertEqual(executed_filenames, {"img_a.png", "img_b.png", "img_d.png"})
        self.assertEqual(summary.approved_items, 3)
        self.assertEqual(summary.executed, 3)

    def test_skipped_actions_are_not_processed(self) -> None:
        self._approve_full_plan()
        summary = execute_plan(self.output)
        by_filename = {record["filename"]: record for record in summary.records}
        self.assertEqual(by_filename["img_c.png"]["status"], "skipped")
        self.assertIn("not eligible", by_filename["img_c.png"]["skipped_reason"])
        self.assertEqual(by_filename["img_e.png"]["status"], "skipped")
        self.assertIn("rejected", by_filename["img_e.png"]["skipped_reason"])
        self.assertEqual(by_filename["img_f.png"]["status"], "skipped")
        self.assertIn("not eligible", by_filename["img_f.png"]["skipped_reason"])
        processed = {p.name for p in (self.output / PROCESSED_DIR).iterdir()}
        self.assertNotIn("img_c_clean_light.png", processed)
        self.assertNotIn("img_e_clean_strong.png", processed)
        self.assertNotIn("img_f_clean_light.png", processed)

    def test_placeholder_output_creation(self) -> None:
        self._approve_full_plan()
        execute_plan(self.output)
        output_file = self.output / PROCESSED_DIR / "img_a_clean_light.png"
        self.assertTrue(output_file.is_file())
        self.assertEqual(output_file.read_bytes(), b"alpha")
        metadata_file = output_file.with_name(output_file.name + ".json")
        self.assertTrue(metadata_file.is_file())
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        self.assertTrue(metadata["placeholder"])
        self.assertEqual(metadata["action"], "CLEAN_LIGHT")

    def test_no_overwrite_behavior(self) -> None:
        self._approve_full_plan()
        execute_plan(self.output)
        execute_plan(self.output, force=True)
        processed = self.output / PROCESSED_DIR
        self.assertTrue((processed / "img_a_clean_light.png").is_file())
        self.assertTrue((processed / "img_a_clean_light_2.png").is_file())
        self.assertEqual(
            (processed / "img_a_clean_light.png").read_bytes(),
            (processed / "img_a_clean_light_2.png").read_bytes(),
        )

    def test_source_image_hash_unchanged(self) -> None:
        self._approve_full_plan()
        before = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in self.sources.items()
        }
        execute_plan(self.output)
        execute_plan(self.output, force=True)
        after = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in self.sources.items()
        }
        self.assertEqual(before, after)

    def test_execution_report_generation(self) -> None:
        self._approve_full_plan()
        summary = execute_plan(self.output)
        json_path = self.output / EXECUTION_REPORT_JSON
        csv_path = self.output / EXECUTION_REPORT_CSV
        self.assertTrue(json_path.is_file())
        self.assertTrue(csv_path.is_file())
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["approved_items"], 3)
        self.assertEqual(data["executed"], 3)
        self.assertEqual(len(data["records"]), 6)
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 6)
        self.assertIn("image_id", rows[0])
        self.assertIn("output_path", rows[0])

    def test_resume_skips_completed_items(self) -> None:
        self._approve_full_plan()
        first = execute_plan(self.output)
        self.assertEqual(first.executed, 3)
        second = execute_plan(self.output)
        statuses = {
            record["filename"]: record["status"]
            for record in second.records
            if record["filename"] in {"img_a.png", "img_b.png", "img_d.png"}
        }
        self.assertEqual(set(statuses.values()), {"skipped"})
        self.assertEqual(second.executed, 0)
        processed = self.output / PROCESSED_DIR
        self.assertEqual(len(list(processed.iterdir())), 3 * 2)

    def test_force_reruns_completed_items(self) -> None:
        self._approve_full_plan()
        execute_plan(self.output)
        second = execute_plan(self.output, force=True)
        self.assertEqual(second.executed, 3)
        processed = self.output / PROCESSED_DIR
        # Each of the 3 images now has two non-overwritten copies plus
        # matching metadata sidecars: 3 images * 2 runs * 2 files.
        self.assertEqual(len(list(processed.iterdir())), 3 * 2 * 2)

    def test_limit_restricts_executed_items(self) -> None:
        self._approve_full_plan()
        summary = execute_plan(self.output, limit=1)
        self.assertEqual(summary.executed, 1)
        limited = [
            record
            for record in summary.records
            if record["skipped_reason"] == "execution limit reached"
        ]
        self.assertEqual(len(limited), 2)

    def test_cli_execute_plan_dry_run(self) -> None:
        self._approve_full_plan()
        result = main(["execute-plan", "--output", str(self.output), "--dry-run"])
        self.assertEqual(result, 0)
        self.assertFalse((self.output / PROCESSED_DIR).exists())

    def test_cli_execute_plan_blocked(self) -> None:
        result = main(["execute-plan", "--output", str(self.output)])
        self.assertEqual(result, 2)


def _write_source(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _write_plan(output: Path) -> None:
    decisions = [
        _decision("a-id", "img_a.png", "CLEAN_LIGHT"),
        _decision("b-id", "img_b.png", "CLEAN_MEDIUM"),
        _decision("c-id", "img_c.png", "KEEP"),
        _decision("d-id", "img_d.png", "CAPTION_ONLY"),
        _decision("e-id", "img_e.png", "CLEAN_STRONG"),
        _decision("f-id", "img_f.png", "MANUAL_REVIEW"),
    ]
    (output / "cleanup_plan.json").write_text(
        json.dumps(
            {
                "version": 1,
                "total_images": len(decisions),
                "action_counts": {},
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


def _write_manifest(output: Path, sources: dict[str, Path]) -> None:
    path = output / "manifest_v1.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["filename", "original_path"],
        )
        writer.writeheader()
        for filename, source in sources.items():
            writer.writerow({"filename": filename, "original_path": str(source)})
    (output / "manifest_latest.json").write_text(
        json.dumps({"path": "manifest_v1.csv"}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
