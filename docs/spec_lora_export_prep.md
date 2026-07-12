# Spec: LoRA Export Prep

> **Historical design record. Not on the current product roadmap.** Dataset
> Forge v1.9.3 does not export datasets, copy captions for training, or create
> trainer-ready folders.

**Status:** Specification — not yet implemented.

**Stage in pipeline:** Final stage after analysis and cleanup. Consumes selected
and cleaned images; produces a self-contained export folder ready to hand to a
LoRA trainer.

---

## Purpose

Convert selected/cleaned images into a trainer-ready export folder. The export
must be geometrically safe (no stretching, no unexpected resolution changes),
traceable (manifest records every source), and non-destructive (originals are
never touched). Caption file support is included as an extension point even if
captions are not generated in this phase.

---

## Core Requirements

1. **Never modify originals.** All writes go to a new export folder. The source
   images are read-only inputs.

2. **Preserve aspect ratio.** No image may be stretched or squeezed. Width-to-
   height ratio from the source is always maintained in the exported copy.

3. **Optional square padding.** When `pad_to_square: true`, images are placed
   on a square canvas using letterboxing. The canvas size is `max(width, height)`
   rounded up to the nearest multiple of `canvas_multiple` (default 64). Pad
   color is configurable; default is `(255, 255, 255)` (white) for painted
   artwork, with `(0, 0, 0)` as the other common option.

4. **No stretching under any circumstances.** If padding is disabled and the
   image is not square, the image is exported at its natural dimensions. Trainers
   that require square input must use padding.

5. **Clean export folder.** Only exported images and their associated files
   (captions, manifest) go in the export folder. No analysis reports, no
   thumbnails, no intermediates.

6. **`export_manifest.json` always written.** Every export produces a manifest
   that records: export timestamp, source path, output path, original dimensions,
   exported dimensions, pad applied, format, and any caption file path.

7. **Caption file support (extension point).** If a `.txt` sidecar exists
   alongside the source image (matching stem), it is copied to the export folder
   alongside the exported image. The manifest records `caption_file` for each
   image. Caption generation is not part of this spec.

8. **Format control.** Output format is configurable: `PNG`, `JPEG`, or `WEBP`.
   Default is `PNG` for lossless archival export. JPEG quality is a parameter
   (default 95). WEBP lossless is the recommended alternative.

9. **Deterministic output.** Same inputs and same config always produce the
   same export. No timestamps in filenames, no random suffixes.

---

## Configuration

All parameters live in an `ExportConfig` dataclass (or equivalent JSON/YAML
block). Reasonable defaults apply; no parameter is required.

```python
@dataclass
class ExportConfig:
    pad_to_square: bool = False
    canvas_multiple: int = 64        # exported size rounded to nearest multiple
    pad_color: tuple[int,int,int] = (255, 255, 255)
    output_format: str = "PNG"       # "PNG" | "JPEG" | "WEBP"
    jpeg_quality: int = 95
    max_dimension: int | None = None # optional cap on longest edge; preserves AR
    copy_captions: bool = True
    overwrite: bool = False          # abort if export folder already exists
```

---

## `export_manifest.json` Schema

Written to the root of the export folder.

```json
{
  "version": 1,
  "exported_at": "2026-06-16T12:00:00Z",
  "config": {
    "pad_to_square": false,
    "canvas_multiple": 64,
    "pad_color": [255, 255, 255],
    "output_format": "PNG",
    "max_dimension": null,
    "copy_captions": true
  },
  "images": [
    {
      "source_path": "/abs/path/to/source/image.jpg",
      "export_filename": "image.png",
      "original_size": [1024, 768],
      "exported_size": [1024, 768],
      "pad_applied": false,
      "canvas_size": null,
      "caption_file": null,
      "status": "ok",
      "error": null
    }
  ],
  "summary": {
    "total": 100,
    "exported": 98,
    "skipped": 0,
    "errors": 2,
    "padded": 0
  }
}
```

`status` values: `"ok"`, `"skipped"` (already exists, overwrite=False),
`"error"`.

---

## Export Folder Layout

```
export/
├── export_manifest.json
├── image_001.png
├── image_001.txt          ← caption sidecar (if copy_captions=True and exists)
├── image_002.png
└── ...
```

Filenames in the export folder match the source stem exactly, with only the
extension changed to match `output_format`. If two sources share a stem (from
different directories), the second gets a numeric suffix (`image_001_2.png`).
The manifest records the final filename used.

---

## Geometry Rules

These rules are absolute. They may not be relaxed by configuration.

```
exported_width / exported_height == source_width / source_height
```

**No padding (default):**
- If `max_dimension` is set and the image exceeds it: resize so the longest
  edge equals `max_dimension`, shortest edge scaled proportionally, both rounded
  to integers. If a `canvas_multiple` is set, exported size is further rounded
  down to the nearest multiple (never up — up would change the ratio).
- If `max_dimension` is None: export at original dimensions, no resize.

**With padding (`pad_to_square: True`):**
- Compute `canvas = max(width, height)` after any `max_dimension` resize.
- If `canvas_multiple` is set, round `canvas` up to the next multiple.
- Create a `canvas × canvas` image filled with `pad_color`.
- Paste the image centered (floor division for offset, so top-left bias on
  odd remainders).
- The pasted image is never rescaled beyond the `max_dimension` step above.

---

## What This Stage Does Not Do

- Does not analyze images for quality or artifacts.
- Does not apply cleanup filters.
- Does not generate captions.
- Does not validate that images are suitable for training (that is the Decision
  Engine's job upstream).
- Does not rename images for trainer-specific naming conventions (e.g., `N_tag`
  prefix for Kohya). That is a separate formatting step.
- Does not remove duplicate images. Deduplication must happen upstream.
- Does not modify EXIF or embed metadata.

---

## Implementation Location

| Component | Path |
|---|---|
| ExportConfig dataclass | `src/dataset_forge/exporters/lora.py` |
| `export_lora_dataset()` function | `src/dataset_forge/exporters/lora.py` |
| CLI subcommand | `src/dataset_forge/cli.py` — `lora-export` |
| Integration test | `tests/exporters/test_lora_export.py` |

The `exporters/` package already exists (`src/dataset_forge/exporters/`).
`lora.py` is a new file within it.

---

## CLI Interface (proposed)

```
dataset-forge lora-export \
  --input  /path/to/selected_images/ \
  --output /path/to/export/ \
  [--pad-to-square] \
  [--canvas-multiple 64] \
  [--pad-color 255,255,255] \
  [--format PNG|JPEG|WEBP] \
  [--jpeg-quality 95] \
  [--max-dimension 1024] \
  [--no-captions] \
  [--overwrite]
```

`--input` may point to a folder or to a previously written
`export_manifest.json` (for re-exporting a prior selection).

---

## Acceptance Criteria

An implementation passes when:

1. Export folder contains only exported images, caption sidecars, and the
   manifest. No other files.
2. `export_manifest.json` is valid JSON matching the schema above.
3. No source image has been modified (verified by comparing file mtimes and
   checksums before and after).
4. All exported images have the correct aspect ratio:
   `abs(out_w / out_h - src_w / src_h) < 0.001`
5. Padded images have equal width and height. Non-padded images match source
   dimensions (after any max_dimension resize).
6. Running the same export twice with `overwrite=False` does not overwrite and
   reports `skipped` in the manifest.
7. Caption sidecars that exist at source are copied; those that do not exist
   are silently skipped (no error).
8. An image that cannot be opened is recorded in the manifest with
   `status: "error"` and does not abort the export of remaining images.

---

## Open Questions (to resolve before implementation)

1. **Filename policy when sources come from multiple directories.** Current
   proposal: stem collision gets `_2`, `_3` suffix. Alternative: use a flat
   serial number (`000001.png`). Serial numbers are friendlier for trainers that
   sort by filename but lose the original name.

2. **Should `max_dimension` round to `canvas_multiple` before or after the
   aspect-ratio resize?** Recommended: resize first, then round. Rounding before
   changes the effective cap.

3. **Default `pad_color` for dark/anime-lineart images.** White makes sense for
   watercolor/pencil. Black may be better for lineart on a dark canvas. Consider
   a style-aware default in the future, or expose `--pad-color` clearly in docs.

4. **Manifest vs. per-image sidecar JSON.** Current spec: single manifest.
   Some trainers expect a `.json` sidecar per image. Could add
   `write_per_image_json: bool = False` as a future flag.
