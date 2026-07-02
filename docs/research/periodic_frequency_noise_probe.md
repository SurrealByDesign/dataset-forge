# Periodic Frequency Noise Probe

Status: researched; not approved for implementation.

Probe script:

- `scripts/research/_probe_periodic_frequency_noise.py`

Probe outputs:

- `benchmarks/results/probe_periodic_frequency_noise/`
- Outputs are ignored and should not be committed.

## Candidate Tested

FFT symmetric peak analysis plus autocorrelation confirmation.

Measured fields:

- `symmetric_peak_pair_count`
- `max_peak_prominence_ratio`
- `median_peak_prominence_ratio`
- `directional_energy_ratio`
- `spectral_entropy`
- `autocorrelation_peak_strength`
- `estimated_repeat_period_px`
- `periodic_energy_ratio`

## Fixtures Tested

Positive synthetic cases:

- horizontal sinusoidal periodic contamination
- diagonal sinusoidal periodic contamination
- grid periodic contamination

Negative / normal cases:

- watercolor-like noise
- committed texture clean fixture

Guard cases:

- pencil/paper grain
- intentional stripes
- intentional checker pattern
- intentional plaid pattern
- committed texture-positive fixture
- committed crystalline fixture
- committed oversharpening/halo fixture
- committed high-frequency isolated bright speck fixture
- committed high-frequency isolated dark speck fixture

## Key Results

The synthetic sinusoidal positives produced strong spectral evidence, but the
same measurements also fired on intentional repeated patterns and an existing
crystalline fixture.

Important overlap:

| Case | Group | Peak ratio | Autocorrelation | Detected |
|---|---:|---:|---:|---|
| `periodic_sine_horizontal` | positive | 4890.22 | 0.996 | yes |
| `periodic_diagonal` | positive | 35596.66 | 0.983 | yes |
| `periodic_grid` | positive | 97.00 | 0.986 | no |
| `intentional_stripes` | guard | 46194964.00 | 0.996 | yes |
| `intentional_plaid` | guard | 2081516.88 | 0.960 | yes |
| `fixture_crystalline_medium` | guard | 34045.77 | 0.977 | yes |

Autocorrelation did not improve precision. Intentional stripes, checker/plaid
patterns, and crystalline structure can also produce strong autocorrelation.

## Decision

Reject FFT symmetric peak plus autocorrelation as a production analyzer signal
for now.

Reasons:

- Positive periodic fixtures do not cleanly separate from guard fixtures.
- Intentional repeated patterns produce stronger FFT peaks than synthetic
  periodic contamination.
- The crystalline fixture overlaps heavily with the candidate signal.
- Autocorrelation confirms repetition, but it does not distinguish unwanted
  periodic noise from legitimate repeated structure.
- The resulting detector would likely create broad false positives and violate
  Dataset Forge's "healthy images should be left alone" principle.

## Revisit Criteria

Revisit this analyzer only if a new discriminator can separate synthetic
periodic contamination from legitimate repeated content.

Required evidence before implementation:

- positives separate from intentional stripes/plaid/checker guards with clear
  numeric margin
- crystalline, oversharpening, texture, and high-frequency isolated fixtures do
  not trigger the periodic analyzer
- autocorrelation or another spatial validation improves precision rather than
  merely confirming repetition
- evidence remains explainable in an inspection report
- real labeled examples show a distinct artifact family not already covered by
  current analyzers
