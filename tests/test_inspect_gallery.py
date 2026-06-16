"""Tests for src/dataset_forge/inspect_gallery.py and gallery integration.

Covers:
  - build_image_records: severity routing, z-score computation, error images
  - select_gallery_groups: group assignment, sorting, deduplication, padding
  - write_inspection_gallery: file written, valid PNG, expected size
  - run_inspect integration: gallery=False → gallery_path is None
  - run_inspect integration: gallery=True  → gallery_path set, file exists
  - CLI: --gallery flag wires through
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

import numpy as np
from PIL import Image

from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.finding import Finding, Severity
from dataset_forge.inspect import InspectResult, run_inspect
from dataset_forge.inspect_gallery import (
    GROUP_COLS,
    TILE_H,
    TILE_W,
    GROUP_GAP,
    OUTER_PAD,
    TITLE_EXTRA,
    HEADER_H,
    TILE_GAP,
    ImageRecord,
    build_image_records,
    select_gallery_groups,
    write_inspection_gallery,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ctx(n: int = 10, mean: float = 40.0, stddev: float = 10.0) -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
        image_paths=tuple(Path(f"img_{i:03d}.png") for i in range(n)),
        image_count=n,
        error_count=0,
        resolution_stats=ResolutionStats(
            mean_w=512.0, mean_h=512.0, stddev_w=0.0, stddev_h=0.0,
            min_w=512, min_h=512, max_w=512, max_h=512, sample_count=n,
        ),
        aspect_ratio_stats=AspectRatioStats(
            mean=1.0, stddev=0.0, min=1.0, max=1.0, sample_count=n,
        ),
        texture_distributions=TextureDistributions(
            mean=mean, stddev=stddev, p10=mean - stddev, p90=mean + stddev,
            sample_count=n,
        ),
        frequency_distributions=FrequencyDistributions(
            dominant_freq_mean=0.0, dominant_freq_stddev=0.0, sample_count=0,
        ),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _finding(image: str, severity: Severity = Severity.MEDIUM) -> Finding:
    return Finding(
        image_path=Path(image),
        analyzer="texture_analyzer/v1",
        category="texture.high_microtexture",
        severity=severity,
        confidence=0.65,
        false_positive_rate=0.15,
        benchmark_version="uncalibrated",
        evidence={"z_score": 2.0, "microtexture_density": 60.0, "calibrated": False},
        explanation="High microtexture.",
        recommendation="Review before applying cleanup.",
    )


def _scores(paths: list[str], micros: list[float]) -> dict[str, dict]:
    return {
        p: {
            "microtexture_density": m,
            "watercolor_smoothness": max(0.0, 80.0 - m),
            "highlight_speck": m * 0.1,
        }
        for p, m in zip(paths, micros)
    }


def _write_smooth(path: Path, n: int) -> list[Path]:
    written = []
    for i in range(n):
        p = path / f"smooth_{i:03d}.png"
        Image.fromarray(np.full((64, 64, 3), 128, dtype=np.uint8)).save(p)
        written.append(p)
    return written


def _write_noisy(path: Path, n: int) -> list[Path]:
    rng = np.random.default_rng(7)
    written = []
    for i in range(n):
        p = path / f"noisy_{i:03d}.png"
        Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(p)
        written.append(p)
    return written


# ---------------------------------------------------------------------------
# build_image_records
# ---------------------------------------------------------------------------

class TestBuildImageRecords(unittest.TestCase):

    def test_clean_image_gets_none_severity(self):
        scores = _scores(["img_000.png"], [30.0])
        records = build_image_records(scores, [], dist_mean=40.0, dist_stddev=10.0)
        self.assertEqual(records[0].severity, "NONE")

    def test_finding_image_gets_severity(self):
        paths = ["img_000.png"]
        scores = _scores(paths, [60.0])
        f = _finding("img_000.png", Severity.HIGH)
        records = build_image_records(
            scores, [f],
            dist_mean=40.0, dist_stddev=10.0,
        )
        self.assertEqual(records[0].severity, "HIGH")

    def test_highest_severity_wins_when_multiple_findings(self):
        paths = [str(Path("img_000.png").resolve())]
        scores = {paths[0]: {"microtexture_density": 60.0,
                              "watercolor_smoothness": 20.0,
                              "highlight_speck": 6.0}}
        f_med = Finding(
            image_path=Path(paths[0]),
            analyzer="texture_analyzer/v1",
            category="texture.high_microtexture",
            severity=Severity.MEDIUM,
            confidence=0.6, false_positive_rate=0.15,
            benchmark_version="uncalibrated",
            evidence={}, explanation="", recommendation="",
        )
        f_high = Finding(
            image_path=Path(paths[0]),
            analyzer="texture_analyzer/v1",
            category="texture.high_microtexture",
            severity=Severity.HIGH,
            confidence=0.6, false_positive_rate=0.15,
            benchmark_version="uncalibrated",
            evidence={}, explanation="", recommendation="",
        )
        records = build_image_records(scores, [f_med, f_high], 40.0, 10.0)
        self.assertEqual(records[0].severity, "HIGH")

    def test_z_score_computed_correctly(self):
        scores = _scores(["img.png"], [50.0])
        records = build_image_records(scores, [], dist_mean=40.0, dist_stddev=10.0)
        self.assertAlmostEqual(records[0].z, 1.0)

    def test_z_score_zero_stddev_does_not_crash(self):
        scores = _scores(["img.png"], [40.0])
        records = build_image_records(scores, [], dist_mean=40.0, dist_stddev=0.0)
        self.assertIsInstance(records[0].z, float)

    def test_error_image_gets_error_severity(self):
        scores = {"bad.png": {"error": "could not open"}}
        records = build_image_records(scores, [], 40.0, 10.0)
        self.assertEqual(records[0].severity, "ERROR")

    def test_error_image_has_zero_micro(self):
        scores = {"bad.png": {"error": "could not open"}}
        records = build_image_records(scores, [], 40.0, 10.0)
        self.assertEqual(records[0].micro, 0.0)

    def test_metrics_extracted(self):
        scores = _scores(["img.png"], [55.5])
        records = build_image_records(scores, [], 40.0, 10.0)
        self.assertAlmostEqual(records[0].micro, 55.5)
        self.assertAlmostEqual(records[0].smooth, 24.5, places=1)

    def test_returns_one_record_per_image(self):
        paths = ["a.png", "b.png", "c.png"]
        scores = _scores(paths, [10.0, 20.0, 30.0])
        records = build_image_records(scores, [], 20.0, 5.0)
        self.assertEqual(len(records), 3)


# ---------------------------------------------------------------------------
# select_gallery_groups
# ---------------------------------------------------------------------------

class TestSelectGalleryGroups(unittest.TestCase):

    def _make_records(self, specs: list[tuple[str, str, float]]) -> list[ImageRecord]:
        """specs: [(name, severity, micro), ...]  — z computed as micro/10."""
        return [
            ImageRecord(
                path=Path(name), severity=sev,
                micro=micro, z=micro / 10.0,
                smooth=80.0 - micro, speck=micro * 0.1,
            )
            for name, sev, micro in specs
        ]

    def test_high_findings_in_group_a(self):
        records = self._make_records([
            ("h1.png", "HIGH", 90.0),
            ("h2.png", "HIGH", 80.0),
            ("c1.png", "NONE", 20.0),
        ])
        groups = select_gallery_groups(records)
        severities = [r.severity for r in groups["A"] if r is not None]
        self.assertTrue(all(s == "HIGH" for s in severities))

    def test_medium_findings_in_group_b(self):
        records = self._make_records([
            ("m1.png", "MEDIUM", 60.0),
            ("m2.png", "MEDIUM", 55.0),
            ("c1.png", "NONE", 20.0),
        ])
        groups = select_gallery_groups(records)
        severities = [r.severity for r in groups["B"] if r is not None]
        self.assertTrue(all(s == "MEDIUM" for s in severities))

    def test_group_a_sorted_descending_by_z(self):
        records = self._make_records([
            ("h1.png", "HIGH", 70.0),
            ("h2.png", "HIGH", 90.0),
            ("h3.png", "HIGH", 80.0),
        ])
        groups = select_gallery_groups(records)
        zs = [r.z for r in groups["A"] if r is not None]
        self.assertEqual(zs, sorted(zs, reverse=True))

    def test_group_b_sorted_descending_by_z(self):
        records = self._make_records([
            ("m1.png", "MEDIUM", 50.0),
            ("m2.png", "MEDIUM", 70.0),
            ("m3.png", "MEDIUM", 60.0),
        ])
        groups = select_gallery_groups(records)
        zs = [r.z for r in groups["B"] if r is not None]
        self.assertEqual(zs, sorted(zs, reverse=True))

    def test_clean_images_in_group_d_lowest_z_first(self):
        records = self._make_records([
            ("c1.png", "NONE", 30.0),
            ("c2.png", "NONE", 10.0),
            ("c3.png", "NONE", 20.0),
        ])
        groups = select_gallery_groups(records)
        zs = [r.z for r in groups["D"] if r is not None]
        self.assertEqual(zs, sorted(zs))

    def test_each_group_has_exactly_group_cols_slots(self):
        records = self._make_records([("img.png", "NONE", 30.0)])
        groups = select_gallery_groups(records)
        for gid in ("A", "B", "C", "D"):
            self.assertEqual(len(groups[gid]), GROUP_COLS)

    def test_empty_slots_padded_with_none(self):
        records = self._make_records([("img.png", "HIGH", 90.0)])
        groups = select_gallery_groups(records)
        none_count = sum(1 for r in groups["A"] if r is None)
        self.assertEqual(none_count, GROUP_COLS - 1)

    def test_group_c_excludes_images_already_in_a_and_b(self):
        # 5 HIGH + 5 MEDIUM + 5 clean; boundary should only pick from clean
        specs = (
            [(f"h{i}.png", "HIGH", 90.0 - i) for i in range(5)]
            + [(f"m{i}.png", "MEDIUM", 60.0 - i) for i in range(5)]
            + [(f"c{i}.png", "NONE", 20.0 - i) for i in range(5)]
        )
        records = self._make_records(specs)
        groups = select_gallery_groups(records)
        a_b_paths = {r.path for g in ("A", "B") for r in groups[g] if r}
        c_paths = {r.path for r in groups["C"] if r}
        self.assertTrue(c_paths.isdisjoint(a_b_paths))

    def test_group_c_prefers_images_nearest_z_1(self):
        # Provide images at various z-scores; boundary should pick those near 1.0
        specs = [
            ("far_low.png", "NONE", 0.0),   # z far below 1.0
            ("near.png", "NONE", 11.0),      # z≈1.1, nearest 1.0 (z = micro/10)
            ("far_high.png", "NONE", 50.0),  # z far above 1.0
        ]
        records = self._make_records(specs)
        groups = select_gallery_groups(records)
        c_paths = [r.path.name for r in groups["C"] if r]
        self.assertIn("near.png", c_paths)

    def test_empty_input_returns_all_none(self):
        groups = select_gallery_groups([])
        for gid in ("A", "B", "C", "D"):
            self.assertTrue(all(r is None for r in groups[gid]))

    def test_at_most_group_cols_per_group(self):
        # 10 HIGH images — group A should cap at GROUP_COLS
        records = self._make_records(
            [(f"h{i}.png", "HIGH", 90.0 - i) for i in range(10)]
        )
        groups = select_gallery_groups(records)
        non_none = [r for r in groups["A"] if r is not None]
        self.assertEqual(len(non_none), GROUP_COLS)


# ---------------------------------------------------------------------------
# write_inspection_gallery
# ---------------------------------------------------------------------------

class TestWriteInspectionGallery(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp.name)
        self.ctx = _ctx(n=6, mean=40.0, stddev=10.0)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, image_paths: list[Path], scores: dict, findings=None) -> Path:
        out = self.out_dir / "inspection_gallery.png"
        return write_inspection_gallery(
            findings or [], self.ctx, out, scores,
        )

    def test_returns_path(self):
        scores = _scores(["a.png", "b.png"], [20.0, 60.0])
        result = self._run([], scores)
        self.assertIsInstance(result, Path)

    def test_file_written(self):
        scores = _scores(["a.png", "b.png"], [20.0, 60.0])
        out = self._run([], scores)
        self.assertTrue(out.exists())

    def test_output_is_valid_png(self):
        scores = _scores(["a.png"], [30.0])
        out = self._run([], scores)
        with Image.open(out) as img:
            self.assertEqual(img.format, "PNG")

    def test_output_is_rgb(self):
        scores = _scores(["a.png"], [30.0])
        out = self._run([], scores)
        with Image.open(out) as img:
            self.assertEqual(img.mode, "RGB")

    def test_width_matches_layout(self):
        group_w = GROUP_COLS * TILE_W + (GROUP_COLS - 1) * TILE_GAP
        expected_w = OUTER_PAD * 2 + 4 * group_w + 3 * GROUP_GAP
        scores = _scores(["a.png"], [30.0])
        out = self._run([], scores)
        with Image.open(out) as img:
            self.assertEqual(img.width, expected_w)

    def test_height_matches_layout(self):
        expected_h = (
            OUTER_PAD * 2
            + TITLE_EXTRA
            + 4 * (HEADER_H + TILE_H + TILE_GAP * 2 + 8)
        )
        scores = _scores(["a.png"], [30.0])
        out = self._run([], scores)
        with Image.open(out) as img:
            self.assertEqual(img.height, expected_h)

    def test_empty_scores_does_not_crash(self):
        out = self._run([], {})
        self.assertTrue(out.exists())

    def test_error_scores_do_not_crash(self):
        scores = {"bad.png": {"error": "file not found"}}
        out = self._run([], scores)
        self.assertTrue(out.exists())

    def test_missing_image_files_do_not_crash(self):
        # Scores reference paths that don't exist on disk — should load-error gracefully
        scores = _scores(["/nonexistent/img.png"], [50.0])
        out = self._run([], scores)
        self.assertTrue(out.exists())

    def test_parent_dir_created_if_missing(self):
        nested = self.out_dir / "deep" / "nested" / "gallery.png"
        write_inspection_gallery([], self.ctx, nested, {})
        self.assertTrue(nested.exists())

    def test_real_image_thumbnailed_into_canvas(self):
        """Gallery produced from a real synthetic image should differ from blank."""
        tmp2 = tempfile.TemporaryDirectory()
        try:
            img_path = Path(tmp2.name) / "real.png"
            arr = np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8)
            Image.fromarray(arr).save(img_path)
            scores = {str(img_path): {
                "microtexture_density": 85.0,
                "watercolor_smoothness": 10.0,
                "highlight_speck": 8.0,
            }}
            out = self.out_dir / "real_gallery.png"
            write_inspection_gallery([], self.ctx, out, scores)
            self.assertTrue(out.exists())
        finally:
            tmp2.cleanup()


# ---------------------------------------------------------------------------
# run_inspect integration
# ---------------------------------------------------------------------------

class TestRunInspectGalleryIntegration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        _write_smooth(self.dataset, n=5)
        _write_noisy(self.dataset, n=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gallery_false_returns_none_path(self):
        result = run_inspect(self.dataset, self.output, gallery=False)
        self.assertIsNone(result.gallery_path)

    def test_gallery_false_does_not_write_file(self):
        run_inspect(self.dataset, self.output, gallery=False)
        self.assertFalse((self.output / "inspection_gallery.png").exists())

    def test_gallery_true_returns_path(self):
        result = run_inspect(self.dataset, self.output, gallery=True)
        self.assertIsNotNone(result.gallery_path)

    def test_gallery_true_writes_file(self):
        result = run_inspect(self.dataset, self.output, gallery=True)
        self.assertTrue(result.gallery_path.exists())

    def test_gallery_path_is_in_output_dir(self):
        result = run_inspect(self.dataset, self.output, gallery=True)
        self.assertEqual(result.gallery_path.parent, self.output.resolve())

    def test_gallery_filename_is_inspection_gallery(self):
        result = run_inspect(self.dataset, self.output, gallery=True)
        self.assertEqual(result.gallery_path.name, "inspection_gallery.png")

    def test_gallery_is_valid_png(self):
        result = run_inspect(self.dataset, self.output, gallery=True)
        with Image.open(result.gallery_path) as img:
            self.assertEqual(img.format, "PNG")

    def test_inspect_result_gallery_path_none_by_default(self):
        result = run_inspect(self.dataset, self.output)
        self.assertIsNone(result.gallery_path)

    def test_inspect_result_still_frozen(self):
        result = run_inspect(self.dataset, self.output, gallery=True)
        with self.assertRaises(Exception):
            result.gallery_path = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestCLIGalleryFlag(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "ds"
        self.output = Path(self.tmp.name) / "out"
        self.dataset.mkdir()
        _write_smooth(self.dataset, n=3)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_cli(self, *extra_args: str) -> int:
        from dataset_forge.cli import main
        argv = ["inspect", str(self.dataset), "--output", str(self.output)] + list(extra_args)
        return main(argv)

    def test_no_gallery_flag_exits_zero(self):
        self.assertEqual(self._run_cli(), 0)

    def test_no_gallery_flag_no_png(self):
        self._run_cli()
        self.assertFalse((self.output / "inspection_gallery.png").exists())

    def test_gallery_flag_exits_zero(self):
        self.assertEqual(self._run_cli("--gallery"), 0)

    def test_gallery_flag_writes_png(self):
        self._run_cli("--gallery")
        self.assertTrue((self.output / "inspection_gallery.png").exists())

    def test_gallery_flag_prints_path(self):
        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            self._run_cli("--gallery")
        finally:
            sys.stdout = old_stdout
        self.assertIn("inspection_gallery.png", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
