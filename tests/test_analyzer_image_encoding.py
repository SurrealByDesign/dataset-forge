"""Tests for the advisory Image Encoding Analyzer."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from dataset_forge.analyzers.image_encoding import (
    ImageEncodingAnalyzer,
    measure_image_encoding,
)
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Severity
from dataset_forge.recommendation_summary import build_recommendation_summary


def _ctx(paths: list[Path]) -> DatasetContext:
    return DatasetContext.empty(image_paths=paths)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gradient(size: tuple[int, int] = (256, 256)) -> Image.Image:
    x = np.linspace(0, 255, size[0], dtype=np.uint8)
    arr = np.tile(x, (size[1], 1))
    return Image.fromarray(np.dstack([arr, arr, arr]), "RGB")


def _posterized_gradient(size: tuple[int, int] = (256, 256)) -> Image.Image:
    x = np.linspace(0, 255, size[0], dtype=np.uint8)
    x = (x // 32) * 32
    arr = np.tile(x, (size[1], 1))
    return Image.fromarray(np.dstack([arr, arr, arr]), "RGB")


def _block_boundary_image(size: tuple[int, int] = (256, 256)) -> Image.Image:
    rng = np.random.default_rng(2)
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    for y in range(0, size[1], 8):
        for x in range(0, size[0], 8):
            arr[y:y + 8, x:x + 8] = rng.integers(0, 255, size=3)
    return Image.fromarray(arr, "RGB")


def _line_art(size: tuple[int, int] = (256, 256)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for x in range(24, 232, 32):
        draw.line((x, 20, x, 236), fill="black", width=3)
    draw.rectangle((64, 64, 192, 192), outline="black", width=4)
    return image


def _watercolor_like(size: tuple[int, int] = (256, 256)) -> Image.Image:
    y = np.linspace(0, 1, size[1], dtype=np.float32)[:, None]
    x = np.linspace(0, 1, size[0], dtype=np.float32)[None, :]
    wash = 145 + 25 * np.sin(x * 12.0) + 18 * np.cos(y * 15.0)
    arr = np.stack([wash + 18, wash, wash - 10], axis=2)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _categories(findings: list) -> set[str]:
    return {finding.category for finding in findings}


class TestImageEncodingAnalyzerContract(unittest.TestCase):
    def test_contract(self) -> None:
        analyzer = ImageEncodingAnalyzer()

        self.assertEqual(analyzer.name, "image_encoding_analyzer")
        self.assertEqual(analyzer.version, "v1")
        self.assertEqual(analyzer.analyzer_id, "image_encoding_analyzer/v1")
        self.assertEqual(
            analyzer.supported_categories,
            (
                "source_encoding.jpeg_compression",
                "source_encoding.jpeg_blocking",
                "source_encoding.jpeg_ringing",
                "source_encoding.chroma_artifact",
                "source_encoding.banding",
                "source_encoding.low_source_quality",
            ),
        )


class TestImageEncodingAnalyzerFindings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analyzer = ImageEncodingAnalyzer()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _analyze(self, path: Path) -> list:
        return self.analyzer.analyze(path, _ctx([path]))

    def test_high_quality_jpeg_presence_alone_does_not_flag(self) -> None:
        path = self.root / "high_quality.jpg"
        _gradient().save(path, quality=95)

        findings = self._analyze(path)

        self.assertEqual(findings, [])

    def test_low_quality_jpeg_flags_compression_context(self) -> None:
        path = self.root / "low_quality.jpg"
        _gradient().save(path, quality=8)

        findings = self._analyze(path)

        self.assertIn("source_encoding.jpeg_compression", _categories(findings))
        compression = [
            finding for finding in findings
            if finding.category == "source_encoding.jpeg_compression"
        ][0]
        self.assertIn("does not mean JPEG is unsuitable", compression.explanation)
        self.assertIn("does not", compression.recommendation)
        self.assertNotIn("training_risk", compression.evidence)
        self.assertLessEqual(compression.severity, Severity.MEDIUM)

    def test_8x8_blocking_flags(self) -> None:
        path = self.root / "blocking.jpg"
        _block_boundary_image().save(path, quality=95)

        findings = self._analyze(path)

        self.assertIn("source_encoding.jpeg_blocking", _categories(findings))
        blocking = [
            finding for finding in findings
            if finding.category == "source_encoding.jpeg_blocking"
        ][0]
        self.assertGreater(blocking.evidence["blocking_ratio"], 1.0)
        self.assertIn("review signal only", blocking.recommendation)

    def test_edge_ringing_and_mosquito_noise_flags_when_obvious(self) -> None:
        path = self.root / "ringing.jpg"
        _line_art().save(path, quality=8)

        findings = self._analyze(path)

        self.assertIn("source_encoding.jpeg_ringing", _categories(findings))
        ringing = [
            finding for finding in findings
            if finding.category == "source_encoding.jpeg_ringing"
        ][0]
        self.assertGreater(
            ringing.evidence["edge_ringing_score"]
            + ringing.evidence["mosquito_noise_score"],
            0,
        )
        self.assertIn("intentional hard edge illustration texture", ringing.explanation)

    def test_chroma_artifact_flags_when_practical(self) -> None:
        path = self.root / "chroma.jpg"
        _block_boundary_image().save(path, quality=95)

        findings = self._analyze(path)

        self.assertIn("source_encoding.chroma_artifact", _categories(findings))

    def test_banding_posterization_flags(self) -> None:
        path = self.root / "banding.png"
        _posterized_gradient().save(path)

        findings = self._analyze(path)

        self.assertIn("source_encoding.banding", _categories(findings))
        banding = [
            finding for finding in findings
            if finding.category == "source_encoding.banding"
        ][0]
        self.assertGreaterEqual(banding.evidence["banding_score"], 0.55)
        self.assertIn("deliberate posterized style", banding.recommendation)

    def test_png_natural_texture_does_not_flag(self) -> None:
        path = self.root / "natural_texture.png"
        Image.effect_noise((256, 256), 30).convert("RGB").save(path)

        findings = self._analyze(path)

        self.assertEqual(findings, [])

    def test_watercolor_pencil_like_texture_does_not_flag(self) -> None:
        path = self.root / "watercolor.png"
        _watercolor_like().save(path)

        findings = self._analyze(path)

        self.assertEqual(findings, [])

    def test_hard_edge_line_art_png_does_not_flag(self) -> None:
        path = self.root / "line_art.png"
        _line_art().save(path)

        findings = self._analyze(path)

        self.assertEqual(findings, [])

    def test_tiny_stock_like_jpeg_flags_low_source_quality(self) -> None:
        path = self.root / "tiny.jpg"
        _gradient((96, 96)).save(path, quality=35)

        findings = self._analyze(path)

        self.assertIn("source_encoding.low_source_quality", _categories(findings))
        low_source = [
            finding for finding in findings
            if finding.category == "source_encoding.low_source_quality"
        ][0]
        self.assertTrue(low_source.evidence["low_resolution_source"])
        self.assertIn("not an automatic exclusion", low_source.explanation)

    def test_output_is_deterministic_and_read_only(self) -> None:
        path = self.root / "low_quality.jpg"
        _gradient().save(path, quality=8)
        before = _sha256(path)

        first = [finding.to_dict() for finding in self._analyze(path)]
        second = [finding.to_dict() for finding in self._analyze(path)]

        self.assertEqual(first, second)
        self.assertEqual(_sha256(path), before)

    def test_measurement_evidence_is_transparent(self) -> None:
        path = self.root / "low_quality.jpg"
        _gradient().save(path, quality=8)

        measurement = measure_image_encoding(path)
        finding = self._analyze(path)[0]

        self.assertEqual(measurement.status, "analyzed")
        for key in [
            "image_format",
            "width",
            "height",
            "pixel_count",
            "file_size_bytes",
            "bytes_per_pixel",
            "quantization_table_available",
            "approximate_jpeg_quality",
            "chroma_subsampling",
            "block_boundary_score",
            "block_interior_score",
            "blocking_ratio",
            "edge_ringing_score",
            "mosquito_noise_score",
            "banding_score",
            "low_resolution_source",
        ]:
            self.assertIn(key, finding.evidence)

    def test_recommendation_summary_accepts_encoding_findings_without_schema_change(self) -> None:
        path = self.root / "low_quality.jpg"
        _gradient().save(path, quality=8)
        findings = self._analyze(path)

        summary = build_recommendation_summary(findings, _ctx([path])).to_dict()

        self.assertEqual(summary["schema"], "dataset-forge/recommendation-summary/v1")
        refs = summary["recommendations"][0]["finding_refs"]
        self.assertTrue(
            any(ref["category"].startswith("source_encoding.") for ref in refs)
        )
        self.assertIn("policy_semantics", summary)
        self.assertIn("finding_set_counts", summary)


if __name__ == "__main__":
    unittest.main()
