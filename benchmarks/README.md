# Private Benchmark Images

This folder is for local, private benchmark material. Benchmark images are
private and local by default, ignored by Git, and should not be committed.

Users provide their own clean reference image in:

```text
benchmarks/reference/
```

Generate deterministic synthetic defect variants with:

```powershell
python scripts/generate_benchmark_defects.py `
  --input benchmarks/reference/my_clean_reference.png `
  --output benchmarks/synthetic_defects `
  --seed 1234 `
  --strength medium
```

The generator writes a normalized reference copy, five synthetic defect
images, and `benchmark_manifest.json` into
`benchmarks/synthetic_defects/`. It never modifies the input image.

This benchmark system tests cleanup quality across Dataset Forge workflows. It
is not limited to LoRA dataset preparation.

Available strengths are `light`, `medium`, and `strong`. Reusing the same
input pixels, seed, and strength produces the same generated image pixels.
The manifest timestamp records when the benchmark set was created.
