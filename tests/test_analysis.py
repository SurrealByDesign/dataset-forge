import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from dataset_forge.analysis import assign_duplicate_references, extract_image_metrics
from dataset_forge.pipeline import PipelineOptions, run_pipeline
from dataset_forge.reporting import build_dataset_report


class AnalysisTests(unittest.TestCase):
    def test_extracts_image_metrics(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "gradient.png"
            image = Image.new("RGB", (120, 80))
            draw = ImageDraw.Draw(image)
            for x in range(image.width):
                value = round(x / (image.width - 1) * 255)
                draw.line((x, 0, x, image.height), fill=(value, 80, 255 - value))
            image.save(path)

            metrics = extract_image_metrics(path)

            self.assertEqual(metrics.width, 120)
            self.assertEqual(metrics.height, 80)
            self.assertEqual(metrics.aspect_ratio, 1.5)
            self.assertEqual(metrics.megapixels, 0.0096)
            self.assertEqual(metrics.color_mode, "RGB")
            self.assertEqual(len(metrics.perceptual_hash), 16)
            self.assertEqual(len(metrics.file_hash), 64)
            for value in (
                metrics.average_brightness,
                metrics.average_saturation,
                metrics.average_contrast,
                metrics.texture_score,
                metrics.artifact_score,
            ):
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 100)

    def test_detects_exact_duplicates(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.png"
            second = root / "second.png"
            image = Image.new("RGB", (32, 32), (10, 20, 30))
            image.save(first)
            image.save(second)
            rows = [_analysis_row(first), _analysis_row(second)]

            exact_count, probable_count = assign_duplicate_references(rows)

            self.assertEqual(exact_count, 1)
            self.assertEqual(probable_count, 0)
            self.assertEqual(rows[1]["exact_duplicate_of"], str(first))

    def test_detects_probable_duplicates(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.png"
            second = root / "second.png"
            Image.new("RGB", (32, 32), (100, 100, 100)).save(first)
            Image.new("RGB", (32, 32), (102, 102, 102)).save(second)
            rows = [_analysis_row(first), _analysis_row(second)]

            exact_count, probable_count = assign_duplicate_references(rows)

            self.assertEqual(exact_count, 0)
            self.assertEqual(probable_count, 1)
            self.assertEqual(rows[1]["probable_duplicate_of"], str(first))

    def test_does_not_match_large_brightness_changes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            dark = root / "dark.png"
            bright = root / "bright.png"
            Image.new("RGB", (32, 32), (20, 20, 20)).save(dark)
            Image.new("RGB", (32, 32), (240, 240, 240)).save(bright)

            counts = assign_duplicate_references(
                [_analysis_row(dark), _analysis_row(bright)]
            )

            self.assertEqual(counts, (0, 0))

    def test_generates_dataset_report_and_read_only_outputs(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            Image.new("RGB", (64, 48), (20, 20, 20)).save(source / "dark.png")
            Image.new("RGB", (48, 64), (240, 240, 240)).save(source / "bright.png")

            summary = run_pipeline(
                PipelineOptions(
                    input_path=source,
                    output_path=output,
                    analyze=True,
                )
            )

            report = json.loads(
                (output / "dataset_report.json").read_text(encoding="utf-8")
            )
            with (output / "manifest.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(summary.images_processed, 2)
            self.assertEqual(report["total_images"], 2)
            self.assertIn("average_resolution", report)
            self.assertIn("recommendations", report)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["file_hash"] for row in rows))
            self.assertFalse((output / "originals").exists())
            self.assertEqual(
                sorted(path.name for path in source.iterdir()),
                ["bright.png", "dark.png"],
            )

    def test_report_orders_highest_artifact_scores(self) -> None:
        rows = [
            _report_row("low.png", artifact=12, brightness=20),
            _report_row("high.png", artifact=88, brightness=90),
        ]

        report = build_dataset_report(rows, duplicate_count=0, probable_duplicate_count=0)

        highest = report["images_with_highest_artifact_scores"]
        self.assertEqual(highest[0]["path"], "high.png")
        self.assertEqual(report["average_artifact_score"], 50)
        self.assertTrue(
            any(
                "brightness variation" in item.lower()
                for item in report["recommendations"]
            )
        )


def _analysis_row(path: Path) -> dict[str, object]:
    metrics = extract_image_metrics(path).to_dict()
    metrics["original_path"] = str(path)
    metrics["status"] = "analyzed"
    return metrics


def _report_row(path: str, artifact: float, brightness: float) -> dict[str, object]:
    return {
        "original_path": path,
        "status": "analyzed",
        "image_width": 100,
        "image_height": 100,
        "megapixels": 0.01,
        "texture_score": 20,
        "artifact_score": artifact,
        "aspect_ratio": 1,
        "average_brightness": brightness,
    }


if __name__ == "__main__":
    unittest.main()
