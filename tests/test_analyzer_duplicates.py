"""Tests for exact duplicate detection analyzer."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin

from dataset_forge.analyzers.duplicates import (
    DuplicateDetectionAnalyzer,
    _DuplicateRecord,
    _duplicate_groups,
    _representative_sort_key,
)
from dataset_forge.context import DatasetContext


def _ctx(paths: list[Path]) -> DatasetContext:
    _duplicate_groups.cache_clear()
    return DatasetContext.empty(image_paths=paths)


def _pattern_image(size: tuple[int, int] = (32, 32)) -> Image.Image:
    image = Image.new("RGB", size, (20, 40, 80))
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = ((x * 7) % 255, (y * 11) % 255, ((x + y) * 5) % 255)
    return image


def _write_png(path: Path, *, metadata: str = "") -> None:
    pnginfo = PngImagePlugin.PngInfo()
    if metadata:
        pnginfo.add_text("note", metadata)
    _pattern_image().save(path, pnginfo=pnginfo)


def _findings(paths: list[Path]) -> dict[str, list]:
    analyzer = DuplicateDetectionAnalyzer()
    context = _ctx(paths)
    return {
        path.name: analyzer.analyze(path, context)
        for path in paths
    }


class TestDuplicateDetectionAnalyzerContract(unittest.TestCase):
    def test_contract(self) -> None:
        analyzer = DuplicateDetectionAnalyzer()

        self.assertEqual(analyzer.name, "duplicate_detection_analyzer")
        self.assertEqual(analyzer.version, "v1")
        self.assertEqual(analyzer.analyzer_id, "duplicate_detection_analyzer/v1")
        self.assertEqual(analyzer.supported_categories, ("dataset.duplicate.exact",))


class TestDuplicateDetectionAnalyzerFindings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        _duplicate_groups.cache_clear()
        self.tmp.cleanup()

    def test_byte_identical_duplicate_files_emit_one_finding_per_image(self) -> None:
        first = self.root / "a.png"
        second = self.root / "b.png"
        _write_png(first)
        shutil.copyfile(first, second)

        findings = _findings([first, second])

        self.assertEqual(len(findings["a.png"]), 1)
        self.assertEqual(len(findings["b.png"]), 1)
        evidence = findings["a.png"][0].evidence
        self.assertEqual(evidence["duplicate_kind"], "file_sha256")
        self.assertEqual(evidence["group_id"], "duplicate-group-0001")
        self.assertEqual(evidence["group_size"], 2)

    def test_same_decoded_pixels_with_different_png_metadata_are_duplicates(self) -> None:
        first = self.root / "a.png"
        second = self.root / "b.png"
        _write_png(first, metadata="first")
        _write_png(second, metadata="second")

        findings = _findings([first, second])

        evidence = findings["a.png"][0].evidence
        self.assertEqual(evidence["duplicate_kind"], "pixel_sha256")
        self.assertEqual(evidence["group_size"], 2)
        self.assertIn(first.resolve().as_posix(), evidence["duplicate_member_paths"])
        self.assertIn(second.resolve().as_posix(), evidence["duplicate_member_paths"])

    def test_png_and_jpeg_same_source_do_not_count_when_pixels_differ(self) -> None:
        png = self.root / "a.png"
        jpeg = self.root / "a.jpg"
        image = _pattern_image()
        image.save(png)
        image.save(jpeg, quality=70)

        findings = _findings([png, jpeg])

        self.assertEqual(findings["a.png"], [])
        self.assertEqual(findings["a.jpg"], [])

    def test_resized_image_does_not_count_as_duplicate(self) -> None:
        first = self.root / "a.png"
        resized = self.root / "resized.png"
        image = _pattern_image()
        image.save(first)
        image.resize((16, 16)).save(resized)

        findings = _findings([first, resized])

        self.assertEqual(findings["a.png"], [])
        self.assertEqual(findings["resized.png"], [])

    def test_cropped_image_does_not_count_as_duplicate(self) -> None:
        first = self.root / "a.png"
        cropped = self.root / "cropped.png"
        image = _pattern_image()
        image.save(first)
        image.crop((0, 0, 24, 24)).save(cropped)

        findings = _findings([first, cropped])

        self.assertEqual(findings["a.png"], [])
        self.assertEqual(findings["cropped.png"], [])

    def test_visually_similar_but_distinct_image_does_not_count(self) -> None:
        first = self.root / "a.png"
        second = self.root / "b.png"
        image = _pattern_image()
        image.save(first)
        changed = image.copy()
        changed.putpixel((0, 0), (255, 255, 255))
        changed.save(second)

        findings = _findings([first, second])

        self.assertEqual(findings["a.png"], [])
        self.assertEqual(findings["b.png"], [])

    def test_suggested_representative_role_and_wording_are_advisory(self) -> None:
        first = self.root / "a.png"
        second = self.root / "b.png"
        _write_png(first, metadata="first")
        _write_png(second, metadata="second")

        findings = _findings([first, second])

        roles = {
            item[0].evidence["current_image_role"]
            for item in findings.values()
            if item
        }
        self.assertEqual(roles, {"suggested_representative", "duplicate_candidate"})
        finding = findings["a.png"][0]
        self.assertIn("Suggested representative is advisory", finding.explanation)
        self.assertIn("does not delete, move, or exclude files", finding.explanation)
        self.assertIn("No files were moved", finding.recommendation)

    def test_group_ids_are_deterministic(self) -> None:
        a = self.root / "a.png"
        b = self.root / "b.png"
        c = self.root / "c.png"
        d = self.root / "d.png"
        _write_png(a, metadata="a")
        _write_png(b, metadata="b")
        Image.new("RGB", (10, 10), (1, 2, 3)).save(c)
        shutil.copyfile(c, d)

        findings = _findings([d, b, c, a])

        group_ids = sorted(
            {
                item[0].evidence["group_id"]
                for item in findings.values()
                if item
            }
        )
        self.assertEqual(group_ids, ["duplicate-group-0001", "duplicate-group-0002"])


class TestDuplicateRepresentativeRanking(unittest.TestCase):
    def _record(self, path: str, **overrides) -> _DuplicateRecord:
        defaults = {
            "file_sha256": path,
            "pixel_sha256": "pixels",
            "width": 32,
            "height": 32,
            "mode": "RGB",
            "image_format": "PNG",
            "file_size": 1024,
        }
        defaults.update(overrides)
        return _DuplicateRecord(path=Path(path), **defaults)

    def test_highest_pixel_count_wins(self) -> None:
        small = self._record("b.png", width=16, height=16)
        large = self._record("a.png", width=32, height=32)

        self.assertLess(_representative_sort_key(large), _representative_sort_key(small))

    def test_lossless_non_jpeg_preferred_when_dimensions_equal(self) -> None:
        png = self._record("b.png", image_format="PNG")
        jpeg = self._record("a.jpg", image_format="JPEG")

        self.assertLess(_representative_sort_key(png), _representative_sort_key(jpeg))

    def test_path_tie_break_is_stable(self) -> None:
        first = self._record("a.png")
        second = self._record("b.png")

        self.assertLess(_representative_sort_key(first), _representative_sort_key(second))


if __name__ == "__main__":
    unittest.main()
