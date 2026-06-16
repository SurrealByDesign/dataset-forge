from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from dataset_forge.cleanup.profiles import CleanupProfile

IMPLEMENTED_OPERATIONS = {
    "bilateral_filter",
    "edge_preserving_smoothing",
    "frequency_smoothing",
    "local_contrast_normalization",
    "speck_removal",
}


def process_traditional_cleanup(
    source: Path,
    target: Path,
    profile: CleanupProfile,
) -> dict[str, Any]:
    cv2, np = _opencv()
    with Image.open(source) as opened:
        image_format = opened.format or _format_for_suffix(source.suffix)
        transposed = ImageOps.exif_transpose(opened)
        alpha = transposed.getchannel("A") if "A" in transposed.getbands() else None
        original = np.asarray(transposed.convert("RGB"), dtype=np.uint8)

    cleaned = original.copy()
    operations_applied: list[dict[str, Any]] = []
    for operation in profile.operations:
        if operation.name not in IMPLEMENTED_OPERATIONS:
            continue
        cleaned = _apply_operation(
            operation.name,
            cleaned,
            operation.parameters,
            cv2,
            np,
        )
        operations_applied.append(operation.to_dict())

    metrics_before = _image_metrics(original, cv2, np)
    metrics_after = _image_metrics(cleaned, cv2, np)
    preservation = _preservation_metrics(original, cleaned, cv2, np)
    rejection_reason = _rejection_reason(
        preservation,
        profile.acceptance_checks,
    )
    accepted = rejection_reason == ""

    output_hash: str | None = None
    bytes_written = 0
    if accepted:
        target.parent.mkdir(parents=True, exist_ok=True)
        output_image = Image.fromarray(cleaned, mode="RGB")
        if alpha is not None:
            output_image.putalpha(alpha)
        save_options: dict[str, Any] = {}
        if image_format.upper() in {"JPEG", "JPG"}:
            save_options.update({"quality": 95, "subsampling": 0})
        output_image.save(target, format=image_format, **save_options)
        output_hash = _sha256(target)
        bytes_written = target.stat().st_size

    metadata = {
        "plugin_id": "cleanup.traditional_cleanup",
        "profile": profile.name,
        "requested_operations": [op.to_dict() for op in profile.operations],
        "operations_applied": operations_applied,
        "parameters": {op.name: dict(op.parameters) for op in profile.operations},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source),
        "source_hash": _sha256(source),
        "output_hash": output_hash,
        "placeholder": False,
        "accepted": accepted,
        "rejection_reason": rejection_reason,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "preservation_metrics": preservation,
        "acceptance_checks": dict(profile.acceptance_checks),
    }
    metadata_path = target.with_name(target.name + ".json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "output_path": target if accepted else None,
        "metadata_path": metadata_path,
        "bytes_written": bytes_written,
        "accepted": accepted,
        "rejection_reason": rejection_reason,
        "preservation_metrics": preservation,
        "operations_applied": operations_applied,
        "source_path": source,
    }


def generate_comparison_sheet(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    thumbnails = output_dir / "comparison_thumbnails"
    thumbnails.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for metadata_path in sorted(output_dir.glob("*.*.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metadata.get("placeholder") is not False:
            continue
        source = Path(str(metadata.get("source_path", "")))
        target = metadata_path.with_name(metadata_path.name[:-5])
        source_thumb = _write_thumbnail(source, thumbnails, "original")
        cleaned_thumb = (
            _write_thumbnail(target, thumbnails, "cleaned")
            if metadata.get("accepted") and target.is_file()
            else None
        )
        preservation = metadata.get("preservation_metrics", {})
        operations = ", ".join(
            str(item.get("name", ""))
            for item in metadata.get("operations_applied", [])
        )
        cards.append(
            _comparison_card(
                source.name,
                bool(metadata.get("accepted")),
                str(metadata.get("rejection_reason", "")),
                source_thumb,
                cleaned_thumb,
                preservation,
                operations,
            )
        )

    page = output_dir / "comparison_sheet.html"
    page.write_text(
        _comparison_page(cards),
        encoding="utf-8",
    )
    return page


def _apply_operation(
    name: str,
    image: Any,
    parameters: dict[str, Any],
    cv2: Any,
    np: Any,
) -> Any:
    if name == "speck_removal":
        return _speck_removal(image, parameters, cv2, np)
    if name == "edge_preserving_smoothing":
        return _edge_preserving_smoothing(image, parameters, cv2, np)
    if name == "local_contrast_normalization":
        return _local_contrast_normalization(image, parameters, cv2, np)
    if name == "frequency_smoothing":
        return _frequency_smoothing(image, parameters, cv2, np)
    if name == "bilateral_filter":
        return _bilateral_filter(image, parameters, cv2, np)
    return image


def _speck_removal(image: Any, parameters: dict[str, Any], cv2: Any, np: Any) -> Any:
    sensitivity = int(parameters.get("sensitivity", 32))
    max_area = max(1, int(parameters.get("max_area", parameters.get("min_area", 4))))
    blend = _bounded_float(parameters.get("replacement_blend", 0.7), 0.0, 1.0)
    median_kernel = _odd_kernel(parameters.get("median_kernel", 3))
    median = cv2.medianBlur(image, median_kernel)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    median_gray = cv2.cvtColor(median, cv2.COLOR_RGB2GRAY)
    outliers = (cv2.absdiff(gray, median_gray) >= sensitivity).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(outliers, 8)
    mask = np.zeros(gray.shape, dtype=np.uint8)
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area <= max_area:
            mask[labels == label] = 255
    mixed = cv2.addWeighted(image, 1.0 - blend, median, blend, 0)
    result = image.copy()
    result[mask > 0] = mixed[mask > 0]
    return result


def _edge_preserving_smoothing(
    image: Any,
    parameters: dict[str, Any],
    cv2: Any,
    np: Any,
) -> Any:
    sigma_spatial = float(
        parameters.get("sigma_spatial", parameters.get("strength", 18))
    )
    sigma_range = float(parameters.get("sigma_range", 0.12))
    blend = _bounded_float(parameters.get("blend", 0.22), 0.0, 1.0)
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    filtered = cv2.edgePreservingFilter(
        bgr,
        flags=cv2.RECURS_FILTER,
        sigma_s=max(1.0, sigma_spatial),
        sigma_r=_bounded_float(sigma_range, 0.01, 1.0),
    )
    filtered = cv2.cvtColor(filtered, cv2.COLOR_BGR2RGB)
    return cv2.addWeighted(image, 1.0 - blend, filtered, blend, 0)


def _local_contrast_normalization(
    image: Any,
    parameters: dict[str, Any],
    cv2: Any,
    np: Any,
) -> Any:
    clip_limit = max(0.1, float(parameters.get("clip_limit", 1.35)))
    grid = max(2, int(parameters.get("tile_grid_size", 8)))
    blend = _bounded_float(parameters.get("blend", 0.14), 0.0, 1.0)
    lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
    luminance, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid, grid))
    normalized = clahe.apply(luminance)
    adjusted = cv2.cvtColor(
        cv2.merge((normalized, a_channel, b_channel)),
        cv2.COLOR_LAB2RGB,
    )
    return cv2.addWeighted(image, 1.0 - blend, adjusted, blend, 0)


def _bilateral_filter(
    image: Any,
    parameters: dict[str, Any],
    cv2: Any,
    np: Any,
) -> Any:
    d = max(3, int(parameters.get("diameter", 5)))
    sigma_color = max(1.0, float(parameters.get("sigma_color", 25.0)))
    sigma_space = max(1.0, float(parameters.get("sigma_space", 2.0)))
    blend = _bounded_float(parameters.get("blend", 0.5), 0.0, 1.0)
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    filtered = cv2.bilateralFilter(bgr, d, sigma_color, sigma_space)
    filtered = cv2.cvtColor(filtered, cv2.COLOR_BGR2RGB)
    return cv2.addWeighted(image, 1.0 - blend, filtered, blend, 0)


def _frequency_smoothing(
    image: Any,
    parameters: dict[str, Any],
    cv2: Any,
    np: Any,
) -> Any:
    sigma = max(0.5, float(parameters.get("sigma", 1.0)))
    blend = _bounded_float(parameters.get("blend", 0.25), 0.0, 1.0)
    blurred = cv2.GaussianBlur(image, (0, 0), sigma)
    return cv2.addWeighted(image, 1.0 - blend, blurred, blend, 0)


def _image_metrics(image: Any, cv2: Any, np: Any) -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    mean_color = np.mean(image, axis=(0, 1))
    return {
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "average_luminance": round(float(np.mean(gray)), 4),
        "average_color_rgb": [round(float(value), 4) for value in mean_color],
        "edge_density": round(float(np.count_nonzero(edges) / edges.size), 6),
    }


def _preservation_metrics(original: Any, cleaned: Any, cv2: Any, np: Any) -> dict[str, float]:
    pixel_difference = float(
        np.mean(np.abs(original.astype(np.float32) - cleaned.astype(np.float32)))
    )
    histogram_differences: list[float] = []
    for channel in range(3):
        original_hist = cv2.calcHist([original], [channel], None, [64], [0, 256])
        cleaned_hist = cv2.calcHist([cleaned], [channel], None, [64], [0, 256])
        cv2.normalize(original_hist, original_hist)
        cv2.normalize(cleaned_hist, cleaned_hist)
        histogram_differences.append(
            float(
                cv2.compareHist(
                    original_hist,
                    cleaned_hist,
                    cv2.HISTCMP_BHATTACHARYYA,
                )
            )
        )
    original_edges = cv2.Canny(
        cv2.cvtColor(original, cv2.COLOR_RGB2GRAY),
        80,
        160,
    )
    cleaned_edges = cv2.Canny(
        cv2.cvtColor(cleaned, cv2.COLOR_RGB2GRAY),
        80,
        160,
    )
    edge_difference = float(
        np.count_nonzero(original_edges != cleaned_edges) / original_edges.size
    )
    return {
        "average_pixel_difference": round(pixel_difference, 6),
        "color_histogram_difference": round(
            float(np.mean(histogram_differences)),
            6,
        ),
        "edge_difference": round(edge_difference, 6),
    }


def _rejection_reason(
    metrics: dict[str, float],
    thresholds: dict[str, float],
) -> str:
    checks = (
        (
            "average_pixel_difference",
            "max_average_pixel_difference",
            "average pixel difference",
        ),
        (
            "color_histogram_difference",
            "max_color_histogram_difference",
            "color histogram difference",
        ),
        ("edge_difference", "max_edge_difference", "edge difference"),
    )
    failures = [
        f"{label} {metrics[metric]:.6f} exceeds {thresholds[threshold]:.6f}"
        for metric, threshold, label in checks
        if threshold in thresholds and metrics[metric] > thresholds[threshold]
    ]
    return "; ".join(failures)


def _write_thumbnail(source: Path, directory: Path, role: str) -> str | None:
    if not source.is_file():
        return None
    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    target = directory / f"{role}-{digest}.jpg"
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((320, 320), Image.Resampling.LANCZOS)
            image.save(target, "JPEG", quality=82, optimize=True)
    except OSError:
        return None
    return target.relative_to(directory.parent).as_posix()


def _comparison_card(
    filename: str,
    accepted: bool,
    reason: str,
    original_thumbnail: str | None,
    cleaned_thumbnail: str | None,
    metrics: dict[str, Any],
    operations: str,
) -> str:
    status = "Accepted" if accepted else "Rejected"
    original = (
        f'<img src="{html.escape(original_thumbnail, quote=True)}" alt="Original">'
        if original_thumbnail
        else "<div class=\"missing\">Original unavailable</div>"
    )
    cleaned = (
        f'<img src="{html.escape(cleaned_thumbnail, quote=True)}" alt="Cleaned">'
        if cleaned_thumbnail
        else '<div class="missing">Rejected: no cleaned output written</div>'
    )
    metric_text = ", ".join(
        f"{key.replace('_', ' ')}: {float(value):.4f}"
        for key, value in metrics.items()
    )
    return f"""
<article class="card">
  <h2>{html.escape(filename)}</h2>
  <span class="status {'accepted' if accepted else 'rejected'}">{status}</span>
  <div class="images"><figure>{original}<figcaption>Original thumbnail</figcaption></figure>
  <figure>{cleaned}<figcaption>Cleaned thumbnail</figcaption></figure></div>
  <p><strong>Operations:</strong> {html.escape(operations or 'None')}</p>
  <p><strong>Preservation metrics:</strong> {html.escape(metric_text)}</p>
  {'<p><strong>Rejection:</strong> ' + html.escape(reason) + '</p>' if reason else ''}
</article>"""


def _comparison_page(cards: list[str]) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dataset Forge cleanup comparison</title>
<style>
body {{ margin: 0; padding: 24px; color: #e8edf4; background: #10141b; font-family: sans-serif; }}
h1 {{ margin-top: 0; }} .grid {{ display: grid; gap: 18px; }}
.card {{ padding: 18px; border: 1px solid #344052; border-radius: 12px; background: #19212c; }}
.images {{ display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 14px; }}
figure {{ margin: 0; }} img,.missing {{ width: 100%; height: 280px; object-fit: contain; background: #0b0f15; }}
.missing {{ display: grid; place-items: center; color: #aeb8c7; }}
figcaption {{ margin-top: 6px; color: #aeb8c7; }} .status {{ font-weight: 700; }}
.accepted {{ color: #6ee7a8; }} .rejected {{ color: #ff8d8d; }}
</style></head><body><h1>Cleanup comparison sheet</h1><main class="grid">
{''.join(cards) if cards else '<p>No real cleanup results are available.</p>'}
</main></body></html>"""


def _opencv() -> tuple[Any, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Traditional cleanup requires opencv-python. Install project dependencies."
        ) from exc
    return cv2, np


def _format_for_suffix(suffix: str) -> str:
    return {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }.get(suffix.lower(), "PNG")


def _bounded_float(value: Any, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _odd_kernel(value: Any, minimum: int = 3, maximum: int = 9) -> int:
    kernel = int(value)
    kernel = max(minimum, min(maximum, kernel))
    if kernel % 2 == 0:
        kernel += 1
    return kernel


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
