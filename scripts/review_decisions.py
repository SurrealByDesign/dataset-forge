"""
Review Dataset Forge decisions against human judgment.

For each image, shows the analyzer's decision (FINDING or CLEAN), the
severity, and available texture metrics, then asks the reviewer whether
they agree with it.

Reviews are saved to decision_review.json in the dataset folder.
The session is resumable — already-reviewed images are skipped unless
--review is passed.

Usage
-----
    python scripts/review_decisions.py \\
        --dataset "C:/path/to/dataset" \\
        --report  "C:/path/to/inspect_output/inspection_report.json"

Options
-------
    --dataset     Path to the image folder (required).
    --report      Path to inspection_report.json (required).
    --output      Where to write decision_review.json.
                  Default: <dataset>/decision_review.json
    --review      Re-review already-reviewed images.
    --recursive   Scan sub-folders recursively.
    --no-preview  Do not open images automatically (default: images open
                  in the system viewer before each prompt).

decision_review.json schema
---------------------------
{
    "schema": "dataset-forge/decision-review/v1",
    "dataset_path": "<absolute path>",
    "report_path":  "<absolute path>",
    "reviewed_by":  "human",
    "created_at":   "ISO timestamp",
    "updated_at":   "ISO timestamp",
    "reviews": {
        "filename.png": {
            "review":      "AGREE" | "DISAGREE" | "UNSURE",
            "notes":       "<optional free text>",
            "df_decision": "FINDING" | "CLEAN",
            "severity":    "HIGH" | "MEDIUM" | "CRITICAL" | null,
            "micro":       <float | null>,
            "z":           <float | null>,
            "smooth":      <float | null>,
            "speck":       <float | null>,
            "reviewed_at": "ISO timestamp"
        }
    }
}
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dataset_forge.discovery import discover_images

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DECISION_REVIEW_SCHEMA = "dataset-forge/decision-review/v1"
VALID_REVIEWS = ("AGREE", "DISAGREE", "UNSURE")
REVIEW_SHORTCUTS = {"a": "AGREE", "d": "DISAGREE", "u": "UNSURE"}

_EXCLUDED_DIRS = frozenset({"inspect_output", "_report", "output", "__pycache__"})


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_review_file(path: Path) -> dict:
    """Load an existing decision_review.json or return a fresh skeleton."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == DECISION_REVIEW_SCHEMA:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema": DECISION_REVIEW_SCHEMA,
        "dataset_path": "",
        "report_path": "",
        "reviewed_by": "human",
        "created_at": _now(),
        "updated_at": _now(),
        "reviews": {},
    }


def _save_review_file(data: dict, path: Path) -> None:
    data["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_report(report_path: Path) -> dict:
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected JSON shape in {report_path}")
    return raw


def _build_findings_index(report: dict) -> dict[str, dict]:
    """Map filename → finding dict for every flagged image."""
    index: dict[str, dict] = {}
    for f in report.get("findings", []):
        name = Path(f.get("image_path", "")).name
        if name:
            index[name] = f
    return index


def _extract_metrics(finding: dict | None) -> dict:
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
    df_decision: str,
    metrics: dict,
    existing_review: str | None,
) -> None:
    sev = metrics.get("severity")
    marker = _SEV_MARKERS.get(sev, "[       ]")
    decision_tag = f"FINDING  {marker}" if df_decision == "FINDING" else "CLEAN    [  ----  ]"

    print()
    print(_BAR)
    print(f"  [{idx}/{total}]  {name}")
    print(f"  DF decision: {decision_tag}  severity: {sev or 'none'}")

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
        print("  (no texture metrics)")

    if existing_review:
        print(f"  Current review: {existing_review}")

    print(_BAR)


def _open_image(path: Path) -> Callable[[], None] | None:
    """Open image in a tkinter preview window in a background thread.

    Returns a closer callable that dismisses the window, or None on failure.
    Using tkinter (instead of os.startfile) lets us close the window
    programmatically so the desktop doesn't flood with viewer windows.
    """
    try:
        import tkinter as tk
        from PIL import Image, ImageTk

        close_event = threading.Event()

        def _run() -> None:
            try:
                root = tk.Tk()
                root.title(path.name)
                root.configure(bg="black")
                root.attributes("-topmost", True)

                img = Image.open(path)
                img.thumbnail((900, 700))
                photo = ImageTk.PhotoImage(img)
                tk.Label(root, image=photo, bg="black").pack()

                def _poll() -> None:
                    if close_event.is_set():
                        root.destroy()
                    else:
                        root.after(50, _poll)

                root.after(50, _poll)
                root.mainloop()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
        return close_event.set

    except Exception:
        return None


def _prompt_review() -> tuple[str, str] | None:
    """Prompt for a review decision. Returns (review, note) or None to quit."""
    print("  Review:  [A] agree   [D] disagree   [U] unsure")
    print("  Other:   [S] skip    [Q] quit and save")
    while True:
        raw = input("  > ").strip().lower()
        if not raw:
            continue
        if raw == "q":
            return None
        if raw == "s":
            return "SKIP", ""
        review = REVIEW_SHORTCUTS.get(raw) or raw.upper()
        if review in VALID_REVIEWS:
            note_raw = input("  Note (optional, Enter to skip): ").strip()
            return review, note_raw
        print(f"  Unrecognised: {raw!r}. Use A, D, U, S, or Q.")


# ---------------------------------------------------------------------------
# Exclusion
# ---------------------------------------------------------------------------

def _is_excluded(path: Path, dataset_root: Path) -> bool:
    try:
        rel = path.relative_to(dataset_root)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] in _EXCLUDED_DIRS)


# ---------------------------------------------------------------------------
# Core review session
# ---------------------------------------------------------------------------

def run_review_session(
    dataset_path: Path,
    report_path: Path,
    output_path: Path,
    *,
    review: bool = False,
    recursive: bool = False,
    preview: bool = True,
) -> dict:
    """Run an interactive decision-review session and return the final data dict.

    Designed to be testable: patch ``builtins.input`` before calling, and
    pass preview=False to suppress OS file-open calls during tests.
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

    data = _load_review_file(output_path)
    data["dataset_path"] = str(dataset_path)
    data["report_path"]  = str(report_path)

    existing_reviews: dict[str, dict] = data.setdefault("reviews", {})

    to_review = [
        p for p in all_images
        if review or p.name not in existing_reviews
    ]

    skipped_count  = len(all_images) - len(to_review)
    reviewed_count = 0
    total          = len(to_review)

    print()
    print("Dataset Forge — Decision Review")
    print("================================")
    print(f"Dataset:   {dataset_path}")
    print(f"Report:    {report_path}")
    print(f"Output:    {output_path}")
    print(f"Images:    {len(all_images)} total, {skipped_count} already reviewed, "
          f"{total} to review")
    if review:
        print("Mode:      --review (re-reviewing existing entries)")
    if not preview:
        print("Preview:   disabled (--no-preview)")
    print()
    print("Review: A=agree  D=disagree  U=unsure  S=skip  Q=quit+save")

    if total == 0:
        print("\nNothing to review. Pass --review to re-examine existing entries.")
        _save_review_file(data, output_path)
        return data

    for idx, image_path in enumerate(to_review, start=1):
        name = image_path.name
        finding = findings_index.get(name)
        metrics = _extract_metrics(finding)
        df_decision = "FINDING" if finding is not None else "CLEAN"
        existing_review = existing_reviews.get(name, {}).get("review")

        closer = _open_image(image_path) if preview else None

        _print_image_header(idx, total, name, df_decision, metrics, existing_review)

        result = _prompt_review()

        if closer:
            closer()

        if result is None:
            print(f"\nSaving and quitting after {reviewed_count} reviews.")
            break

        rev, note = result
        if rev == "SKIP":
            continue

        existing_reviews[name] = {
            "review":      rev,
            "notes":       note,
            "df_decision": df_decision,
            "severity":    metrics.get("severity"),
            "micro":       metrics.get("micro"),
            "z":           metrics.get("z"),
            "smooth":      metrics.get("smooth"),
            "speck":       metrics.get("speck"),
            "reviewed_at": _now(),
        }
        reviewed_count += 1
        _save_review_file(data, output_path)

    print()
    total_reviewed = len(existing_reviews)
    total_images   = len(all_images)
    print(f"Session complete: {reviewed_count} reviewed this session.")
    print(f"Total reviewed: {total_reviewed} / {total_images}")
    print(f"Decision review written: {output_path}")
    _save_review_file(data, output_path)
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Review Dataset Forge inspection decisions as AGREE / DISAGREE / UNSURE."
        )
    )
    p.add_argument("--dataset",    type=Path, required=True,
                   help="Path to the image dataset folder.")
    p.add_argument("--report",     type=Path, required=True,
                   help="Path to inspection_report.json from dataset-forge inspect.")
    p.add_argument("--output",     type=Path, default=None,
                   help="Where to write decision_review.json. "
                        "Default: <dataset>/decision_review.json")
    p.add_argument("--review",     action="store_true",
                   help="Re-review already-reviewed images.")
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
        else dataset_path / "decision_review.json"
    )

    if not dataset_path.is_dir():
        print(f"ERROR: Dataset directory not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)
    if not report_path.exists():
        print(f"ERROR: Report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    run_review_session(
        dataset_path,
        report_path,
        output_path,
        review=args.review,
        recursive=args.recursive,
        preview=not args.no_preview,
    )


if __name__ == "__main__":
    main()
