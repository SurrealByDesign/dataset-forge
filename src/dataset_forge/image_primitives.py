"""Small deterministic image-processing primitives for analyzers.

These helpers centralize repeated read-only preprocessing without becoming a
general image framework. They intentionally mirror the behavior analyzers used
before extraction.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


def load_rgb_thumbnail(path: Path, max_size: int) -> np.ndarray:
    """Load an image with EXIF orientation, RGB conversion, and LANCZOS thumbnail."""
    resolved = path.expanduser().resolve()
    with Image.open(resolved) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.uint8)


def rgb_to_gray_float32(rgb: np.ndarray) -> np.ndarray:
    """Convert an RGB uint8 image array to OpenCV grayscale float32."""
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)


def gaussian_blur(image: np.ndarray, sigma: float) -> np.ndarray:
    """Apply the analyzer-standard Gaussian blur for a sigma value."""
    return cv2.GaussianBlur(image, (0, 0), sigma)


def signed_residual(image: np.ndarray, sigma: float) -> np.ndarray:
    """Return image minus its Gaussian-blurred baseline."""
    return image - gaussian_blur(image, sigma)


def absolute_residual(image: np.ndarray, sigma: float) -> np.ndarray:
    """Return absolute local residual against a Gaussian-blurred baseline."""
    return np.abs(signed_residual(image, sigma))


def canny_edge_mask(
    gray: np.ndarray,
    *,
    blur_sigma: float = 1.0,
    threshold1: int = 40,
    threshold2: int = 120,
) -> np.ndarray:
    """Return a deterministic boolean Canny edge mask from grayscale input."""
    blurred = gaussian_blur(gray, blur_sigma)
    edges = cv2.Canny(
        np.clip(blurred, 0, 255).astype(np.uint8),
        threshold1=threshold1,
        threshold2=threshold2,
    )
    return edges > 0


def dilated_mask(mask: np.ndarray, kernel_size: int) -> np.ndarray:
    """Dilate a boolean mask with an elliptical kernel and return a boolean mask."""
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size),
    )
    return cv2.dilate(mask.astype(np.uint8), kernel) > 0


__all__ = [
    "absolute_residual",
    "canny_edge_mask",
    "dilated_mask",
    "gaussian_blur",
    "load_rgb_thumbnail",
    "rgb_to_gray_float32",
    "signed_residual",
]
