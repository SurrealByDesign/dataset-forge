"""Tests for conservative perceptual near-duplicate detection analyzer."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from dataset_forge.analyzers.perceptual_duplicates import (
    PerceptualDuplicateAnalyzer,
    _perceptual_groups,
)
from dataset_forge.context import DatasetContext
from dataset_forge.recommendation_summary import build_recommendation_summary


def _ctx(paths: list[Path]) -> DatasetContext:
    _perceptual_groups.cache_clear()
    return DatasetContext.empty(image_paths=paths)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _base_image(size: tuple[int, int] = (96, 96)) -> Image.Image:
    width, height = size
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    red = 40 + 130 * x + 30 * np.sin(y * 8)
    green = 60 + 100 * y + 20 * np.cos(x * 10)
    blue = 90 + 80 * (x * y) + 25 * np.sin((x + y) * 6)
    arr = np.stack([
        np.broadcast_to(red, (height, width)),
        np.broadcast_to(green, (height, width)),
        np.broadcast_to(blue, (height, width)),
    ], axis=2)
    arr[28:68, 34:74, 0] += 45
    arr[20:45, 14:38, 2] += 55
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _different_same_subject(size: tuple[int, int] = (96, 96)) -> Image.Image:
    image = Image.new("RGB", size, (235, 230, 220))
    arr = np.asarray(image, dtype=np.uint8).copy()
    yy, xx = np.ogrid[:size[1], :size[0]]
    mask = (xx - 48) ** 2 + (yy - 48) ** 2 <= 30 ** 2
    arr[mask] = (95, 130, 180)
    arr[35:62, 18:78] = (160, 80, 70)
    return Image.fromarray(arr, "RGB")


def _write(path: Path, image: Image.Image, **save_kwargs) -> None:
    image.save(path, **save_kwargs)
    path.with_suffix(".txt").write_text(
        f"neutral caption for {path.stem}",
        encoding="utf-8",
    )


def _findings(paths: list[Path]) -> dict[str, list]:
    analyzer = PerceptualDuplicateAnalyzer()
    context = _ctx(paths)
    return {
        path.name: analyzer.analyze(path, context)
        for path in paths
    }


def _group_findings(findings: dict[str, list]) -> list:
    return [
        finding
        for rows in findings.values()
        for finding in rows
        if finding.category == "duplicate.perceptual"
    ]


class TestPerceptualDuplicateAnalyzerContract(unittest.TestCase):
    def test_contract(self) -> None:
        analyzer = PerceptualDuplicateAnalyzer()

        self.assertEqual(analyzer.name, "perceptual_duplicate_analyzer")
        self.assertEqual(analyzer.version, "v1")
        self.assertEqual(analyzer.analyzer_id, "perceptual_duplicate_analyzer/v1")
        self.assertEqual(analyzer.supported_categories, ("duplicate.perceptual",))


class TestPerceptualDuplicateAnalyzerFindings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        _perceptual_groups.cache_clear()
        self.tmp.cleanup()

    def test_identical_image_negative_exact_analyzer_owns_it(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        image = _base_image()
        _write(first, image)
        _write(second, image)

        findings = _findings([first, second])

        self.assertEqual(_group_findings(findings), [])

    def test_pixel_identical_with_metadata_difference_negative(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        image = _base_image()
        _write(first, image)
        image.save(second, pnginfo=None)
        second.with_suffix(".txt").write_text("neutral caption second", encoding="utf-8")

        findings = _findings([first, second])

        self.assertEqual(_group_findings(findings), [])

    def test_small_jpeg_recompression_positive(self) -> None:
        source = self.root / "source.png"
        recompressed = self.root / "recompressed.jpg"
        image = _base_image()
        _write(source, image)
        _write(recompressed, image, quality=90)

        findings = _findings([source, recompressed])
        groups = _group_findings(findings)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].evidence["group_size"], 2)
        self.assertIn("average_hash_16x16", groups[0].evidence["matching_algorithms"])

    def test_tiny_resize_positive(self) -> None:
        source = self.root / "source.png"
        resized = self.root / "resized.png"
        image = _base_image()
        _write(source, image)
        _write(resized, image.resize((94, 94), Image.Resampling.BICUBIC))

        groups = _group_findings(_findings([source, resized]))

        self.assertEqual(len(groups), 1)

    def test_slight_crop_positive(self) -> None:
        source = self.root / "source.png"
        cropped = self.root / "cropped.png"
        image = _base_image()
        _write(source, image)
        _write(
            cropped,
            ImageOps.fit(
                image.crop((2, 2, image.width - 2, image.height - 2)),
                image.size,
                method=Image.Resampling.BICUBIC,
            ),
        )

        groups = _group_findings(_findings([source, cropped]))

        self.assertEqual(len(groups), 1)

    def test_tiny_color_shift_positive(self) -> None:
        source = self.root / "source.png"
        shifted = self.root / "shifted.png"
        image = _base_image()
        _write(source, image)
        _write(shifted, ImageEnhance.Color(image).enhance(1.03))

        groups = _group_findings(_findings([source, shifted]))

        self.assertEqual(len(groups), 1)

    def test_unrelated_images_negative(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        _write(first, _base_image())
        _write(second, ImageOps.mirror(_different_same_subject()))

        groups = _group_findings(_findings([first, second]))

        self.assertEqual(groups, [])

    def test_low_information_smooth_variants_negative(self) -> None:
        first = self.root / "smooth_096.png"
        second = self.root / "smooth_097.png"
        _write(first, Image.new("RGB", (96, 96), (96, 96, 96)))
        _write(second, Image.new("RGB", (96, 96), (97, 97, 97)))

        groups = _group_findings(_findings([first, second]))

        self.assertEqual(groups, [])

    def test_different_artwork_same_subject_negative(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        _write(first, _base_image())
        _write(second, _different_same_subject())

        groups = _group_findings(_findings([first, second]))

        self.assertEqual(groups, [])

    def test_deterministic_output_and_read_only_behavior(self) -> None:
        source = self.root / "source.png"
        recompressed = self.root / "recompressed.jpg"
        image = _base_image()
        _write(source, image)
        _write(recompressed, image, quality=90)
        before = {
            source: _sha256(source),
            recompressed: _sha256(recompressed),
        }

        first = [finding.to_dict() for rows in _findings([source, recompressed]).values() for finding in rows]
        second = [finding.to_dict() for rows in _findings([source, recompressed]).values() for finding in rows]

        self.assertEqual(first, second)
        self.assertEqual({path: _sha256(path) for path in before}, before)

    def test_grouping_and_representative_evidence(self) -> None:
        source = self.root / "a_source.png"
        resized = self.root / "b_resized.png"
        shifted = self.root / "c_shifted.png"
        image = _base_image()
        _write(source, image)
        _write(resized, image.resize((94, 94), Image.Resampling.BICUBIC))
        _write(shifted, ImageEnhance.Color(image).enhance(1.03))

        group = _group_findings(_findings([shifted, resized, source]))[0]

        self.assertEqual(group.evidence["group_id"], "perceptual-duplicate-group-0001")
        self.assertEqual(group.evidence["group_size"], 3)
        self.assertIn(group.evidence["representative_image"], group.evidence["member_paths"])
        self.assertEqual(
            group.evidence["ranking_evidence"]["suggested_representative"]["path"],
            group.evidence["representative_image"],
        )
        self.assertGreaterEqual(len(group.evidence["pair_verification"]), 2)
        self.assertIn("does not delete, move, copy", group.recommendation)

    def test_recommendation_summary_accepts_perceptual_duplicate_without_schema_change(self) -> None:
        source = self.root / "source.png"
        recompressed = self.root / "recompressed.jpg"
        image = _base_image()
        _write(source, image)
        _write(recompressed, image, quality=90)
        findings = [
            finding
            for rows in _findings([source, recompressed]).values()
            for finding in rows
        ]

        summary = build_recommendation_summary(findings, _ctx([source, recompressed])).to_dict()

        self.assertEqual(summary["schema"], "dataset-forge/recommendation-summary/v1")
        refs = summary["recommendations"][0]["finding_refs"]
        self.assertTrue(any(ref["category"] == "duplicate.perceptual" for ref in refs))
        self.assertIn("policy_semantics", summary)
        self.assertIn("finding_set_counts", summary)


if __name__ == "__main__":
    unittest.main()
