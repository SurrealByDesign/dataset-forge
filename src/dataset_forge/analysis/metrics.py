from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

ANALYSIS_SIZE = (256, 256)
PERCEPTUAL_HASH_DISTANCE = 8


@dataclass(frozen=True)
class ImageMetrics:
    width: int
    height: int
    aspect_ratio: float
    megapixels: float
    file_size: int
    color_mode: str
    average_brightness: float
    average_saturation: float
    average_contrast: float
    perceptual_hash: str
    file_hash: str
    texture_score: float
    artifact_score: float

    def to_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


def extract_image_metrics(path: Path) -> ImageMetrics:
    file_size = path.stat().st_size
    file_hash = _file_hash(path)

    with Image.open(path) as source:
        color_mode = source.mode
        image = ImageOps.exif_transpose(source).convert("RGB")
        width, height = image.size
        working = image.copy()
        working.thumbnail(ANALYSIS_SIZE, Image.Resampling.LANCZOS)

    grayscale = working.convert("L")
    hsv = working.convert("HSV")
    brightness = _round_score(ImageStat.Stat(grayscale).mean[0] / 255 * 100)
    saturation = _round_score(ImageStat.Stat(hsv).mean[1] / 255 * 100)
    contrast = _round_score(ImageStat.Stat(grayscale).stddev[0] / 127.5 * 100)
    texture_score, edge_density, local_noise = _texture_metrics(grayscale)
    artifact_score = _artifact_score(grayscale, edge_density, local_noise)

    return ImageMetrics(
        width=width,
        height=height,
        aspect_ratio=round(width / height, 4),
        megapixels=round(width * height / 1_000_000, 4),
        file_size=file_size,
        color_mode=color_mode,
        average_brightness=brightness,
        average_saturation=saturation,
        average_contrast=contrast,
        perceptual_hash=_perceptual_hash(working),
        file_hash=file_hash,
        texture_score=texture_score,
        artifact_score=artifact_score,
    )


def perceptual_hash_distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


def assign_duplicate_references(
    rows: list[dict[str, object]],
    threshold: int = PERCEPTUAL_HASH_DISTANCE,
) -> tuple[int, int]:
    exact_first: dict[str, str] = {}
    prior_rows: list[dict[str, object]] = []
    exact_count = 0
    probable_count = 0

    for row in rows:
        row["exact_duplicate_of"] = ""
        row["probable_duplicate_of"] = ""
        if row.get("status") == "error":
            continue

        file_hash = str(row["file_hash"])
        original_path = str(row["original_path"])
        if file_hash in exact_first:
            row["exact_duplicate_of"] = exact_first[file_hash]
            exact_count += 1
        else:
            exact_first[file_hash] = original_path
            closest_path = ""
            closest_distance = threshold + 1
            for prior in prior_rows:
                if prior["file_hash"] == file_hash:
                    continue
                if not _plausible_visual_match(row, prior):
                    continue
                distance = perceptual_hash_distance(
                    str(row["perceptual_hash"]),
                    str(prior["perceptual_hash"]),
                )
                if distance <= threshold and distance < closest_distance:
                    closest_path = str(prior["original_path"])
                    closest_distance = distance
            if closest_path:
                row["probable_duplicate_of"] = closest_path
                probable_count += 1

        prior_rows.append(row)

    return exact_count, probable_count


def _plausible_visual_match(
    first: dict[str, object],
    second: dict[str, object],
) -> bool:
    return (
        abs(float(first["aspect_ratio"]) - float(second["aspect_ratio"])) <= 0.02
        and abs(
            float(first["average_brightness"])
            - float(second["average_brightness"])
        ) <= 10
        and abs(
            float(first["average_saturation"])
            - float(second["average_saturation"])
        ) <= 15
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _perceptual_hash(image: Image.Image) -> str:
    sample = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = _pixel_values(sample)
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return f"{bits:016x}"


def _texture_metrics(grayscale: Image.Image) -> tuple[float, float, float]:
    pixels, width, height = _pixels(grayscale)
    if width < 3 or height < 3:
        return 0.0, 0.0, 0.0

    laplacian_values: list[float] = []
    edge_pixels = 0
    local_variances: list[float] = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            center = pixels[y * width + x]
            left = pixels[y * width + x - 1]
            right = pixels[y * width + x + 1]
            up = pixels[(y - 1) * width + x]
            down = pixels[(y + 1) * width + x]
            laplacian_values.append(4 * center - left - right - up - down)
            gradient = abs(right - left) + abs(down - up)
            if gradient > 60:
                edge_pixels += 1

    laplacian_variance = _variance(laplacian_values)
    interior_count = (width - 2) * (height - 2)
    edge_density = edge_pixels / interior_count

    block_size = 8
    for top in range(0, height, block_size):
        for left in range(0, width, block_size):
            block = [
                pixels[y * width + x]
                for y in range(top, min(top + block_size, height))
                for x in range(left, min(left + block_size, width))
            ]
            if len(block) > 1:
                local_variances.append(_variance(block))

    local_variance = sum(local_variances) / len(local_variances) if local_variances else 0.0
    laplacian_score = _saturating_score(laplacian_variance, 2500)
    edge_score = min(100.0, edge_density / 0.35 * 100)
    local_score = _saturating_score(local_variance, 1500)
    texture = 0.45 * laplacian_score + 0.30 * edge_score + 0.25 * local_score
    local_noise = min(100.0, math.sqrt(local_variance) / 45 * 100)
    return _round_score(texture), edge_density, local_noise


def _artifact_score(
    grayscale: Image.Image,
    edge_density: float,
    local_noise: float,
) -> float:
    pixels, width, height = _pixels(grayscale)
    blurred = _pixel_values(grayscale.filter(ImageFilter.GaussianBlur(radius=1)))
    high_frequency = sum(abs(value - blurred[index]) for index, value in enumerate(pixels))
    high_frequency /= max(1, len(pixels))
    high_frequency_score = min(100.0, high_frequency / 22 * 100)

    isolated_highlights = 0
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            index = y * width + x
            if pixels[index] < 245:
                continue
            neighbors = (
                pixels[index - 1],
                pixels[index + 1],
                pixels[index - width],
                pixels[index + width],
            )
            if sum(neighbors) / 4 < 205:
                isolated_highlights += 1
    highlight_ratio = isolated_highlights / max(1, (width - 2) * (height - 2))
    highlight_score = min(100.0, highlight_ratio / 0.01 * 100)
    excessive_edges = min(100.0, max(0.0, edge_density - 0.18) / 0.32 * 100)

    score = (
        0.35 * high_frequency_score
        + 0.20 * highlight_score
        + 0.25 * excessive_edges
        + 0.20 * local_noise
    )
    return _round_score(score)


def _pixels(image: Image.Image) -> tuple[list[int], int, int]:
    width, height = image.size
    return _pixel_values(image), width, height


def _pixel_values(image: Image.Image) -> list[int]:
    flattened = getattr(image, "get_flattened_data", None)
    if flattened is not None:
        return list(flattened())
    return list(image.getdata())


def _variance(values: list[float] | list[int]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _saturating_score(value: float, scale: float) -> float:
    return 100 * (1 - math.exp(-value / scale))


def _round_score(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)
