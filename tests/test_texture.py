import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image

from dataset_forge.analysis.texture import evaluate_texture, generate_texture_report
from dataset_forge.cli import main
from dataset_forge.evidence import Evidence, ImageEvidence
from dataset_forge.recommendations.engine import recommend_evidence


class TextureEvaluatorTests(unittest.TestCase):
    def test_synthetic_texture_signals_and_ranked_reports(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            paths = _write_synthetic_images(source)
            before = {path.name: path.read_bytes() for path in paths}

            summary = generate_texture_report(source, output, thumbnail_size=64)
            report = json.loads(
                (output / "texture_report.json").read_text(encoding="utf-8")
            )
            by_name = {item["filename"]: item for item in report["images"]}

            self.assertEqual(summary.analyzed_images, 4)
            self.assertGreater(
                by_name["noisy.png"]["microtexture_density_score"],
                by_name["smooth.png"]["microtexture_density_score"],
            )
            self.assertGreater(
                by_name["oversharpened.png"]["edge_sharpness_score"],
                by_name["smooth.png"]["edge_sharpness_score"],
            )
            self.assertGreater(
                by_name["speckled.png"]["highlight_speck_score"],
                by_name["smooth.png"]["highlight_speck_score"],
            )
            self.assertEqual(by_name["smooth.png"]["recommendation"], "KEEP")
            self.assertIn(
                by_name["noisy.png"]["recommendation"],
                {"TEXTURE_NORMALIZE_MEDIUM", "MANUAL_REVIEW"},
            )
            self.assertTrue(by_name["smooth.png"]["explanation"])
            self.assertTrue((output / "texture_report.csv").is_file())
            page = (output / "texture_report.html").read_text(encoding="utf-8")
            self.assertIn("Highest microtexture", page)
            self.assertIn("Most representative", page)
            self.assertIn("Cleanest", page)
            self.assertNotIn("https://", page)
            self.assertEqual(len(list((output / "texture_thumbnails").glob("*.jpg"))), 4)
            self.assertEqual(
                before,
                {path.name: path.read_bytes() for path in paths},
            )

    def test_csv_contains_all_texture_metrics(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            Image.new("RGB", (64, 64), "gray").save(source / "sample.png")
            generate_texture_report(source, root / "output", create_thumbnails=False)
            with (root / "output" / "texture_report.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                row = next(csv.DictReader(handle))
            for field in (
                "microtexture_density_score",
                "local_contrast_score",
                "edge_sharpness_score",
                "highlight_speck_score",
                "texture_consistency_score",
                "watercolor_smoothness_score",
                "pencil_grain_score",
                "recommendation",
                "explanation",
            ):
                self.assertIn(field, row)
            self.assertFalse((root / "output" / "texture_thumbnails").exists())

    def test_cli_writes_texture_report(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            Image.new("RGB", (64, 64), "gray").save(source / "sample.png")
            output = root / "output"
            exit_code = main(
                [
                    "texture-report",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                    "--no-thumbnails",
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "texture_report.json").is_file())
            self.assertTrue((output / "texture_report.csv").is_file())
            self.assertTrue((output / "texture_report.html").is_file())

    def test_unreadable_analyzer_emits_evidence_and_engine_routes_review(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "broken.png"
            path.write_bytes(b"not an image")
            result = evaluate_texture(path)
            self.assertEqual(result.status, "error")
            self.assertEqual(result.recommendation, "")
            evidence = Evidence(
                images=[
                    ImageEvidence(
                        image_id="broken",
                        filename=result.filename,
                        original_path=result.original_path,
                        status=result.status,
                        error=result.error,
                    )
                ]
            )
            self.assertEqual(
                recommend_evidence(evidence)[0].action,
                "MANUAL_REVIEW",
            )


def _write_synthetic_images(folder: Path) -> list[Path]:
    size = 192
    smooth = np.full((size, size), 128, dtype=np.uint8)
    rng = np.random.default_rng(42)
    noisy = np.clip(
        smooth.astype(np.int16) + rng.normal(0, 45, smooth.shape),
        0,
        255,
    ).astype(np.uint8)
    checker = ((np.indices((size, size)).sum(axis=0) // 3) % 2 * 255).astype(
        np.uint8
    )
    oversharpened = cv2.addWeighted(checker, 2.2, cv2.GaussianBlur(checker, (0, 0), 1), -1.2, 0)
    speckled = smooth.copy()
    points = rng.integers(2, size - 2, size=(400, 2))
    speckled[points[:, 0], points[:, 1]] = 255
    arrays = {
        "smooth.png": smooth,
        "noisy.png": noisy,
        "oversharpened.png": oversharpened,
        "speckled.png": speckled,
    }
    paths = []
    for name, array in arrays.items():
        path = folder / name
        Image.fromarray(array, mode="L").convert("RGB").save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    unittest.main()
