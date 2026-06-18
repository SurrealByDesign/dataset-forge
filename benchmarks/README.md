# Dataset Forge Benchmarks

This directory holds benchmark manifests, generated synthetic defect images,
and (locally only) private real-sample images. Most files here are gitignored.

---

## Manifests

| File | Tracked in git | Purpose |
|---|---|---|
| `benchmark_manifest.json` | Yes | Public suite — synthetic cases only |
| `local_benchmark_manifest.json` | **No** | Private suite — real dataset samples |

### Public manifest (`benchmark_manifest.json`)

Contains only cases whose images can be generated from code. All images are
still gitignored (they must be generated before running), but no private
filenames or dataset details appear in the manifest itself.

Run it after generating the synthetic defects:

```
python scripts/generate_benchmark_defects.py
python scripts/run_benchmarks.py
```

### Local manifest (`local_benchmark_manifest.json`)

Contains cases that reference private real images from a local training
dataset. This file is gitignored and must never be committed. It exists
alongside the public manifest for full local calibration.

To run the local suite:

```
python scripts/run_benchmarks.py --manifest benchmarks/local_benchmark_manifest.json
```

If any referenced image is missing the runner skips that case (exit 0 still
returned if no non-skipped case fails). This means partial runs are safe.

---

## Synthetic defects

All files in `benchmarks/synthetic_defects/` are gitignored except
`.gitkeep`. Generate them with:

```
python scripts/generate_benchmark_defects.py
```

The generator requires a clean reference image placed in
`benchmarks/reference/`. It writes deterministic PNG variants into
`benchmarks/synthetic_defects/`. Probe scores for each generated image are
recorded in the public manifest's `source_description` fields.

---

## Real samples (`benchmarks/real_samples/`)

All image files in this directory are gitignored. Place private calibration
images here manually. Filenames and expected scores are documented in
`local_benchmark_manifest.json` (also gitignored).

Real samples serve purposes that synthetics cannot:
- Confirming recall against actual GPT-generated image artifacts
- Validating severity tier assignments against human-reviewed labels
- Documenting known false-positive patterns

---

## Results

`benchmarks/results/` is gitignored. Each run of `run_benchmarks.py` writes
`benchmark_results.json` and `benchmark_results.txt` there.
