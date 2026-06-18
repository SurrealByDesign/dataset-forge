import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.cli import future_main as main


class PipelineCliTests(unittest.TestCase):
    def test_simulate_previews_profile_without_writing(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            Image.new("RGB", (16, 16), "white").save(source / "sample.png")
            output_path = root / "output"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "simulate",
                        "--pipeline",
                        "default",
                        "--profile",
                        "eco",
                        "--input",
                        str(source),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertFalse(output_path.exists())
            self.assertIn("Execution profile: eco", output.getvalue())
            self.assertIn("Simulation complete", output.getvalue())

    def test_run_applies_profile_overrides(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            Image.new("RGB", (16, 16), "white").save(source / "sample.png")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "run",
                        "--pipeline",
                        "default",
                        "--profile",
                        "eco",
                        "--max-workers",
                        "3",
                        "--cache-policy",
                        "aggressive",
                        "--input",
                        str(source),
                        "--output",
                        str(root / "output"),
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Worker count: 3", output.getvalue())
            self.assertIn("Cache policy: aggressive", output.getvalue())

    def test_default_pipeline_cli_dry_run_is_read_only(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            Image.new("RGB", (16, 16), "white").save(source / "sample.png")
            output_path = root / "output"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "run",
                        "--pipeline",
                        "default",
                        "--input",
                        str(source),
                        "--output",
                        str(output_path),
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertFalse(output_path.exists())
            self.assertIn("scan: RUN", output.getvalue())
            self.assertIn("Dry run complete", output.getvalue())

    def test_default_pipeline_cli_runs_and_resumes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            image_path = source / "sample.png"
            Image.new("RGB", (32, 24), "gray").save(image_path)
            before = image_path.read_bytes()
            output_path = root / "output"

            first_exit = main(
                [
                    "run",
                    "--pipeline",
                    "default",
                    "--input",
                    str(source),
                    "--output",
                    str(output_path),
                    "--no-thumbnails",
                ]
            )
            second_exit = main(["resume", "--output", str(output_path)])

            state = json.loads(
                (output_path / "pipeline_state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            self.assertEqual(state["status"], "completed")
            self.assertTrue((output_path / "manifest_v1.csv").is_file())
            self.assertTrue((output_path / "manifest_v2.csv").is_file())
            self.assertTrue((output_path / "manifest_v3.csv").is_file())
            self.assertTrue((output_path / "manifest_latest.json").is_file())
            self.assertTrue((output_path / "pipeline_report.json").is_file())
            self.assertTrue(
                all(stage["status"] == "skipped" for stage in state["stages"])
            )
            self.assertEqual(before, image_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
