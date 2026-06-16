# Dataset Forge Plugin Development

**Build better datasets.**

Dataset Forge is a modular, deterministic dataset engineering platform for
preparing, analyzing, cleaning, validating, benchmarking, and exporting
datasets for generative AI. LoRA dataset preparation is the first primary use
case, while the plugin API supports broader generative AI and ML dataset
workflows.

Dataset Forge follows one architectural rule:

> Core should orchestrate. Plugins should specialize.

The pipeline engine owns ordering, dependencies, checkpoints, caching decisions,
resource policy, timing, and reports. Plugins own domain behavior such as image
analysis, validation, transformation, captioning, importing, review, and
exporting.

Adding a style, model, dataset format, or analysis policy must not require a
change to the pipeline engine.

## Plugin Types

Choose the narrowest SDK interface:

- `Analyzer`: measures or classifies dataset artifacts
- `Transform`: creates derived artifacts without overwriting inputs
- `Validator`: checks constraints and produces validation results
- `Captioner`: creates or plans textual metadata
- `Exporter`: packages existing artifacts for another workflow
- `Importer`: introduces external data as declared artifacts
- `ReviewProvider`: creates a review surface or review queue

All interfaces inherit from `dataset_forge.plugins.Plugin`.

## Minimal Plugin

```python
from dataset_forge.plugins import (
    Analyzer,
    PluginContext,
    PluginExecutionResult,
)


class CompositionAnalyzer(Analyzer):
    id = "example.composition_analyzer"
    name = "Composition Analyzer"
    version = "1.0.0"
    author = "Example Team"
    description = "Measures composition consistency."
    tags = ("analysis", "composition")
    input_types = ("source_images",)
    output_types = ("json_report",)
    configurable_parameters = {
        "sensitivity": {"type": "number", "default": 50}
    }
    requires = ("source_images",)
    produces = ("composition_report",)
    estimated_runtime = "seconds to minutes"
    estimated_memory = 256 * 1024 * 1024
    estimated_gpu = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        destination = (
            context.output_path
            / "plugins"
            / self.id
            / "composition_report.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("{}\n", encoding="utf-8")
        return PluginExecutionResult(
            plugin_id=self.id,
            status="success",
            artifacts={"composition_report": destination},
        )
```

## Metadata

Every concrete plugin must define:

- `id`: stable, globally distinctive identifier
- `name`: user-facing name
- `version`: plugin implementation version
- `author`: maintainer or organization
- `description`: concise purpose
- `tags`: discovery and filtering labels
- `input_types`: accepted data types
- `output_types`: generated data types
- `configurable_parameters`: parameter schema and defaults
- `requires`: artifact names required before execution
- `produces`: artifact names produced by execution
- `estimated_runtime`: human-readable estimate
- `estimated_memory`: estimated peak RAM in bytes
- `estimated_gpu`: estimated GPU memory in bytes
- `run()`: specialized behavior

Artifact names form the contract between plugins. Plugins should not import or
call another plugin's internal implementation.

## Lifecycle

1. Discovery imports modules under `dataset_forge.plugins`.
2. Registration validates metadata and rejects duplicate IDs.
3. Enablement state is loaded.
4. JSON or YAML defaults are merged with runtime configuration.
5. Dependency validation checks `requires` against available artifacts.
6. The registry creates the plugin.
7. `run()` receives a `PluginContext`.
8. The plugin returns `PluginExecutionResult`.
9. Failures are logged and converted to `status="failed"` unless fail-fast
   execution was explicitly requested.

Enablement state defaults to `~/.dataset_forge/plugins.json`. Set
`DATASET_FORGE_PLUGIN_STATE` to use another file.

## Configuration

JSON:

```json
{
  "plugins": {
    "example.composition_analyzer": {
      "sensitivity": 65
    }
  }
}
```

YAML:

```yaml
plugins:
  example.composition_analyzer:
    sensitivity: 65
```

Load configuration through `PluginRegistry.configure(path)`. Runtime values
passed to `create()` or `execute()` override file defaults.

## Pipeline Integration

Use `PluginStageAdapter` to insert any registered plugin into a pipeline:

```python
from dataset_forge.execution import Pipeline
from dataset_forge.plugins import PluginStageAdapter, PluginRegistry

registry = PluginRegistry()
registry.discover("dataset_forge.plugins")

stage = PluginStageAdapter(
    registry,
    "example.composition_analyzer",
    {"sensitivity": 65},
)

pipeline = Pipeline(
    "composition_review",
    [stage],
    initial_artifacts=("source_images",),
)
```

The adapter maps plugin metadata to the generic stage contract. The pipeline
engine does not need analyzer-, captioner-, transform-, or exporter-specific
code.

## Resource Rules

Plugins must use `context.resource_manager` for worker budgets, CPU/RAM policy,
cache behavior, temporary storage, and future GPU scheduling. A plugin must not
create an independent scheduling policy.

Transforms and exporters must write derived outputs. They must never overwrite
source images. Large copies should only be created when the selected exporter
explicitly requires them.

## LoRA Plugins

LoRA dataset preparation is the first primary use case, but LoRA behavior stays
outside core and does not define the platform identity.

A LoRA plugin should:

- use `lora` as a tag, not as a core execution mode
- consume generic artifacts such as `source_images`, manifests, or captions
- produce explicit artifacts such as suitability reports or export plans
- keep style-specific cleanup in transform plugins
- keep caption-model logic in captioner plugins
- keep training-folder layout in exporter plugins
- avoid model loading until `run()` begins
- obtain all scheduling decisions from `ResourceManager`

The built-in LoRA plugins are placeholders. They prove discovery, metadata,
configuration, isolation, and pipeline adaptation without performing cleanup,
captioning, image copying, or training.

## Discovery

Built-in discovery uses Python package scanning:

```python
registry.discover("dataset_forge.plugins.builtin")
```

The registry accepts any package name, leaving a clean extension point for
future Python entry-point discovery from separately installed packages.

## Management CLI

```powershell
dataset-forge plugins list
dataset-forge plugins info lora.dataset_analyzer
dataset-forge plugins disable lora.dataset_analyzer
dataset-forge plugins enable lora.dataset_analyzer
```

## Design Boundary

Core may know:

- how to discover and register a plugin
- how to validate artifact dependencies
- how to execute and isolate a plugin
- how to adapt a plugin to a pipeline stage

Core must not know:

- watercolor or anime cleanup behavior
- caption prompts or caption model APIs
- LoRA folder conventions
- model-specific artifact detection
- service-specific import or export formats

Those decisions belong in replaceable plugins.
