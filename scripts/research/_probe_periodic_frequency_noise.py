"""Periodic frequency noise probe.

Research-only script. Does not modify production analyzer code, measurement
code, benchmark schemas, reports, CLI behavior, thresholds, or calibration
status.

Candidate signal:
  - FFT symmetric peak analysis
  - directional Fourier energy
  - normalized spectral entropy
  - autocorrelation repeat-period confirmation

The probe generates temporary synthetic cases under benchmarks/results and
also measures existing committed fixtures for current analyzer families.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = _ROOT / "benchmarks" / "results" / "probe_periodic_frequency_noise"
FIXTURE_DIR = _ROOT / "benchmarks" / "synthetic_defects"
ANALYSIS_MAX = 512


@dataclass(frozen=True)
class ProbeCase:
    case_id: str
    group: str
    path: Path
    description: str


@dataclass(frozen=True)
class PeriodicMeasurements:
    symmetric_peak_pair_count: int
    max_peak_prominence_ratio: float
    median_peak_prominence_ratio: float
    directional_energy_ratio: float
    spectral_entropy: float
    autocorrelation_peak_strength: float
    estimated_repeat_period_px: float
    periodic_energy_ratio: float


def _load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        image.thumbnail((ANALYSIS_MAX, ANALYSIS_MAX), Image.Resampling.LANCZOS)
        rgb = np.asarray(image, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)


def _radial_distances(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = shape
    yy, xx = np.indices((h, w))
    cy = h // 2
    cx = w // 2
    dy = yy - cy
    dx = xx - cx
    radius = np.sqrt(dx * dx + dy * dy)
    angle = np.arctan2(dy, dx)
    return radius, angle, np.asarray((cy, cx), dtype=np.int32)


def _windowed_power(gray: np.ndarray) -> np.ndarray:
    centered = gray - float(np.mean(gray))
    window_y = np.hanning(gray.shape[0]).astype(np.float32)
    window_x = np.hanning(gray.shape[1]).astype(np.float32)
    window = np.outer(window_y, window_x)
    spectrum = np.fft.fftshift(np.fft.fft2(centered * window))
    return np.abs(spectrum) ** 2


def _annulus_reference(power: np.ndarray, radius: np.ndarray, r: float) -> float:
    ring = (radius >= max(1.0, r - 2.0)) & (radius <= r + 2.0)
    values = power[ring]
    if values.size == 0:
        return 0.0
    return float(np.percentile(values, 95))


def _find_symmetric_peak_pairs(
    power: np.ndarray,
    radius: np.ndarray,
    center: np.ndarray,
) -> list[tuple[tuple[int, int], tuple[int, int], float]]:
    h, w = power.shape
    min_r = max(5.0, min(h, w) * 0.025)
    max_r = min(h, w) * 0.42
    valid = (radius >= min_r) & (radius <= max_r)

    local_max = power == cv2.dilate(power.astype(np.float64), np.ones((5, 5), np.uint8))
    candidate_mask = local_max & valid
    coords = np.argwhere(candidate_mask)

    peaks: list[tuple[int, int, float]] = []
    for y, x in coords:
        ring_reference = _annulus_reference(power, radius, float(radius[y, x]))
        prominence = float(power[y, x] / max(ring_reference, 1e-9))
        if prominence >= 3.0:
            peaks.append((int(y), int(x), prominence))

    peaks.sort(key=lambda item: item[2], reverse=True)
    peaks = peaks[:40]
    peak_by_coord = {(y, x): prom for y, x, prom in peaks}
    used: set[tuple[int, int]] = set()
    pairs: list[tuple[tuple[int, int], tuple[int, int], float]] = []

    cy, cx = int(center[0]), int(center[1])
    for y, x, prom in peaks:
        if (y, x) in used:
            continue
        sy = 2 * cy - y
        sx = 2 * cx - x
        best_coord: tuple[int, int] | None = None
        best_prom = 0.0
        for yy in range(max(0, sy - 2), min(h, sy + 3)):
            for xx in range(max(0, sx - 2), min(w, sx + 3)):
                other_prom = peak_by_coord.get((yy, xx), 0.0)
                if other_prom > best_prom:
                    best_coord = (yy, xx)
                    best_prom = other_prom
        if best_coord is None or best_coord == (y, x):
            continue
        used.add((y, x))
        used.add(best_coord)
        pairs.append(((y, x), best_coord, min(prom, best_prom)))

    return pairs[:12]


def _directional_energy_ratio(power: np.ndarray, radius: np.ndarray, angle: np.ndarray) -> float:
    valid = (radius >= max(5.0, min(power.shape) * 0.025)) & (
        radius <= min(power.shape) * 0.42
    )
    if not np.any(valid):
        return 0.0
    # Direction is pi-periodic: opposite FFT peaks describe the same direction.
    folded = np.mod(angle[valid], math.pi)
    weights = power[valid]
    bins = np.linspace(0.0, math.pi, 19)
    hist, _ = np.histogram(folded, bins=bins, weights=weights)
    total = float(np.sum(hist))
    if total <= 1e-9:
        return 0.0
    return float(np.max(hist) / total)


def _spectral_entropy(power: np.ndarray, radius: np.ndarray) -> float:
    valid = (radius >= max(5.0, min(power.shape) * 0.025)) & (
        radius <= min(power.shape) * 0.42
    )
    values = power[valid].astype(np.float64)
    total = float(np.sum(values))
    if total <= 1e-9 or values.size <= 1:
        return 0.0
    probs = values / total
    entropy = -float(np.sum(probs * np.log(probs + 1e-12)))
    return entropy / math.log(values.size)


def _autocorrelation(gray: np.ndarray) -> tuple[float, float]:
    centered = gray - float(np.mean(gray))
    fft = np.fft.fft2(centered)
    autocorr = np.fft.fftshift(np.fft.ifft2(np.abs(fft) ** 2).real)
    center_value = float(autocorr[autocorr.shape[0] // 2, autocorr.shape[1] // 2])
    if center_value <= 1e-9:
        return 0.0, 0.0
    autocorr = autocorr / center_value
    radius, _, _ = _radial_distances(autocorr.shape)
    min_r = 6.0
    max_r = min(80.0, min(autocorr.shape) * 0.35)
    valid = (radius >= min_r) & (radius <= max_r)
    if not np.any(valid):
        return 0.0, 0.0
    masked = np.where(valid, autocorr, 0.0)
    index = np.unravel_index(int(np.argmax(masked)), masked.shape)
    strength = float(masked[index])
    period = float(radius[index])
    return strength, period


def measure_periodicity(path: Path) -> PeriodicMeasurements:
    gray = _load_gray(path)
    if min(gray.shape) < 32:
        return PeriodicMeasurements(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    power = _windowed_power(gray)
    radius, angle, center = _radial_distances(power.shape)
    pairs = _find_symmetric_peak_pairs(power, radius, center)
    pair_proms = [pair[2] for pair in pairs]
    max_peak = max(pair_proms) if pair_proms else 0.0
    median_peak = statistics.median(pair_proms) if pair_proms else 0.0

    valid = (radius >= max(5.0, min(power.shape) * 0.025)) & (
        radius <= min(power.shape) * 0.42
    )
    total_energy = float(np.sum(power[valid]))
    pair_energy = 0.0
    for (a, b, _) in pairs[:4]:
        for y, x in (a, b):
            disk = (np.indices(power.shape)[0] - y) ** 2 + (
                np.indices(power.shape)[1] - x
            ) ** 2 <= 2 ** 2
            pair_energy += float(np.sum(power[disk]))
    periodic_energy_ratio = pair_energy / total_energy if total_energy > 1e-9 else 0.0

    ac_strength, ac_period = _autocorrelation(gray)

    return PeriodicMeasurements(
        symmetric_peak_pair_count=len(pairs),
        max_peak_prominence_ratio=round(max_peak, 4),
        median_peak_prominence_ratio=round(float(median_peak), 4),
        directional_energy_ratio=round(_directional_energy_ratio(power, radius, angle), 4),
        spectral_entropy=round(_spectral_entropy(power, radius), 4),
        autocorrelation_peak_strength=round(ac_strength, 4),
        estimated_repeat_period_px=round(ac_period, 4),
        periodic_energy_ratio=round(periodic_energy_ratio, 6),
    )


def _base_gradient(size: int = 256) -> np.ndarray:
    x = np.linspace(-1, 1, size, dtype=np.float32)
    y = np.linspace(-1, 1, size, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    base = 142 + 9 * xx + 5 * yy
    return np.stack([base + 4, base + 1, base - 3], axis=2)


def _save(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").save(path)


def _generate_probe_fixtures(output_dir: Path) -> list[ProbeCase]:
    fixture_dir = output_dir / "generated_fixtures"
    size = 256
    x = np.arange(size, dtype=np.float32)
    y = np.arange(size, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    base = _base_gradient(size)

    cases: list[ProbeCase] = []

    def add(case_id: str, group: str, arr: np.ndarray, description: str) -> None:
        path = fixture_dir / f"{case_id}.png"
        _save(path, arr)
        cases.append(ProbeCase(case_id, group, path, description))

    add(
        "periodic_sine_horizontal",
        "positive",
        base + 22 * np.sin(2 * math.pi * xx / 12.0)[:, :, None],
        "synthetic horizontal sinusoidal periodic contamination",
    )
    add(
        "periodic_diagonal",
        "positive",
        base + 20 * np.sin(2 * math.pi * (xx + yy) / 15.0)[:, :, None],
        "synthetic diagonal sinusoidal periodic contamination",
    )
    add(
        "periodic_grid",
        "positive",
        base
        + 14 * np.sin(2 * math.pi * xx / 16.0)[:, :, None]
        + 14 * np.sin(2 * math.pi * yy / 16.0)[:, :, None],
        "synthetic grid periodic contamination",
    )
    add(
        "watercolor_noise",
        "negative",
        base + np.random.default_rng(2201).normal(0, 3.0, base.shape),
        "normal low-amplitude watercolor-like texture",
    )
    add(
        "pencil_grain_noise",
        "guard",
        base
        + np.random.default_rng(2202).normal(0, 9.0, base.shape)
        + 3 * np.sin(2 * math.pi * (xx + yy) / 37.0)[:, :, None],
        "normal pencil/paper grain guard",
    )

    stripes = base.copy()
    stripes[:, (np.arange(size) // 12) % 2 == 0, :] += 35
    add("intentional_stripes", "guard", stripes, "intentional stripe pattern")

    checker = base.copy()
    mask = ((np.arange(size)[:, None] // 16) + (np.arange(size)[None, :] // 16)) % 2
    checker[mask == 0] += 35
    checker[mask == 1] -= 25
    add("intentional_checker", "guard", checker, "intentional checker pattern")

    plaid = base.copy()
    plaid[:, (np.arange(size) // 18) % 2 == 0, 0] += 35
    plaid[(np.arange(size) // 22) % 2 == 0, :, 2] += 35
    add("intentional_plaid", "guard", plaid, "intentional plaid pattern")

    return cases


def _existing_fixture_cases() -> list[ProbeCase]:
    requested = [
        ("fixture_texture_clean", "negative", "09_texture_clean.png", "committed texture clean fixture"),
        ("fixture_texture_positive", "guard", "10_texture_positive.png", "committed microtexture positive fixture"),
        ("fixture_crystalline_medium", "guard", "07_crystalline_medium.png", "committed crystalline fixture"),
        ("fixture_oversharpen_halo", "guard", "12_oversharpen_halo_positive.png", "committed oversharpening fixture"),
        ("fixture_hfi_bright", "guard", "15_hfi_bright_speck_positive.png", "committed HFI bright speck fixture"),
        ("fixture_hfi_dark", "guard", "16_hfi_dark_speck_positive.png", "committed HFI dark speck fixture"),
    ]
    cases: list[ProbeCase] = []
    for case_id, group, filename, description in requested:
        path = FIXTURE_DIR / filename
        if path.exists():
            cases.append(ProbeCase(case_id, group, path, description))
    return cases


def _candidate_detected(row: dict, thresholds: dict[str, float]) -> bool:
    return (
        row["symmetric_peak_pair_count"] >= thresholds["min_symmetric_peak_pair_count"]
        and row["max_peak_prominence_ratio"] >= thresholds["min_max_peak_prominence_ratio"]
        and row["autocorrelation_peak_strength"] >= thresholds["min_autocorrelation_peak_strength"]
        and row["periodic_energy_ratio"] >= thresholds["min_periodic_energy_ratio"]
        and row["spectral_entropy"] <= thresholds["max_spectral_entropy"]
    )


def _separation_summary(rows: list[dict], metric: str) -> dict:
    positives = [float(r[metric]) for r in rows if r["group"] == "positive"]
    guards = [float(r[metric]) for r in rows if r["group"] == "guard"]
    negatives = [float(r[metric]) for r in rows if r["group"] == "negative"]
    return {
        "metric": metric,
        "positive_min": min(positives) if positives else None,
        "positive_median": statistics.median(positives) if positives else None,
        "guard_max": max(guards) if guards else None,
        "guard_median": statistics.median(guards) if guards else None,
        "negative_max": max(negatives) if negatives else None,
    }


def _recommend_thresholds(rows: list[dict]) -> dict[str, float]:
    positives = [r for r in rows if r["group"] == "positive"]
    guards = [r for r in rows if r["group"] == "guard"]
    if not positives:
        return {}
    return {
        "min_symmetric_peak_pair_count": 1,
        "min_max_peak_prominence_ratio": round(
            max(4.0, min(r["max_peak_prominence_ratio"] for r in positives) * 0.8),
            4,
        ),
        "min_autocorrelation_peak_strength": round(
            max(0.05, min(r["autocorrelation_peak_strength"] for r in positives) * 0.8),
            4,
        ),
        "min_periodic_energy_ratio": round(
            max(0.005, min(r["periodic_energy_ratio"] for r in positives) * 0.8),
            6,
        ),
        "max_spectral_entropy": round(
            min(0.98, max(r["spectral_entropy"] for r in positives) * 1.05),
            4,
        ),
        "guard_max_peak_prominence_ratio": (
            round(max(r["max_peak_prominence_ratio"] for r in guards), 4)
            if guards else 0.0
        ),
    }


def _verdict(rows: list[dict], thresholds: dict[str, float]) -> str:
    if not thresholds:
        return "REJECT"
    positives = [r for r in rows if r["group"] == "positive"]
    guards = [r for r in rows if r["group"] == "guard"]
    negatives = [r for r in rows if r["group"] == "negative"]
    pos_hits = sum(_candidate_detected(r, thresholds) for r in positives)
    guard_hits = sum(_candidate_detected(r, thresholds) for r in guards)
    neg_hits = sum(_candidate_detected(r, thresholds) for r in negatives)
    prominence = _separation_summary(rows, "max_peak_prominence_ratio")
    ac = _separation_summary(rows, "autocorrelation_peak_strength")

    clear_prominence = (
        prominence["positive_min"] is not None
        and prominence["guard_max"] is not None
        and prominence["positive_min"] > prominence["guard_max"] * 1.25
    )
    ac_helps = (
        ac["positive_min"] is not None
        and ac["guard_max"] is not None
        and ac["positive_min"] > ac["guard_max"] * 1.10
    )
    if pos_hits == len(positives) and guard_hits == 0 and neg_hits == 0 and clear_prominence and ac_helps:
        return "IMPLEMENT"
    if pos_hits == len(positives) and guard_hits == 0 and neg_hits == 0:
        return "POSTPONE"
    return "REJECT"


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "case_id",
        "group",
        "description",
        "path",
        "symmetric_peak_pair_count",
        "max_peak_prominence_ratio",
        "median_peak_prominence_ratio",
        "directional_energy_ratio",
        "spectral_entropy",
        "autocorrelation_peak_strength",
        "estimated_repeat_period_px",
        "periodic_energy_ratio",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_report(rows: list[dict], thresholds: dict[str, float]) -> str:
    verdict = _verdict(rows, thresholds)
    lines = [
        "Dataset Forge Periodic Frequency Noise Probe",
        "=" * 60,
        "Candidate: FFT symmetric peak analysis + autocorrelation confirmation",
        "",
        "Scope: research only; no analyzer, inspect, CLI, benchmark manifest, or cleanup changes.",
        "",
        "Recommended thresholds from this probe",
        "-" * 60,
    ]
    for key, value in thresholds.items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "Separation summary", "-" * 60])
    for metric in [
        "symmetric_peak_pair_count",
        "max_peak_prominence_ratio",
        "autocorrelation_peak_strength",
        "periodic_energy_ratio",
        "spectral_entropy",
    ]:
        summary = _separation_summary(rows, metric)
        lines.append(
            f"{metric:<34} positive_min={summary['positive_min']} "
            f"positive_median={summary['positive_median']} "
            f"guard_max={summary['guard_max']} negative_max={summary['negative_max']}"
        )

    lines.extend(["", "Case table", "-" * 60])
    header = (
        f"{'group':<9} {'case':<34} {'pairs':>5} {'peak':>9} "
        f"{'ac':>7} {'period':>8} {'energy':>8} {'entropy':>8} detected"
    )
    lines.append(header)
    for row in rows:
        detected = _candidate_detected(row, thresholds)
        lines.append(
            f"{row['group']:<9} {row['case_id']:<34} "
            f"{row['symmetric_peak_pair_count']:>5} "
            f"{row['max_peak_prominence_ratio']:>9.2f} "
            f"{row['autocorrelation_peak_strength']:>7.3f} "
            f"{row['estimated_repeat_period_px']:>8.2f} "
            f"{row['periodic_energy_ratio']:>8.4f} "
            f"{row['spectral_entropy']:>8.3f} {detected}"
        )

    lines.extend([
        "",
        "Verdict",
        "-" * 60,
        verdict,
        "",
        "Interpretation",
        "-" * 60,
    ])
    if verdict == "IMPLEMENT":
        lines.append(
            "Synthetic periodic positives separate from guard fixtures with the "
            "combined FFT/autocorrelation rule. This supports a first benchmark-backed slice."
        )
    elif verdict == "POSTPONE":
        lines.append(
            "The candidate thresholds classify this small fixture set, but the "
            "margin is not strong enough to justify implementation without more guards."
        )
    else:
        lines.append(
            "The candidate does not meet the acceptance bar. Positives do not "
            "separate cleanly from guard fixtures and/or autocorrelation does not "
            "improve precision enough."
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Research-only periodic frequency noise probe."
    )
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = _generate_probe_fixtures(output_dir) + _existing_fixture_cases()
    rows: list[dict] = []
    for case in cases:
        measurements = measure_periodicity(case.path)
        rows.append({
            "case_id": case.case_id,
            "group": case.group,
            "description": case.description,
            "path": str(case.path),
            **asdict(measurements),
        })

    thresholds = _recommend_thresholds(rows)
    payload = {
        "probe": "periodic_frequency_noise",
        "measurements": rows,
        "recommended_thresholds": thresholds,
        "verdict": _verdict(rows, thresholds),
    }
    json_path = output_dir / "probe_periodic_frequency_noise_results.json"
    csv_path = output_dir / "probe_periodic_frequency_noise_results.csv"
    report_path = output_dir / "probe_periodic_frequency_noise_report.txt"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_csv(rows, csv_path)
    report_text = _render_report(rows, thresholds)
    report_path.write_text(report_text, encoding="utf-8")

    print(report_text, end="")
    print(f"\nWrote: {json_path}")
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
