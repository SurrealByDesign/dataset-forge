import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.cli import main
from dataset_forge.execution import Pipeline
from dataset_forge.plugins import (
    Analyzer,
    PluginContext,
    PluginExecutionResult,
    PluginMetadataError,
    PluginRegistry,
    PluginStageAdapter,
)


class GoodPlugin(Analyzer):
    id = "test.good"
    name = "Good Plugin"
    version = "1.0.0"
    author = "Tests"
    description = "Valid test plugin."
    tags = ("test",)
    input_types = ("source_images",)
    output_types = ("json",)
    configurable_parameters = {
        "level": {"type": "number", "default": 1},
    }
    requires = ("source_images",)
    produces = ("good_report",)
    estimated_runtime = "instant"
    estimated_memory = 1024
    estimated_gpu = 0

    def run(self, context):
        destination = context.output_path / "good.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps({"level": self.config["level"]}),
            encoding="utf-8",
        )
        return PluginExecutionResult(
            self.id,
            "success",
            {"good_report": destination},
        )


class DependentPlugin(GoodPlugin):
    id = "test.dependent"
    name = "Dependent Plugin"
    requires = ("good_report",)
    produces = ("dependent_report",)


class FailingPlugin(GoodPlugin):
    id = "test.failing"
    name = "Failing Plugin"
    produces = ("failure_report",)

    def run(self, context):
        raise RuntimeError("isolated plugin failure")


class InvalidPlugin(Analyzer):
    id = ""

    def run(self, context):
        return PluginExecutionResult("", "success")


class PluginTests(unittest.TestCase):
    def test_registers_and_inspects_plugin_metadata(self) -> None:
        with TemporaryDirectory() as temp:
            registry = PluginRegistry(Path(temp) / "state.json")

            registry.register(GoodPlugin)
            metadata = registry.info("test.good")

            self.assertEqual(metadata["category"], "analyzer")
            self.assertEqual(metadata["version"], "1.0.0")
            self.assertEqual(metadata["produces"], ["good_report"])
            self.assertTrue(metadata["enabled"])

    def test_rejects_invalid_plugin_metadata(self) -> None:
        with TemporaryDirectory() as temp:
            registry = PluginRegistry(Path(temp) / "state.json")

            with self.assertRaises(PluginMetadataError):
                registry.register(InvalidPlugin)

    def test_discovers_builtin_plugins(self) -> None:
        with TemporaryDirectory() as temp:
            registry = PluginRegistry(Path(temp) / "state.json")

            discovered = registry.discover("dataset_forge.plugins.builtin")

            self.assertIn("lora.dataset_analyzer", discovered)
            self.assertIn(
                "cleanup.anime_placeholder",
                [plugin["id"] for plugin in registry.list_plugins()],
            )
            self.assertEqual(len(registry.list_plugins()), 8)

    def test_enable_disable_state_persists(self) -> None:
        with TemporaryDirectory() as temp:
            state_path = Path(temp) / "plugins.json"
            registry = PluginRegistry(state_path)
            registry.register(GoodPlugin)
            registry.disable("test.good")

            reloaded = PluginRegistry(state_path)
            reloaded.register(GoodPlugin)
            self.assertFalse(reloaded.is_enabled("test.good"))

            reloaded.enable("test.good")
            self.assertTrue(reloaded.is_enabled("test.good"))

    def test_validates_plugin_dependencies(self) -> None:
        with TemporaryDirectory() as temp:
            registry = PluginRegistry(Path(temp) / "state.json")
            registry.register(GoodPlugin)
            registry.register(DependentPlugin)

            registry.validate_dependencies(
                ["test.good", "test.dependent"],
                initial_artifacts=("source_images",),
            )
            with self.assertRaisesRegex(ValueError, "missing required artifact"):
                registry.validate_dependencies(
                    ["test.dependent"],
                    initial_artifacts=("source_images",),
                )

    def test_failure_is_isolated_by_default(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            registry = PluginRegistry(root / "state.json")
            registry.register(FailingPlugin)

            result = registry.execute(
                "test.failing",
                PluginContext(root, root / "output"),
            )

            self.assertEqual(result.status, "failed")
            self.assertIn("isolated plugin failure", result.error)

    def test_loads_json_and_yaml_plugin_configuration(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            registry = PluginRegistry(root / "state.json")
            registry.register(GoodPlugin)
            json_path = root / "plugins.json"
            json_path.write_text(
                json.dumps({"plugins": {"test.good": {"level": 4}}}),
                encoding="utf-8",
            )
            registry.configure(json_path)
            self.assertEqual(registry.create("test.good").config["level"], 4)

            yaml_path = root / "plugins.yaml"
            yaml_path.write_text(
                "plugins:\n  test.good:\n    level: 7\n",
                encoding="utf-8",
            )
            registry.configure(yaml_path)
            self.assertEqual(registry.create("test.good").config["level"], 7)

    def test_placeholder_plugins_execute_without_changing_sources(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            image_path = source / "sample.png"
            Image.new("RGB", (16, 16), "navy").save(image_path)
            before = image_path.read_bytes()
            registry = PluginRegistry(root / "state.json")
            registry.discover("dataset_forge.plugins.builtin")
            context = PluginContext(
                source,
                root / "output",
                source_files=(image_path,),
            )

            for metadata in registry.list_plugins():
                result = registry.execute(metadata["id"], context)
                self.assertEqual(result.status, "success")
                self.assertTrue(all(path.is_file() for path in result.artifacts.values()))

            self.assertEqual(before, image_path.read_bytes())
            output_pngs = [
                path for path in (root / "output").rglob("*") if path.suffix == ".png"
            ]
            # TraditionalCleanupTransform copies the source image unchanged
            # into output/precleanup/ as part of its placeholder behavior.
            self.assertTrue(all(path.parent.name == "precleanup" for path in output_pngs))
            for path in output_pngs:
                self.assertEqual(path.read_bytes(), before)

    def test_plugin_stage_adapter_isolates_failure(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            Image.new("RGB", (8, 8), "black").save(source / "sample.png")
            registry = PluginRegistry(root / "state.json")
            registry.register(FailingPlugin)
            stage = PluginStageAdapter(registry, "test.failing")

            summary = Pipeline(
                "plugins",
                [stage],
                initial_artifacts=("source_images",),
            ).run(source, root / "output")

            marker = root / "output" / "plugins" / "test.failing" / "failure_report.json"
            self.assertEqual(summary.status, "completed")
            self.assertEqual(json.loads(marker.read_text())["status"], "failed")

    def test_plugin_cli_lists_and_inspects_plugins(self) -> None:
        with TemporaryDirectory() as temp:
            old_state = os.environ.get("DATASET_FORGE_PLUGIN_STATE")
            os.environ["DATASET_FORGE_PLUGIN_STATE"] = str(
                Path(temp) / "plugin-state.json"
            )
            try:
                output = io.StringIO()
                with redirect_stdout(output):
                    list_exit = main(["plugins", "list"])
                    info_exit = main(
                        ["plugins", "info", "lora.dataset_analyzer"]
                    )
                self.assertEqual(list_exit, 0)
                self.assertEqual(info_exit, 0)
                self.assertIn("lora.dataset_analyzer", output.getvalue())
            finally:
                if old_state is None:
                    os.environ.pop("DATASET_FORGE_PLUGIN_STATE", None)
                else:
                    os.environ["DATASET_FORGE_PLUGIN_STATE"] = old_state


if __name__ == "__main__":
    unittest.main()
