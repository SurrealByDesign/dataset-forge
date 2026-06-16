import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.gallery import generate_review_gallery
from dataset_forge.pipeline import PipelineOptions, run_pipeline
from dataset_forge.quality import Recommendation


class GalleryTests(unittest.TestCase):
    def test_displays_plan_control_metadata(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            source = root / "source.png"
            Image.new("RGB", (32, 32), "purple").save(source)
            index = generate_review_gallery(
                output,
                [_gallery_row(source)],
                [
                    Recommendation(
                        filename=source.name,
                        severity="INFO",
                        issue="Review",
                        recommended_action="Recommend review",
                        reason="Review this image.",
                    )
                ],
                {"dataset_health_score": 70, "total_images": 1},
                create_thumbnails=False,
                decision_metadata={
                    source.name: {
                        "generated_action": "CLEAN_LIGHT",
                        "approval_status": "approved",
                        "override_status": True,
                        "locked": True,
                    }
                },
            )

            page = index.read_text(encoding="utf-8")
            self.assertIn("Proposed action:</strong> CLEAN_LIGHT", page)
            self.assertIn("Approval status:</strong> approved", page)
            self.assertIn("Override status:</strong> overridden", page)
            self.assertIn("Locked status:</strong> locked", page)

    def test_generates_offline_gallery_with_review_fields(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sample.png"
            Image.new("RGB", (400, 300), (80, 110, 140)).save(source)
            row = _gallery_row(source)
            recommendation = Recommendation(
                filename=source.name,
                severity="WARNING",
                issue="Elevated artifact burden",
                recommended_action="Recommend cleanup",
                reason="Artifact score is elevated.",
                suggested_preset="general_artifact_cleanup",
                suggested_strength="medium",
            )

            index = generate_review_gallery(
                root / "output",
                [row],
                [recommendation],
                _health_report(),
            )
            page = index.read_text(encoding="utf-8")

            self.assertIn("Dataset Forge Review Gallery", page)
            self.assertIn("<span>Quality</span>", page)
            self.assertIn("Artifact", page)
            self.assertIn("Texture", page)
            self.assertIn("Duplicate risk", page)
            self.assertIn("Recommend cleanup", page)
            self.assertIn("general_artifact_cleanup", page)
            self.assertIn('id="sort"', page)
            self.assertIn('id="severity"', page)
            self.assertNotIn("https://", page)
            self.assertNotIn("http://", page)

    def test_creates_bounded_thumbnails(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "large.png"
            Image.new("RGB", (1200, 800), (20, 40, 60)).save(source)

            generate_review_gallery(
                root / "output",
                [_gallery_row(source)],
                [_keep_recommendation(source.name)],
                _health_report(),
                thumbnail_size=96,
            )

            thumbnails = list(
                (root / "output" / "review_gallery" / "thumbnails").glob("*.jpg")
            )
            self.assertEqual(len(thumbnails), 1)
            with Image.open(thumbnails[0]) as thumbnail:
                self.assertLessEqual(thumbnail.width, 96)
                self.assertLessEqual(thumbnail.height, 96)

    def test_handles_missing_recommendation_data(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "missing.png"
            Image.new("RGB", (100, 100), "gray").save(source)

            index = generate_review_gallery(
                root / "output",
                [_gallery_row(source)],
                [],
                _health_report(),
            )
            page = index.read_text(encoding="utf-8")

            self.assertIn("Recommend review", page)
            self.assertIn("No image-level recommendation data", page)

    def test_uses_safe_thumbnail_paths_and_escapes_metadata(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "quote'&name.png"
            Image.new("RGB", (100, 80), "white").save(source)

            index = generate_review_gallery(
                root / "output",
                [_gallery_row(source)],
                [_keep_recommendation(source.name)],
                _health_report(),
            )
            page = index.read_text(encoding="utf-8")
            thumbnails = list((index.parent / "thumbnails").iterdir())

            self.assertIn("quote&#x27;&amp;name.png", page)
            self.assertEqual(len(thumbnails), 1)
            self.assertRegex(thumbnails[0].name, r"^\d{6}-[0-9a-f]{12}\.jpg$")
            self.assertEqual(thumbnails[0].parent.resolve(), (index.parent / "thumbnails").resolve())
            self.assertIsNone(re.search(r"quote|name", thumbnails[0].name))

    def test_no_thumbnails_references_original_without_copying(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "original.png"
            Image.new("RGB", (640, 480), "navy").save(source)

            index = generate_review_gallery(
                root / "output",
                [_gallery_row(source)],
                [_keep_recommendation(source.name)],
                _health_report(),
                create_thumbnails=False,
            )
            page = index.read_text(encoding="utf-8")

            self.assertIn(source.resolve().as_uri(), page)
            self.assertFalse((index.parent / "thumbnails").exists())
            self.assertFalse((index.parent / source.name).exists())

    def test_pipeline_writes_no_full_size_image_copies(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source_dir = root / "source"
            output = root / "output"
            source_dir.mkdir()
            source = source_dir / "large.png"
            Image.new("RGB", (1400, 1000), (100, 120, 140)).save(source)
            before = source.read_bytes()

            run_pipeline(
                PipelineOptions(
                    input_path=source_dir,
                    output_path=output,
                    review_gallery=True,
                    thumbnail_size=72,
                )
            )

            output_images = [
                path
                for path in output.rglob("*")
                if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            ]
            self.assertEqual(len(output_images), 1)
            with Image.open(output_images[0]) as thumbnail:
                self.assertLessEqual(thumbnail.width, 72)
                self.assertLessEqual(thumbnail.height, 72)
            self.assertEqual(before, source.read_bytes())
            self.assertFalse((output / source.name).exists())


def _gallery_row(source: Path) -> dict[str, object]:
    return {
        "filename": source.name,
        "original_path": str(source),
        "status": "analyzed",
        "overall_quality_score": 72,
        "artifact_score": 58,
        "texture_score": 43,
        "duplicate_risk": 0,
    }


def _keep_recommendation(filename: str) -> Recommendation:
    return Recommendation(
        filename=filename,
        severity="INFO",
        issue="No major quality issue",
        recommended_action="Recommend keep as-is",
        reason="Image metrics are within review thresholds.",
    )


def _health_report() -> dict[str, object]:
    return {
        "dataset_health_score": 87,
        "total_images": 1,
        "images_requiring_cleanup": 0,
        "likely_duplicates": 0,
        "low_resolution_images": 0,
    }


if __name__ == "__main__":
    unittest.main()
