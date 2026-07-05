import io
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
        self.assertIn("Dataset Forge v0.14.0-alpha", stdout)
        self.assertIn("inspect", stdout)
        self.assertIn("review", stdout)
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
        self.assertIn("Dataset ->", stdout)
        self.assertIn("DatasetContext -> Analyzer -> Finding -> Report", stdout)
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
        self.assertEqual(stdout.strip(), "dataset-forge 0.14.0a0")

    def test_future_commands_are_not_public(self) -> None:
        for command in (
            "run",
            "resume",
            "simulate",
            "plugins",
            "texture-report",
            "health-report",
            "plan",
            "execute-plan",
            "traditional-cleanup",
        ):
            with self.subTest(command=command):
                exit_code, stdout, stderr = self._run([command, "--help"])

                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("not part of the public v0.14.0-alpha CLI", stderr)

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
            self.assertIn("Ready for Training:", stdout)
            self.assertIn("Needs Review:", stdout)
            self.assertIn("Priority Review:", stdout)
            self.assertIn("Recommendations are advisory", stdout)
            self.assertIn("Source images were not modified.", stdout)
            self.assertIn("recommendation_summary.json", stdout)
            self.assertIn("recommendation_summary.md", stdout)
            self.assertIn("review_decisions_template.json", stdout)

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
