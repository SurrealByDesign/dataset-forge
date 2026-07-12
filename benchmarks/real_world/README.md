# Real-World Validation Corpus

This directory defines the optional real-world validation corpus framework.

The corpus is methodology only for now. It does not add analyzers, change thresholds,
modify images, expose cleanup, implement repair planning, or change `inspect` output.

## What Is Committed

- `manifest.json` describes public and optional private validation groups.
- `labels/placeholder_labels.json` proves compatibility with Calibration Evidence labels.
- `expected/placeholder_expected.json` documents expected placeholder validation behavior.

The committed public group intentionally uses existing synthetic fixtures as a wiring
placeholder. It is not real-world calibration evidence and must not be used to claim
real-world analyzer reliability.

## Private / Local Data

Local real-world datasets belong under `benchmarks/real_world/private/`, which is
gitignored. Private fixtures may include local LoRA/image dataset examples, labels,
review decisions, and expected validation dossiers.

Fresh clones must pass without private files. Missing private fixtures are skipped
by the corpus validator when they are marked optional/private in the manifest.

## Rules For Public Fixtures

Committed real-world fixtures must be legally safe and reproducible:

- public-domain, CC0, or otherwise explicitly redistributable
- small enough for the repository
- stable source and license recorded in the manifest
- labeled with `dataset-forge/calibration-labels/v1`
- expected outputs documented without requiring private files

Do not commit copyrighted, private, user-owned, or unclear-license dataset images.

## Validation Role

The corpus is the evidence gate before public validation workflows and any future
action recommendations. It supports measuring existing analyzer reliability; it does
not recommend cleanup, repair, regeneration, deletion, or export.
