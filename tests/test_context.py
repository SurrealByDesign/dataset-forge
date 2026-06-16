"""Tests for DatasetContext and its sub-dataclasses."""

import unittest
from pathlib import Path

from dataset_forge.context import (
    CONTEXT_SCHEMA,
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _res(**kw) -> ResolutionStats:
    defaults = dict(mean_w=512.0, mean_h=768.0, stddev_w=0.0, stddev_h=0.0,
                    min_w=512, min_h=768, max_w=512, max_h=768, sample_count=10)
    return ResolutionStats(**{**defaults, **kw})


def _ar(**kw) -> AspectRatioStats:
    defaults = dict(mean=0.667, stddev=0.02, min=0.5, max=1.0, sample_count=10)
    return AspectRatioStats(**{**defaults, **kw})


def _tex(**kw) -> TextureDistributions:
    defaults = dict(mean=39.9, stddev=11.6, p10=24.1, p90=55.2, sample_count=10)
    return TextureDistributions(**{**defaults, **kw})


def _freq(**kw) -> FrequencyDistributions:
    defaults = dict(dominant_freq_mean=0.12, dominant_freq_stddev=0.04, sample_count=10)
    return FrequencyDistributions(**{**defaults, **kw})


def _context(**kw) -> DatasetContext:
    paths = [Path(f"img_{i:03d}.png") for i in range(5)]
    defaults = dict(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture": "v1", "frequency": "v1"},
        image_paths=tuple(paths),
        image_count=5,
        error_count=0,
        resolution_stats=_res(),
        aspect_ratio_stats=_ar(),
        texture_distributions=_tex(),
        frequency_distributions=_freq(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )
    return DatasetContext(**{**defaults, **kw})


# ---------------------------------------------------------------------------
# ResolutionStats
# ---------------------------------------------------------------------------

class TestResolutionStats(unittest.TestCase):
    def test_constructs(self):
        r = _res()
        self.assertEqual(r.mean_w, 512.0)

    def test_frozen(self):
        r = _res()
        with self.assertRaises(Exception):
            r.mean_w = 0.0  # type: ignore[misc]

    def test_negative_sample_count_rejected(self):
        with self.assertRaises(ValueError):
            _res(sample_count=-1)

    def test_to_dict_keys(self):
        d = _res().to_dict()
        for key in ("mean_w", "mean_h", "stddev_w", "stddev_h", "min_w", "min_h",
                    "max_w", "max_h", "sample_count"):
            self.assertIn(key, d)

    def test_empty_factory(self):
        r = ResolutionStats.empty()
        self.assertEqual(r.sample_count, 0)


# ---------------------------------------------------------------------------
# AspectRatioStats
# ---------------------------------------------------------------------------

class TestAspectRatioStats(unittest.TestCase):
    def test_constructs(self):
        a = _ar()
        self.assertAlmostEqual(a.mean, 0.667)

    def test_frozen(self):
        a = _ar()
        with self.assertRaises(Exception):
            a.mean = 1.0  # type: ignore[misc]

    def test_negative_sample_count_rejected(self):
        with self.assertRaises(ValueError):
            _ar(sample_count=-1)

    def test_empty_factory(self):
        a = AspectRatioStats.empty()
        self.assertEqual(a.sample_count, 0)


# ---------------------------------------------------------------------------
# TextureDistributions
# ---------------------------------------------------------------------------

class TestTextureDistributions(unittest.TestCase):
    def test_constructs(self):
        t = _tex()
        self.assertAlmostEqual(t.mean, 39.9)
        self.assertAlmostEqual(t.p10, 24.1)
        self.assertAlmostEqual(t.p90, 55.2)

    def test_frozen(self):
        t = _tex()
        with self.assertRaises(Exception):
            t.mean = 0.0  # type: ignore[misc]

    def test_negative_sample_count_rejected(self):
        with self.assertRaises(ValueError):
            _tex(sample_count=-1)

    def test_empty_factory(self):
        t = TextureDistributions.empty()
        self.assertEqual(t.sample_count, 0)


# ---------------------------------------------------------------------------
# FrequencyDistributions
# ---------------------------------------------------------------------------

class TestFrequencyDistributions(unittest.TestCase):
    def test_constructs(self):
        f = _freq()
        self.assertAlmostEqual(f.dominant_freq_mean, 0.12)

    def test_frozen(self):
        f = _freq()
        with self.assertRaises(Exception):
            f.dominant_freq_mean = 0.0  # type: ignore[misc]

    def test_negative_sample_count_rejected(self):
        with self.assertRaises(ValueError):
            _freq(sample_count=-1)

    def test_empty_factory(self):
        f = FrequencyDistributions.empty()
        self.assertEqual(f.sample_count, 0)


# ---------------------------------------------------------------------------
# DatasetContext
# ---------------------------------------------------------------------------

class TestDatasetContext(unittest.TestCase):
    def test_constructs(self):
        ctx = _context()
        self.assertEqual(ctx.image_count, 5)
        self.assertEqual(ctx.error_count, 0)

    def test_frozen(self):
        ctx = _context()
        with self.assertRaises(Exception):
            ctx.image_count = 99  # type: ignore[misc]

    def test_wrong_schema_version_rejected(self):
        with self.assertRaises(ValueError):
            _context(schema_version=999)

    def test_negative_image_count_rejected(self):
        with self.assertRaises(ValueError):
            _context(image_count=-1)

    def test_negative_error_count_rejected(self):
        with self.assertRaises(ValueError):
            _context(error_count=-1)

    def test_analyzed_count_property(self):
        ctx = _context(image_count=10, error_count=2)
        self.assertEqual(ctx.analyzed_count, 8)

    def test_exact_duplicate_count_no_dupes(self):
        ctx = _context(duplicate_groups=())
        self.assertEqual(ctx.exact_duplicate_count, 0)

    def test_exact_duplicate_count_with_dupes(self):
        group = (Path("a.png"), Path("b.png"), Path("c.png"))
        ctx = _context(duplicate_groups=(group,))
        # 3 images in group → 2 duplicates (one is the "original")
        self.assertEqual(ctx.exact_duplicate_count, 2)

    def test_empty_factory(self):
        ctx = DatasetContext.empty()
        self.assertEqual(ctx.image_count, 0)
        self.assertEqual(ctx.analyzed_count, 0)

    def test_empty_factory_with_paths(self):
        paths = [Path("a.png"), Path("b.png")]
        ctx = DatasetContext.empty(image_paths=paths)
        self.assertEqual(ctx.image_count, 2)
        self.assertEqual(len(ctx.image_paths), 2)


class TestDatasetContextSerialization(unittest.TestCase):
    def test_to_dict_returns_dict(self):
        d = _context().to_dict()
        self.assertIsInstance(d, dict)

    def test_to_dict_schema_present(self):
        d = _context().to_dict()
        self.assertEqual(d["schema"], CONTEXT_SCHEMA)

    def test_to_dict_contains_all_sections(self):
        d = _context().to_dict()
        for key in ("schema_version", "image_count", "error_count", "analyzed_count",
                    "resolution_stats", "aspect_ratio_stats",
                    "texture_distributions", "frequency_distributions",
                    "duplicate_groups", "analyzer_versions"):
            self.assertIn(key, d, f"missing key: {key}")

    def test_to_dict_duplicate_groups_are_strings(self):
        group = (Path("a.png"), Path("b.png"))
        d = _context(duplicate_groups=(group,)).to_dict()
        self.assertIsInstance(d["duplicate_groups"][0][0], str)

    def test_to_dict_nested_stats_are_dicts(self):
        d = _context().to_dict()
        self.assertIsInstance(d["resolution_stats"], dict)
        self.assertIsInstance(d["texture_distributions"], dict)


if __name__ == "__main__":
    unittest.main()
