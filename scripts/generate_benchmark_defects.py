from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


STRENGTHS: dict[str, dict[str, Any]] = {
    "light": {
        "speckle_density": 0.0015,
        "speckle_radius": (1, 1),
        "texture_amplitude": 5.0,
        "texture_frequency": 18.0,
        "sharpen_radius": 1.0,
        "sharpen_percent": 120,
        "color_noise": 5,
    },
    "medium": {
        "speckle_density": 0.0035,
        "speckle_radius": (1, 2),
        "texture_amplitude": 9.0,
        "texture_frequency": 13.0,
        "sharpen_radius": 1.4,
        "sharpen_percent": 210,
        "color_noise": 10,
    },
    "strong": {
        "speckle_density": 0.007,
        "speckle_radius": (1, 3),
        "texture_amplitude": 15.0,
        "texture_frequency": 9.0,
        "sharpen_radius": 1.8,
        "sharpen_percent": 320,
        "color_noise": 18,
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic image defects."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/synthetic_defects"),
    )
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--strength",
        choices=tuple(STRENGTHS),
        default="medium",
    )
    return parser


def generate_benchmark(
    input_path: Path,
    output_path: Path,
    *,
    seed: int = 1234,
    strength: str = "medium",
) -> Path:
    source = input_path.expanduser().resolve()
    destination = output_path.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Reference image does not exist: {source}")
    if strength not in STRENGTHS:
        raise ValueError(f"Unknown strength: {strength}")

    source_hash = _sha256(source)
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        image.load()

    destination.mkdir(parents=True, exist_ok=True)
    parameters = dict(STRENGTHS[strength])
    generated: list[dict[str, Any]] = []

    variants: tuple[
        tuple[str, str, Callable[[Image.Image, random.Random, dict[str, Any]], Image.Image], int],
        ...,
    ] = (
        ("01_glitter_speckles.png", "glitter_speckles", _glitter_speckles, 101),
        (
            "02_recursive_microtexture.png",
            "recursive_microtexture",
            _recursive_microtexture,
            202,
        ),
        (
            "03_crunchy_oversharpened.png",
            "crunchy_oversharpened",
            _crunchy_oversharpened,
            303,
        ),
        ("04_color_noise.png", "color_noise", _color_noise, 404),
        ("05_mixed_artifacts.png", "mixed_artifacts", _mixed_artifacts, 505),
    )

    reference_name = "00_reference.png"
    image.save(destination / reference_name, "PNG")
    generated.append(
        {
            "filename": reference_name,
            "defect_type": "reference",
            "parameters": {},
        }
    )

    for filename, defect_type, generator, seed_offset in variants:
        variant = generator(image.copy(), random.Random(seed + seed_offset), parameters)
        variant.save(destination / filename, "PNG")
        generated.append(
            {
                "filename": filename,
                "defect_type": defect_type,
                "parameters": _parameters_for(defect_type, parameters),
            }
        )

    manifest = {
        "source_image_path": str(source),
        "source_image_hash": source_hash,
        "seed": seed,
        "strength": strength,
        "generated_files": generated,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = destination / "benchmark_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _glitter_speckles(
    image: Image.Image,
    rng: random.Random,
    parameters: dict[str, Any],
) -> Image.Image:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    count = max(1, round(width * height * parameters["speckle_density"]))
    radius_min, radius_max = parameters["speckle_radius"]
    colors = (
        (255, 255, 255, 220),
        (255, 240, 190, 210),
        (210, 245, 255, 205),
    )
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.randint(radius_min, radius_max)
        color = colors[rng.randrange(len(colors))]
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=color,
        )
    return image


def _recursive_microtexture(
    image: Image.Image,
    rng: random.Random,
    parameters: dict[str, Any],
) -> Image.Image:
    pixels = image.load()
    width, height = image.size
    amplitude = float(parameters["texture_amplitude"])
    frequency = float(parameters["texture_frequency"])
    phase_x = rng.random() * math.tau
    phase_y = rng.random() * math.tau
    for y in range(height):
        for x in range(width):
            wave = (
                math.sin(x / frequency + phase_x)
                * math.sin(y / frequency + phase_y)
                + 0.5
                * math.sin((x + y) / (frequency * 0.55) + phase_x)
            )
            delta = round(amplitude * wave)
            red, green, blue, alpha = pixels[x, y]
            pixels[x, y] = (
                _clamp(red + delta),
                _clamp(green - delta // 3),
                _clamp(blue + delta // 2),
                alpha,
            )
    return image


def _crunchy_oversharpened(
    image: Image.Image,
    rng: random.Random,
    parameters: dict[str, Any],
) -> Image.Image:
    del rng
    sharpened = image.filter(
        ImageFilter.UnsharpMask(
            radius=float(parameters["sharpen_radius"]),
            percent=int(parameters["sharpen_percent"]),
            threshold=1,
        )
    )
    return ImageEnhance.Contrast(sharpened).enhance(1.08)


def _color_noise(
    image: Image.Image,
    rng: random.Random,
    parameters: dict[str, Any],
) -> Image.Image:
    pixels = image.load()
    width, height = image.size
    noise = int(parameters["color_noise"])
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            pixels[x, y] = (
                _clamp(red + rng.randint(-noise, noise)),
                _clamp(green + rng.randint(-noise, noise)),
                _clamp(blue + rng.randint(-noise, noise)),
                alpha,
            )
    return image


def _mixed_artifacts(
    image: Image.Image,
    rng: random.Random,
    parameters: dict[str, Any],
) -> Image.Image:
    image = _recursive_microtexture(image, rng, parameters)
    image = _color_noise(image, rng, parameters)
    image = _crunchy_oversharpened(image, rng, parameters)
    return _glitter_speckles(image, rng, parameters)


def _parameters_for(
    defect_type: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    keys = {
        "glitter_speckles": ("speckle_density", "speckle_radius"),
        "recursive_microtexture": ("texture_amplitude", "texture_frequency"),
        "crunchy_oversharpened": ("sharpen_radius", "sharpen_percent"),
        "color_noise": ("color_noise",),
        "mixed_artifacts": tuple(parameters),
    }[defect_type]
    return {key: parameters[key] for key in keys}


def _clamp(value: int) -> int:
    return max(0, min(255, value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = generate_benchmark(
            args.input,
            args.output,
            seed=args.seed,
            strength=args.strength,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
    print(f"Benchmark manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
