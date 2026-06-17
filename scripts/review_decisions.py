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
            "category":    "<primary finding category>" | null,
            "severity":    "HIGH" | "MEDIUM" | "CRITICAL" | null,
            "micro":       <float | null>,
            "z":           <float | null>,
            "smooth":      <float | null>,
            "speck":       <float | null>,
            "grain":       <float | null>,   # pencil_grain_score if crystalline finding present
            "reviewed_at": "ISO timestamp"
        }
    }
}
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

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
    """Map filename → primary finding dict (first finding) for flagged images.

    Keeps the first finding per image so that the TextureAnalyzer finding is
    not silently overwritten when multiple analyzers both flag the same image.
    """
    index: dict[str, dict] = {}
    for f in report.get("findings", []):
        name = Path(f.get("image_path", "")).name
        if name and name not in index:
            index[name] = f
    return index


def _build_crystalline_index(report: dict) -> dict[str, dict]:
    """Map filename → crystalline faceting finding for images that have one."""
    index: dict[str, dict] = {}
    for f in report.get("findings", []):
        name = Path(f.get("image_path", "")).name
        if name and f.get("category") == "artifact.crystalline_faceting":
            index[name] = f
    return index


def _extract_metrics(finding: dict | None) -> dict:
    if finding is None:
        return {
            "category": None,
            "severity": None,
            "micro": None,
            "z": None,
            "smooth": None,
            "speck": None,
        }
    ev = finding.get("evidence", {})
    return {
        "category": finding.get("category"),
        "severity": finding.get("severity"),
        "micro":    ev.get("microtexture_density"),
        "z":        ev.get("z_score"),
        "smooth":   ev.get("watercolor_smoothness"),
        "speck":    ev.get("highlight_speck"),
    }


def _extract_crystalline_evidence(finding: dict | None) -> dict | None:
    """Extract pencil-grain evidence from a crystalline finding.

    Returns a dict with 'grain', 'smooth', 'micro' keys, or None if the
    finding is None.  All three values may themselves be None if the
    evidence dict is incomplete.
    """
    if finding is None:
        return None
    ev = finding.get("evidence", {})
    return {
        "grain":  ev.get("pencil_grain_score"),
        "smooth": ev.get("watercolor_smoothness_score"),
        "micro":  ev.get("microtexture_density_score"),
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
    *,
    crystalline: dict | None = None,
) -> None:
    sev      = metrics.get("severity")
    category = metrics.get("category")
    marker   = _SEV_MARKERS.get(sev, "[       ]")

    if df_decision == "FINDING":
        decision_tag = f"FINDING  {marker}"
        cat_str = f"  category: {category}" if category else ""
    else:
        decision_tag = "CLEAN    [  ----  ]"
        cat_str = ""

    print()
    print(_BAR)
    print(f"  [{idx}/{total}]  {name}")
    print(f"  DF decision: {decision_tag}  severity: {sev or 'none'}{cat_str}")

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

    if crystalline is not None:
        grain  = crystalline.get("grain")
        csmooth = crystalline.get("smooth")
        cmicro  = crystalline.get("micro")
        print(
            f"  Crystalline:  grain={_fmt_float(grain)}  "
            f"smooth={_fmt_float(csmooth)}  "
            f"micro={_fmt_float(cmicro)}  "
            f"[uncalibrated]"
        )

    if existing_review:
        print(f"  Current review: {existing_review}")

    print(_BAR)


class _PreviewWindow:
    """Single persistent tkinter window reused across all images in a session.

    Creates one Tk root in a background thread and updates its image via a
    queue. This avoids the fatal limitation of creating multiple Tk() instances
    (only the first succeeds; subsequent ones fail silently).

    Usage::
        win = _PreviewWindow()   # starts the window thread
        win.show(path)           # display an image
        win.hide()               # blank/withdraw between images
        win.close()              # destroy and join thread
    """

    _HIDE = object()
    _QUIT = object()

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._ok = False
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=3.0)

    def _run(self) -> None:
        try:
            import tkinter as tk
            from PIL import Image, ImageTk

            root = tk.Tk()
            root.title("Dataset Forge — Preview")
            root.configure(bg="black")
            root.attributes("-topmost", True)
            root.withdraw()

            canvas = tk.Canvas(root, bg="black", width=900, height=700,
                               highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            hint = tk.Label(root, text="scroll to zoom  •  drag to pan",
                            bg="black", fg="#555555", font=("Helvetica", 9))
            hint.pack(pady=(0, 4))

            _ref:       list = [None]   # ImageTk reference (prevent GC)
            _orig:      list = [None]   # original PIL Image for re-render
            _scale:     list = [1.0]
            _img_id:    list = [None]

            def _render() -> None:
                if _orig[0] is None:
                    return
                w = max(1, int(_orig[0].width  * _scale[0]))
                h = max(1, int(_orig[0].height * _scale[0]))
                resized = _orig[0].resize((w, h), Image.LANCZOS)
                _ref[0] = ImageTk.PhotoImage(resized)
                if _img_id[0] is None:
                    _img_id[0] = canvas.create_image(0, 0, anchor="nw",
                                                     image=_ref[0])
                else:
                    canvas.itemconfigure(_img_id[0], image=_ref[0])
                canvas.configure(scrollregion=canvas.bbox("all"))

            def _on_wheel(event: tk.Event) -> None:
                factor = 1.15 if event.delta > 0 else (1.0 / 1.15)
                _scale[0] = max(0.1, min(8.0, _scale[0] * factor))
                _render()

            canvas.bind("<MouseWheel>", _on_wheel)
            canvas.bind("<ButtonPress-1>",
                        lambda e: canvas.scan_mark(e.x, e.y))
            canvas.bind("<B1-Motion>",
                        lambda e: canvas.scan_dragto(e.x, e.y, gain=1))

            self._ok = True
            self._ready.set()

            def _poll() -> None:
                try:
                    while True:
                        msg = self._q.get_nowait()
                        if msg is self._QUIT:
                            root.destroy()
                            return
                        if msg is self._HIDE:
                            root.withdraw()
                        else:
                            img = Image.open(msg)
                            # fit to canvas on first load; preserve original for zoom
                            fit = min(900 / img.width, 700 / img.height, 1.0)
                            _orig[0]  = img
                            _scale[0] = fit
                            canvas.xview_moveto(0)
                            canvas.yview_moveto(0)
                            _render()
                            root.title(f"{Path(msg).name}   (scroll=zoom  drag=pan)")
                            root.deiconify()
                            root.lift()
                except queue.Empty:
                    pass
                root.after(50, _poll)

            root.after(0, _poll)
            root.mainloop()
        except Exception:
            self._ready.set()

    def show(self, path: Path) -> None:
        if self._ok:
            self._q.put(path)

    def hide(self) -> None:
        if self._ok:
            self._q.put(self._HIDE)

    def close(self) -> None:
        if self._ok:
            self._q.put(self._QUIT)


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
    focus: set[str] | None = None,
) -> dict:
    """Run an interactive decision-review session and return the final data dict.

    focus: if provided, only images whose filename is in this set are presented.
           Existing reviews for those images are always overwritten (implies --review
           for the focused subset).

    Designed to be testable: patch ``builtins.input`` before calling, and
    pass preview=False to suppress OS file-open calls during tests.
    """
    dataset_path = dataset_path.resolve()
    report_path  = report_path.resolve()
    output_path  = output_path.resolve()

    report = _load_report(report_path)
    findings_index     = _build_findings_index(report)
    crystalline_index  = _build_crystalline_index(report)

    discovery = discover_images(dataset_path, recursive=recursive)
    all_images = [
        p for p in discovery.images
        if not _is_excluded(p, dataset_path)
    ]

    data = _load_review_file(output_path)
    data["dataset_path"] = str(dataset_path)
    data["report_path"]  = str(report_path)

    existing_reviews: dict[str, dict] = data.setdefault("reviews", {})

    if focus is not None:
        # Only present the focused subset; always re-present even if already reviewed
        to_review = [p for p in all_images if p.name in focus]
        mode_label = f"--focus ({len(to_review)} images)"
    else:
        to_review = [
            p for p in all_images
            if review or p.name not in existing_reviews
        ]
        mode_label = "--review (re-reviewing existing entries)" if review else None

    skipped_count  = len(all_images) - len(to_review)
    reviewed_count = 0
    total          = len(to_review)

    print()
    print("Dataset Forge — Decision Review")
    print("================================")
    print(f"Dataset:   {dataset_path}")
    print(f"Report:    {report_path}")
    print(f"Output:    {output_path}")
    if focus is not None:
        print(f"Focus:     {total} specific images")
    else:
        print(f"Images:    {len(all_images)} total, {skipped_count} already reviewed, "
              f"{total} to review")
    if mode_label:
        print(f"Mode:      {mode_label}")
    if not preview:
        print("Preview:   disabled (--no-preview)")
    print()
    print("Review: A=agree  D=disagree  U=unsure  S=skip  Q=quit+save")

    if total == 0:
        if focus is not None:
            print("\nNo focused images found in dataset. Check filenames.")
        else:
            print("\nNothing to review. Pass --review to re-examine existing entries.")
        _save_review_file(data, output_path)
        return data

    win = _PreviewWindow() if preview else None

    for idx, image_path in enumerate(to_review, start=1):
        name = image_path.name
        finding           = findings_index.get(name)
        cryst_finding     = crystalline_index.get(name)
        metrics           = _extract_metrics(finding)
        cryst_ev          = _extract_crystalline_evidence(cryst_finding)
        df_decision       = "FINDING" if finding is not None else "CLEAN"
        existing_review   = existing_reviews.get(name, {}).get("review")

        if win:
            win.show(image_path)

        _print_image_header(
            idx, total, name, df_decision, metrics, existing_review,
            crystalline=cryst_ev,
        )

        result = _prompt_review()

        if win:
            win.hide()

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
            "category":    metrics.get("category"),
            "severity":    metrics.get("severity"),
            "micro":       metrics.get("micro"),
            "z":           metrics.get("z"),
            "smooth":      metrics.get("smooth"),
            "speck":       metrics.get("speck"),
            "grain":       cryst_ev.get("grain") if cryst_ev else None,
            "reviewed_at": _now(),
        }
        reviewed_count += 1
        _save_review_file(data, output_path)

    if win:
        win.close()

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
    p.add_argument("--focus", type=str, default=None,
                   help="Comma-separated list of filenames to re-review, or path "
                        "to a text file with one filename per line. Overrides "
                        "--review for the focused subset only.")
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

    focus: set[str] | None = None
    if args.focus:
        focus_arg = args.focus.strip()
        focus_path = Path(focus_arg)
        if focus_path.exists():
            focus = {l.strip() for l in focus_path.read_text(encoding="utf-8").splitlines() if l.strip()}
        else:
            focus = {f.strip() for f in focus_arg.split(",") if f.strip()}

    run_review_session(
        dataset_path,
        report_path,
        output_path,
        review=args.review,
        recursive=args.recursive,
        preview=not args.no_preview,
        focus=focus,
    )


if __name__ == "__main__":
    main()
