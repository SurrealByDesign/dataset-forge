import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np
from PIL import Image

from dataset_forge.cli import main


class PublicCliSurfaceTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_root_help_exposes_only_alpha_surface(self) -> None:
        exit_code, stdout, stderr = self._run(["--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Dataset Forge: inspect LoRA/image datasets", stdout)
        self.assertIn("inspect", stdout)
        self.assertIn("review", stdout)
        self.assertIn("compare", stdout)
        self.assertIn("plan", stdout)
        self.assertIn("preview", stdout)
        self.assertIn("preview-import", stdout)
        self.assertIn("--help", stdout)
        self.assertIn("--version", stdout)
        for hidden in (
            "cleanup",
            "plugins",
            "export",
            "texture-report",
            "health-report",
            "run",
            "resume",
            "simulate",
        ):
            self.assertNotIn(hidden, stdout)

    def test_inspect_help_is_read_only_alpha_help(self) -> None:
        exit_code, stdout, stderr = self._run(["inspect", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge inspect", stdout)
        self.assertIn("Inspect a folder of images", stdout)
        self.assertIn("Source images are never modified", stdout)
        self.assertIn("--output", stdout)
        self.assertIn("--gallery", stdout)
        self.assertIn("--review-gallery", stdout)
        self.assertIn("--contact-sheets", stdout)
        self.assertNotIn("cleanup", stdout.lower())
        self.assertNotIn("export", stdout.lower())

    def test_version_is_public(self) -> None:
        exit_code, stdout, stderr = self._run(["--version"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.strip(), "dataset-forge 1.8.0")

    def test_future_commands_are_not_public(self) -> None:
        for command in (
            "run",
            "resume",
            "simulate",
            "plugins",
            "texture-report",
            "health-report",
            "execute-plan",
            "traditional-cleanup",
        ):
            with self.subTest(command=command):
                exit_code, stdout, stderr = self._run([command, "--help"])

                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("not part of the public Dataset Forge CLI", stderr)

    def test_review_help_is_local_only_help(self) -> None:
        exit_code, stdout, stderr = self._run(["review", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge review", stdout)
        self.assertIn("review_decisions.json", stdout)
        self.assertIn("Source images and reports are not modified", stdout)
        self.assertNotIn("cleanup", stdout.lower())
        self.assertNotIn("export", stdout.lower())

    def test_review_requires_inspection_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = self._run(["review", tmp, "--port", "0"])

        self.assertEqual(exit_code, 2)
        self.assertIn("Dataset Forge Review", stdout)
        self.assertIn("Missing required sidecar", stderr)

    def test_compare_help_is_sidecar_only_help(self) -> None:
        exit_code, stdout, stderr = self._run(["compare", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge compare", stdout)
        self.assertIn("inspect output", stdout.lower())
        self.assertIn("comparison_summary.json", stdout)
        self.assertNotIn("cleanup", stdout.lower())
        self.assertNotIn("export", stdout.lower())

    def test_compare_requires_sidecars_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before"
            after = root / "after"
            output = root / "comparison"
            before.mkdir()
            after.mkdir()

            exit_code, stdout, stderr = self._run([
                "compare",
                str(before),
                str(after),
                "--output",
                str(output),
            ])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Missing before inspection report", stderr)

    def test_plan_help_is_sidecar_only_help(self) -> None:
        exit_code, stdout, stderr = self._run(["plan", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge plan", stdout)
        self.assertIn("Improvement Plan", stdout)
        self.assertIn("Source images are not modified", stdout)
        self.assertNotIn("cleanup", stdout.lower())
        self.assertNotIn("export", stdout.lower())

    def test_plan_requires_inspection_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = self._run(["plan", tmp])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Missing inspection report", stderr)

    def test_preview_help_is_execution_free_help(self) -> None:
        exit_code, stdout, stderr = self._run(["preview", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge preview", stdout)
        self.assertIn("Improvement Preview", stdout)
        self.assertIn("Source images are not modified", stdout)
        self.assertNotIn("cleanup", stdout.lower())
        self.assertNotIn("export", stdout.lower())

    def test_preview_requires_inspection_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code, stdout, stderr = self._run(["preview", tmp])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Missing inspection report", stderr)

    def test_preview_import_help_and_successful_isolated_copy(self) -> None:
        exit_code, stdout, stderr = self._run(["preview-import", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge preview-import", stdout)
        self.assertIn("does not generate, process, export, or replace images", stdout)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            candidate = root / "candidate.png"
            Image.fromarray(np.full((16, 16, 3), 80, dtype=np.uint8)).save(source)
            Image.fromarray(np.full((16, 16, 3), 160, dtype=np.uint8)).save(candidate)
            record = {
                "image": {"path": str(source), "filename": source.name},
                "recommended_operation": "REPLACE_SOURCE",
                "current_findings": [],
                "required_provider_type": "MANUAL",
                "preview_status": "WAITING_FOR_PROVIDER",
                "approval_state": "NOT_REQUESTED",
            }
            (output / "improvement_preview.json").write_text(
                json.dumps({
                    "schema": "dataset-forge/improvement-preview/v1",
                    "preview_records": [record],
                    "preview_entries": [record],
                }),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self._run([
                "preview-import", str(output), str(source), str(candidate),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Dataset Forge Preview Import", stdout)
            self.assertTrue((output / "preview_artifacts.json").is_file())
            self.assertTrue(any((output / "preview_artifacts").rglob("candidate-*")))

    def test_preview_writes_improvement_preview_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            (output / "inspection_report.json").write_text(
                '{"schema":"dataset-forge/inspection/v1","findings":[]}',
                encoding="utf-8",
            )
            (output / "recommendation_summary.json").write_text(
                (
                    '{"schema":"dataset-forge/recommendation-summary/v1",'
                    '"source_report_schema":"dataset-forge/inspection/v1",'
                    '"summary":{"image_count":0},"recommendations":[]}'
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self._run(["preview", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Improvement Preview written", stdout)
            self.assertIn("Provider implementations: Not Implemented", stdout)
            self.assertTrue((output / "improvement_preview.json").is_file())
            self.assertTrue((output / "improvement_preview.md").is_file())

    def test_inspect_prints_recommendation_summary_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset"
            output = root / "output"
            dataset.mkdir()
            Image.fromarray(np.full((32, 32, 3), 128, dtype=np.uint8)).save(
                dataset / "img.png"
            )

            exit_code, stdout, stderr = self._run([
                "inspect",
                str(dataset),
                "--output",
                str(output),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Recommendation Summary", stdout)
            self.assertIn("No Findings Emitted:", stdout)
            self.assertIn("Needs Review:", stdout)
            self.assertIn("Priority Review:", stdout)
            self.assertIn("Recommendations are advisory", stdout)
            self.assertIn("Execution, cleanup, export, and source-image modification are out of scope.", stdout)
            self.assertIn("Source images were not modified.", stdout)
            self.assertIn("recommendation_summary.json", stdout)
            self.assertIn("recommendation_summary.md", stdout)
            self.assertIn("triage_dossiers.json", stdout)
            self.assertIn("triage_dossiers.md", stdout)
            self.assertIn("inspection_manifest.json", stdout)
            self.assertIn("review_decisions_template.json", stdout)
            self.assertIn("Start Here", stdout)
            self.assertIn("Review Desk: dataset-forge review", stdout)
            self.assertIn("Output dir:", stdout)

    def test_inspect_review_gallery_flag_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset"
            output = root / "output"
            dataset.mkdir()
            Image.fromarray(np.full((32, 32, 3), 128, dtype=np.uint8)).save(
                dataset / "img.png"
            )

            exit_code, stdout, stderr = self._run([
                "inspect",
                str(dataset),
                "--output",
                str(output),
                "--review-gallery",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertTrue((output / "review_gallery.html").exists())
            self.assertIn("review_gallery.html", stdout)

    def test_inspect_contact_sheets_flag_writes_pngs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset"
            output = root / "output"
            dataset.mkdir()
            Image.fromarray(np.full((32, 32, 3), 128, dtype=np.uint8)).save(
                dataset / "img.png"
            )

            exit_code, stdout, stderr = self._run([
                "inspect",
                str(dataset),
                "--output",
                str(output),
                "--contact-sheets",
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertTrue((output / "priority_review_contact_sheet.png").exists())
            self.assertTrue((output / "needs_review_contact_sheet.png").exists())
            self.assertFalse((output / "ready_for_training_contact_sheet.png").exists())
            self.assertIn("priority_review_contact_sheet.png", stdout)
            self.assertIn("needs_review_contact_sheet.png", stdout)

    def test_public_cli_has_no_recommend_command(self) -> None:
        exit_code, stdout, stderr = self._run(["recommend", "--help"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("unknown command: recommend", stderr)


if __name__ == "__main__":
    unittest.main()
