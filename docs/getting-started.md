# Getting Started

This guide takes you from a folder of images to the local Review Desk.
Dataset Forge never changes the source images in that folder.

## Requirements

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/) for the documented development workflow.
- A local folder containing supported image files.

## Install From Source

```powershell
git clone https://github.com/surrealbydesign/dataset-forge.git
cd dataset-forge
uv sync
```

Confirm the installation:

```powershell
uv run dataset-forge --version
uv run dataset-forge --help
```

## Inspect A Dataset

```powershell
uv run dataset-forge inspect "C:\path\to\my_dataset"
```

By default, reports are written to `my_dataset\inspect_output\`. To keep all
generated files elsewhere:

```powershell
uv run dataset-forge inspect "C:\path\to\my_dataset" `
  --output "C:\path\to\dataset_forge_output"
```

`inspect` prints a **Start Here** block containing the exact Review Desk
command, output directory, and the most useful reports.

## Open The Review Desk

```powershell
uv run dataset-forge review "C:\path\to\dataset_forge_output"
```

The browser opens on localhost. Start with **Next Action**, then review images
in the **Review Queue**. Decisions, workflow state, and notes save to
`review_decisions.json`. Preview approval state saves to
`improvement_preview.json` only when that optional sidecar exists.

## Understand The Queues

- **Priority Review**: inspect first because evidence is more significant or
  comes from multiple finding categories.
- **Needs Review**: one or more advisory findings need human interpretation.
- **No Findings Emitted**: no current analyzer emitted a finding. This is not a
  guarantee that the image is suitable for training.

## Continue The Workflow

After recording decisions:

```powershell
uv run dataset-forge plan "C:\path\to\dataset_forge_output"
uv run dataset-forge preview "C:\path\to\dataset_forge_output"
```

These commands write advisory planning sidecars. They do not execute changes.
See the [Improvement Preview Guide](improvement-preview-guide.md) before
creating or importing a candidate preview.

## Next Reading

- [Review Desk Guide](review-desk-guide.md)
- [User Guide](user-guide.md)
- [Troubleshooting](troubleshooting.md)

