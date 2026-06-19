"""Tests for explicit image measurement routing."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from os import environ
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analysis.texture import TextureImageResult
from dataset_forge.measurement_cache import ENV_CACHE_DIR, ENV_DISABLE_CACHE
from dataset_forge.measurements import ImageMeasurements, measure_image


def _write_image(path: Path) -> None:
    arr = np.full((64, 64, 3), 128, dtype=np.uint8)
    Image.fromarray(arr).save(path)


class TestImageMeasurements(unittest.TestCase):
    def test_measure_image_returns_frozen_measurements(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "image.png"
            _write_image(path)

            with patch.dict(
                environ,
                {ENV_CACHE_DIR: "", ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                measurements = measure_image(path)

        self.assertIsInstance(measurements, ImageMeasurements)
        self.assertIsInstance(measurements.texture, TextureImageResult)
        with self.assertRaises(FrozenInstanceError):
            measurements.image_path = Path("other.png")  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
