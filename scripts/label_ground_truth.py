"""
Ground-truth labeling tool for Dataset Forge calibration.

Walks the dataset, shows each image's texture metrics from an existing
inspection report, and records a human label: ARTIFACT / CLEAN / UNCERTAIN.

Labels are written to ground_truth.json in the dataset folder.
The session is resumable — already-labeled images are skipped unless
--review is passed.

Usage
-----
    python scripts/label_ground_truth.py \\
        --dataset "C:/path/to/dataset" \\
        --report  "C:/path/to/inspect_output/inspection_report.json"

Options
-------
    --dataset     Path to the image folder (required).
    --report      Path to inspection_report.json (required).
    --output      Where to write ground_truth.json.
                  Default: <dataset>/ground_truth.json
    --review      Re-label already-labeled images as well.
    --recursive   Scan sub-folders recursively.
    --no-preview  Do not open images automatically (default: images open
                  in the system viewer before each prompt).

ground_truth.json schema
------------------------
{
    "schema": "dataset-forge/ground-truth/v1",
    "dataset_path": "<absolute path>",
    "report_path":  "<absolute path>",
    "labeled_by":   "human",
    "created_at":   "ISO timestamp",
    "updated_at":   "ISO timestamp",
    "labels": {
        "filename.png": {
            "label":  "ARTIFACT" | "CLEAN" | "UNCERTAIN",
            "notes":  "<optional free text>",
            "severity_from_report": "HIGH" | "MEDIUM" | "NONE" | null,
            "micro":  <float | null>,
            "z":      <float | null>,
            "smooth": <float | null>,
            "speck":  <float | null>,
            "labeled_at": "ISO timestamp"
        }
    }
}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dataset_forge.discovery import discover_images

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GROUND_TRUTH_SCHEMA = "dataset-forge/ground-truth/v1"
VALID_LABELS = ("ARTIFACT", "CLEAN", "UNCERTAIN")
LABEL_SHORTCUTS = {"a": "ARTIFACT", "c": "CLEAN", "u": "UNCERTAIN"}

# Sub-directory names that should never contain labeled images.
_EXCLUDED_DIRS = frozenset({"inspect_output", "_report", "output", "__pycache__"})


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_ground_truth(path: Path) -> dict:
    """Load an existing ground_truth.json or return a fresh skeleton."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == GROUND_TRUTH_SCHEMA:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema": GROUND_TRUTH_SCHEMA,
        "dataset_path": "",
        "report_path": "",
        "labeled_by": "human",
        "created_at": _now(),
        "updated_at": _now(),
        "labels": {},
    }


def _save_ground_truth(data: dict, path: Path) -> None:
    data["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_report(report_path: Path) -> dict:
    """Load inspection_report.json and return it."""
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected JSON shape in {report_path}")
    return raw


def _build_findings_index(report: dict) -> dict[str, dict]:
    """Map filename → finding dict for every flagged image in the report."""
    index: dict[str, dict] = {}
    for f in report.get("findings", []):
        name = Path(f.get("image_path", "")).name
        if name:
            index[name] = f
    return index


def _extract_metrics(finding: dict | None) -> dict:
    """Pull texture metrics out of a finding's evidence block."""
    if finding is None:
        return {"severity": None, "micro": None, "z": None, "smooth": None, "speck": None}
    ev = finding.get("evidence", {})
    return {
        "severity": finding.get("severity"),
        "micro":    ev.get("microtexture_density"),
        "z":        ev.get("z_score"),
        "smooth":   ev.get("watercolor_smoothness"),
        "speck":    ev.get("highlight_speck"),
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_SEV_MARKERS = {
    "HIGH":     "[ HIGH   ]",
    "MEDIUM":   "[ MEDIUM ]",
    "LOW":      "[ LOW    ]",
    "CRITICAL": "[CRITICAL]",
    None:       "[  clean ]",
}

_BAR = "-" * 62


def _fmt_float(v: float | None, width: int = 5, decimals: int = 1) -> str:
    if v is None:
        return " " * width + "  n/a"
    return f"{v:{width}.{decimals}f}"


def _print_image_header(
    idx: int,
    total: int,
    name: str,
    metrics: dict,
    existing_label: str | None,
) -> None:
    sev = metrics.get("severity")
    marker = _SEV_MARKERS.get(sev, "[       ]")
    print()
    print(_BAR)
    print(f"  [{idx}/{total}]  {name}")
    print(f"  {marker}  severity: {sev or 'none'}")

    micro  = metrics.get("micro")
    z      = metrics.get("z")
    smooth = metrics.get("smooth")
    speck  = metrics.get("speck")

    if micro is not None:
        print(
            f"  micro={_fmt_float(micro)}  "
            f"z={'+' if z and z >= 0 else ''}{_fmt_float(z, 5, 2)}  "
            f"smooth={_fmt_float(smooth)}  speck={_fmt_float(speck)}"
        )
    else:
        print("  (no texture metrics — image was not in findings; check report)")

    if existing_label:
        print(f"  Current label: {existing_label}")

    print(_BAR)


def _open_image(path: Path) -> None:
    """Open the image in the system default viewer. Best-effort; never raises."""
    try:
        if sys.platform == "win32":
            os.startfile(path)          # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception:
        pass    # preview is a convenience, never a requirement


def _prompt_label() -> tuple[str, str] | None:
    """Prompt for a label and optional note. Returns (label, note) or None to quit."""
    print("  Label:  [A] ARTIFACT   [C] CLEAN   [U] UNCERTAIN")
    print("  Other:  [S] skip   [Q] quit and save")
    while True:
        raw = input("  > ").strip().lower()
        if not raw:
            continue
        if raw == "q":
            return None
        if raw == "s":
            return "SKIP", ""
        label = LABEL_SHORTCUTS.get(raw) or raw.upper()
        if label in VALID_LABELS:
            note_raw = input("  Note (optional, Enter to skip): ").strip()
            return label, note_raw
        print(f"  Unrecognised: {raw!r}. Use A, C, U, S, or Q.")


# ---------------------------------------------------------------------------
# Core labeling session
# ---------------------------------------------------------------------------

def _is_excluded(path: Path, dataset_root: Path) -> bool:
    """Return True if the path is inside a known output subdirectory."""
    try:
        rel = path.relative_to(dataset_root)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] in _EXCLUDED_DIRS)


def run_labeling_session(
    dataset_path: Path,
    report_path: Path,
    output_path: Path,
    *,
    review: bool = False,
    recursive: bool = False,
    preview: bool = True,
) -> dict:
    """Run an interactive labeling session and return the final ground_truth dict.

    When preview=True (default) each image is opened in the system viewer
    before the prompt so the reviewer can see it while labeling.

    Designed to be testable: callers can monkey-patch ``input`` before calling,
    and pass preview=False to skip OS file-open calls during tests.
    """
    dataset_path = dataset_path.resolve()
    report_path  = report_path.resolve()
    output_path  = output_path.resolve()

    report = _load_report(report_path)
    findings_index = _build_findings_index(report)

    discovery = discover_images(dataset_path, recursive=recursive)
    all_images = [
        p for p in discovery.images
        if not _is_excluded(p, dataset_path)
    ]

    gt = _load_ground_truth(output_path)
    gt["dataset_path"] = str(dataset_path)
    gt["report_path"]  = str(report_path)

    existing_labels: dict[str, dict] = gt.setdefault("labels", {})

    to_label = [
        p for p in all_images
        if review or p.name not in existing_labels
    ]

    skipped_count   = len(all_images) - len(to_label)
    labeled_count   = 0
    total           = len(to_label)

    print()
    print("Dataset Forge — Ground Truth Labeling")
    print("======================================")
    print(f"Dataset:   {dataset_path}")
    print(f"Report:    {report_path}")
    print(f"Output:    {output_path}")
    print(f"Images:    {len(all_images)} total, {skipped_count} already labeled, "
          f"{total} to label")
    if review:
        print("Mode:      --review (re-labeling existing entries)")
    if not preview:
        print("Preview:   disabled (--no-preview)")
    print()
    print("Labels: A=ARTIFACT  C=CLEAN  U=UNCERTAIN  S=skip  Q=quit+save")

    if total == 0:
        print("\nNothing to label. Pass --review to re-label existing entries.")
        _save_ground_truth(gt, output_path)
        return gt

    for idx, image_path in enumerate(to_label, start=1):
        name = image_path.name
        finding = findings_index.get(name)
        metrics = _extract_metrics(finding)
        existing_label = existing_labels.get(name, {}).get("label")

        if preview:
            _open_image(image_path)

        _print_image_header(idx, total, name, metrics, existing_label)

        result = _prompt_label()

        if result is None:          # Q — quit and save
            print(f"\nSaving and quitting after {labeled_count} labels.")
            break

        label, note = result
        if label == "SKIP":
            continue

        existing_labels[name] = {
            "label":                label,
            "notes":                note,
            "severity_from_report": metrics.get("severity"),
            "micro":                metrics.get("micro"),
            "z":                    metrics.get("z"),
            "smooth":               metrics.get("smooth"),
            "speck":                metrics.get("speck"),
            "labeled_at":           _now(),
        }
        labeled_count += 1
        _save_ground_truth(gt, output_path)     # save after every label

    print()
    total_labeled = len(existing_labels)
    total_images  = len(all_images)
    print(f"Session complete: {labeled_count} labeled this session.")
    print(f"Total labeled: {total_labeled} / {total_images}")
    print(f"Ground truth written: {output_path}")
    _save_ground_truth(gt, output_path)
    return gt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Label dataset images as ARTIFACT / CLEAN / UNCERTAIN for "
            "TextureAnalyzer calibration."
        )
    )
    p.add_argument("--dataset",   type=Path, required=True,
                   help="Path to the image dataset folder.")
    p.add_argument("--report",    type=Path, required=True,
                   help="Path to inspection_report.json from dataset-forge inspect.")
    p.add_argument("--output",    type=Path, default=None,
                   help="Where to write ground_truth.json. "
                        "Default: <dataset>/ground_truth.json")
    p.add_argument("--review",     action="store_true",
                   help="Re-label already-labeled images.")
    p.add_argument("--recursive",  action="store_true",
                   help="Search dataset sub-folders recursively.")
    p.add_argument("--no-preview", action="store_true",
                   help="Do not open images automatically before each prompt.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    dataset_path = args.dataset.expanduser().resolve()
    report_path  = args.report.expanduser().resolve()
    output_path  = (
        args.output.expanduser().resolve()
        if args.output
        else dataset_path / "ground_truth.json"
    )

    if not dataset_path.is_dir():
        print(f"ERROR: Dataset directory not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)
    if not report_path.exists():
        print(f"ERROR: Report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    run_labeling_session(
        dataset_path,
        report_path,
        output_path,
        review=args.review,
        recursive=args.recursive,
        preview=not args.no_preview,
    )


if __name__ == "__main__":
    main()
