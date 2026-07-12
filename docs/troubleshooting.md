# Troubleshooting

## `inspect` Finds No Images

Confirm the folder exists and contains supported image formats. Add
`--recursive` when images are inside subfolders.

## Review Desk Reports Missing Sidecars

Run `dataset-forge inspect` first and pass the generated inspect-output folder,
not the source dataset folder, to `dataset-forge review`.

## The Browser Does Not Open

Copy the localhost URL printed by the command into a normal browser. If the
port is in use, choose another:

```powershell
uv run dataset-forge review <inspect_output> --port 8766
```

The server binds only to `127.0.0.1`.

## A Decision Says `Save failed`

Confirm the Review Desk process is still running and that the inspect-output
folder is writable and has free disk space. Retry only after resolving the
error; a failed save is not represented as successful.

## A Candidate Does Not Appear

Confirm:

1. `improvement_preview.json` contains exactly one matching image record.
2. `preview_artifacts.json` exists and has the expected schema.
3. The recorded relative artifact path remains below `preview_artifacts/`.
4. The candidate bytes still match the recorded SHA-256.

Refresh the page after running a candidate CLI command while Review Desk is
already open.

## `preview-generate` Says The Operation Is Unsupported

The selected record must request `LOCAL_CLASSICAL` and either `REDUCE_HALO` or
`REDUCE_ENCODING_ARTIFACTS`. Dataset Forge does not invent or substitute an
operation.

## A Preview Plan Chooses An Unexpected Operation

The current planner selects one operation per image with fixed category
precedence. Caption or duplicate findings may take precedence over image
artifact findings. Review the full evidence list and record human judgment;
do not treat the operation as a complete diagnosis.

## A Sidecar Is Rejected As Malformed

Use UTF-8 JSON with a top-level object and the expected `schema` value. Restore
from a known-good copy if manual editing introduced duplicate or partial
records.

## Findings Seem Too Broad

Check known false-positive contexts in the [Review Desk Guide](review-desk-guide.md).
Use **Accepted Style / False Positive** and notes to preserve your judgment.
Analyzer confidence is advisory, not probability or certainty.

## Source Safety Verification

For a release or high-value dataset, hash source images before and after the
workflow with `Get-FileHash -Algorithm SHA256`. Only inspect-output sidecars and
isolated candidate artifacts should change.

