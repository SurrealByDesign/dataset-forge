"""Tests for shared deterministic image primitives."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from dataset_forge.image_primitives import (
    absolute_residual,
    canny_edge_mask,
    dilated_mask,
    gaussian_blur,
    load_rgb_thumbnail,
    rgb_to_gray_float32,
    signed_residual,
)


class TestImagePrimitives(unittest.TestCase):
    def test_load_rgb_thumbnail_converts_to_rgb_and_bounds_size(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gray.png"
            arr = np.full((40, 80), 128, dtype=np.uint8)
            Image.fromarray(arr, mode="L").save(path)

            rgb = load_rgb_thumbnail(path, max_size=16)

        self.assertEqual(rgb.dtype, np.uint8)
        self.assertEqual(rgb.shape[2], 3)
        self.assertLessEqual(rgb.shape[0], 16)
        self.assertLessEqual(rgb.shape[1], 16)

    def test_load_rgb_thumbnail_applies_exif_orientation(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "oriented.jpg"
            image = Image.new("RGB", (10, 20), (10, 20, 30))
            exif = Image.Exif()
            exif[274] = 6
            image.save(path, exif=exif)

            rgb = load_rgb_thumbnail(path, max_size=100)

        self.assertEqual(rgb.shape[:2], (10, 20))

    def test_rgb_to_gray_float32_matches_opencv_conversion(self):
        rgb = np.array(
            [
                [[255, 0, 0], [0, 255, 0]],
                [[0, 0, 255], [255, 255, 255]],
            ],
            dtype=np.uint8,
        )

        gray = rgb_to_gray_float32(rgb)

        self.assertEqual(gray.dtype, np.float32)
        np.testing.assert_array_equal(
            gray,
            cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32),
        )

    def test_residual_helpers_match_gaussian_baseline(self):
        image = np.zeros((9, 9), dtype=np.float32)
        image[4, 4] = 255.0

        blurred = gaussian_blur(image, 1.2)
        signed = signed_residual(image, 1.2)
        absolute = absolute_residual(image, 1.2)

        np.testing.assert_allclose(signed, image - blurred)
        np.testing.assert_allclose(absolute, np.abs(signed))

    def test_canny_edge_mask_and_dilation_are_deterministic_booleans(self):
        gray = np.zeros((64, 64), dtype=np.float32)
        gray[16:48, 16:48] = 255.0

        edges = canny_edge_mask(gray)
        dilated = dilated_mask(edges, 5)

        self.assertEqual(edges.dtype, np.bool_)
        self.assertEqual(dilated.dtype, np.bool_)
        self.assertEqual(edges.shape, gray.shape)
        self.assertEqual(dilated.shape, gray.shape)
        self.assertGreater(int(np.sum(edges)), 0)
        self.assertGreaterEqual(int(np.sum(dilated)), int(np.sum(edges)))


if __name__ == "__main__":
    unittest.main()
