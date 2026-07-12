# scripts/research/

Internal historical and current research probes. They are not part of the
public API, do not define the current roadmap, and are not required for normal
use. Some early reports predate analyzers that were later implemented with
different methods and tests.

## Contents

| Script | Purpose | Recommendation |
|---|---|---|
| `_probe_oversharpening.py` | Probes edge-ringing and halo signals on a private dataset | DEFER -- no reliable signal found |
| `_probe_speck_glitter.py` | Probes isolated bright-pixel signals on a private dataset | DEFER -- signal inverts; crystalline already covers it |

## Running

Both scripts require the anthropomorph dataset locally. They write output to
`benchmarks/results/probe_*/` (gitignored).

```
uv run python scripts/research/_probe_oversharpening.py
uv run python scripts/research/_probe_speck_glitter.py
```

Research reports are in `benchmarks/results/` (gitignored).
