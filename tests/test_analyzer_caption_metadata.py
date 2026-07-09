"""Tests for the advisory Caption / Metadata Analyzer."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from dataset_forge.analyzers.caption_metadata import CaptionMetadataAnalyzer
from dataset_forge.context import DatasetContext
from dataset_forge.recommendation_summary import build_recommendation_summary


def _ctx(paths: list[Path]) -> DatasetContext:
    return DatasetContext.empty(image_paths=paths)


def _write_image(path: Path) -> None:
    Image.new("RGB", (24, 24), (120, 130, 140)).save(path)


def _write_caption(image_path: Path, text: str) -> Path:
    caption = image_path.with_suffix(".txt")
    caption.write_text(text, encoding="utf-8")
    return caption


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _categories(findings: list) -> set[str]:
    return {finding.category for finding in findings}


class TestCaptionMetadataAnalyzerContract(unittest.TestCase):
    def test_contract(self) -> None:
        analyzer = CaptionMetadataAnalyzer()

        self.assertEqual(analyzer.name, "caption_metadata_analyzer")
        self.assertEqual(analyzer.version, "v1")
        self.assertEqual(analyzer.analyzer_id, "caption_metadata_analyzer/v1")
        self.assertEqual(
            analyzer.supported_categories,
            (
                "caption.missing",
                "caption.empty",
                "caption.duplicate",
                "caption.short",
                "caption.long",
                "caption.token_imbalance",
            ),
        )


class TestCaptionMetadataAnalyzerFindings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analyzer = CaptionMetadataAnalyzer()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _image(self, name: str) -> Path:
        path = self.root / name
        _write_image(path)
        return path

    def _analyze(self, paths: list[Path]) -> dict[str, list]:
        context = _ctx(paths)
        return {
            path.name: self.analyzer.analyze(path, context)
            for path in paths
        }

    def test_missing_caption_sidecar_flags(self) -> None:
        image = self._image("missing.png")

        findings = self._analyze([image])["missing.png"]

        self.assertEqual(_categories(findings), {"caption.missing"})
        finding = findings[0]
        self.assertIn("No caption sidecar", finding.explanation)
        self.assertIn("does not generate, rewrite, or suggest captions", finding.recommendation)
        self.assertFalse(finding.evidence["caption_exists"])

    def test_empty_caption_sidecar_flags(self) -> None:
        image = self._image("empty.jpg")
        _write_caption(image, " \n\t ")

        findings = self._analyze([image])["empty.jpg"]

        self.assertEqual(_categories(findings), {"caption.empty"})
        self.assertTrue(findings[0].evidence["caption_empty"])

    def test_duplicate_captions_flag_exact_matches(self) -> None:
        first = self._image("first.png")
        second = self._image("second.png")
        third = self._image("third.png")
        _write_caption(first, "red fox portrait")
        _write_caption(second, "red fox portrait")
        _write_caption(third, "blue wolf portrait")

        findings = self._analyze([third, second, first])

        self.assertIn("caption.duplicate", _categories(findings["first.png"]))
        self.assertIn("caption.duplicate", _categories(findings["second.png"]))
        self.assertNotIn("caption.duplicate", _categories(findings["third.png"]))
        duplicate = [
            finding for finding in findings["first.png"]
            if finding.category == "caption.duplicate"
        ][0]
        self.assertEqual(duplicate.evidence["duplicate_count"], 2)
        self.assertEqual(len(duplicate.evidence["matched_image_paths"]), 2)
        self.assertIn("not semantic similarity", duplicate.explanation)

    def test_unique_captions_do_not_flag_duplicate(self) -> None:
        first = self._image("first.png")
        second = self._image("second.png")
        _write_caption(first, "red fox portrait")
        _write_caption(second, "blue wolf portrait")

        findings = self._analyze([first, second])

        self.assertNotIn("caption.duplicate", _categories(findings["first.png"]))
        self.assertNotIn("caption.duplicate", _categories(findings["second.png"]))

    def test_short_caption_flags(self) -> None:
        image = self._image("short.png")
        _write_caption(image, "fox")

        findings = self._analyze([image])["short.png"]

        self.assertIn("caption.short", _categories(findings))
        short = [finding for finding in findings if finding.category == "caption.short"][0]
        self.assertEqual(short.evidence["caption_token_count"], 1)
        self.assertIn("does not decide whether the caption is good", short.recommendation)

    def test_long_caption_flags(self) -> None:
        image = self._image("long.png")
        _write_caption(image, " ".join(f"token{index}" for index in range(80)))

        findings = self._analyze([image])["long.png"]

        self.assertIn("caption.long", _categories(findings))
        long = [finding for finding in findings if finding.category == "caption.long"][0]
        self.assertEqual(long.evidence["caption_token_count"], 80)
        self.assertIn("does not score prompt quality", long.recommendation)

    def test_token_imbalance_flags_repeated_boilerplate(self) -> None:
        paths = [self._image(f"img_{index}.png") for index in range(5)]
        for index, path in enumerate(paths):
            _write_caption(path, f"masterpiece fox portrait {index}")

        findings = self._analyze(paths)

        for path in paths:
            self.assertIn("caption.token_imbalance", _categories(findings[path.name]))
        imbalance = [
            finding for finding in findings["img_0.png"]
            if finding.category == "caption.token_imbalance"
        ][0]
        self.assertEqual(imbalance.evidence["term"], "masterpiece")
        self.assertEqual(imbalance.evidence["caption_frequency_percentage"], 100.0)
        self.assertIn("does not optimize prompts", imbalance.recommendation)

    def test_deterministic_output_and_read_only_behavior(self) -> None:
        image = self._image("stable.png")
        caption = _write_caption(image, "masterpiece fox")
        before = {_sha256(image), _sha256(caption)}

        first = [finding.to_dict() for finding in self._analyze([image])["stable.png"]]
        second = [finding.to_dict() for finding in self._analyze([image])["stable.png"]]

        self.assertEqual(first, second)
        self.assertEqual({_sha256(image), _sha256(caption)}, before)

    def test_recommendation_summary_accepts_caption_findings_without_schema_change(self) -> None:
        image = self._image("missing.png")
        findings = self._analyze([image])["missing.png"]

        summary = build_recommendation_summary(findings, _ctx([image])).to_dict()

        self.assertEqual(summary["schema"], "dataset-forge/recommendation-summary/v1")
        refs = summary["recommendations"][0]["finding_refs"]
        self.assertTrue(any(ref["category"].startswith("caption.") for ref in refs))
        self.assertIn("policy_semantics", summary)
        self.assertIn("finding_set_counts", summary)


if __name__ == "__main__":
    unittest.main()
