"""Tests for shared calibration measurement helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))

from _calibration_metrics import (
    METRICS,
    collect_texture_scores,
    measure_texture,
    texture_score_row,
)
from compute_metrics import enrich_with_live_scores
from diagnostic_report import collect_scores


def _texture(status: str = "analyzed", micro: float = 42.0):
    tex = MagicMock()
    tex.status = status
    tex.microtexture_density_score = micro
    tex.local_contrast_score = 12.0
    tex.edge_sharpness_score = 13.0
    tex.highlight_speck_score = 14.0
    tex.texture_consistency_score = 15.0
    tex.watercolor_smoothness_score = 16.0
    tex.pencil_grain_score = 17.0
    return tex


class TestCalibrationMetrics(unittest.TestCase):
    def test_measure_texture_routes_through_measure_image(self):
        path = Path("image.png")
        measurement = MagicMock()
        measurement.texture = _texture(micro=33.0)
        with patch("_calibration_metrics.measure_image", return_value=measurement) as mocked:
            result = measure_texture(path)

        mocked.assert_called_once_with(path)
        self.assertEqual(result.microtexture_density_score, 33.0)

    def test_texture_score_row_preserves_existing_metric_shape(self):
        path = Path("image.png")
        measurement = MagicMock()
        measurement.texture = _texture(micro=44.0)
        with patch("_calibration_metrics.measure_image", return_value=measurement):
            row = texture_score_row(path)

        self.assertEqual(row["filename"], "image.png")
        for key, _ in METRICS:
            self.assertIn(key, row)
        self.assertEqual(row["microtexture_density_score"], 44.0)

    def test_texture_score_row_skips_measurement_errors(self):
        measurement = MagicMock()
        measurement.texture = _texture(status="error")
        with patch("_calibration_metrics.measure_image", return_value=measurement):
            self.assertIsNone(texture_score_row(Path("bad.png")))

    def test_collect_texture_scores_skips_errors(self):
        good = MagicMock()
        good.texture = _texture(micro=10.0)
        bad = MagicMock()
        bad.texture = _texture(status="error")
        with patch("_calibration_metrics.measure_image", side_effect=[good, bad]):
            rows = collect_texture_scores([Path("a.png"), Path("b.png")])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "a.png")

    def test_diagnostic_collect_scores_uses_shared_helper(self):
        rows = [{"filename": "a.png", "microtexture_density_score": 1.0}]
        with patch("diagnostic_report.collect_texture_scores", return_value=rows) as mocked:
            result = collect_scores([Path("a.png")])

        mocked.assert_called_once_with([Path("a.png")])
        self.assertEqual(result, rows)

    def test_compute_metrics_enrichment_uses_shared_measurement_route(self):
        entry = {"filename": "image.png", "micro": None}
        with patch.object(Path, "rglob", return_value=[Path("image.png")]):
            with patch("_calibration_metrics.measure_texture", return_value=_texture(micro=55.0)) as mocked:
                enrich_with_live_scores([entry], Path("dataset"), 40.0, 5.0)

        mocked.assert_called_once_with(Path("image.png"))
        self.assertEqual(entry["micro"], 55.0)
        self.assertEqual(entry["smooth"], 16.0)
        self.assertEqual(entry["speck"], 14.0)
        self.assertEqual(entry["z"], 3.0)


if __name__ == "__main__":
    unittest.main()
