import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.execution import Pipeline, PipelineStage, StageResult
from dataset_forge.resources import (
    ResourceLimitError,
    ResourceManager,
    load_profile,
)


class LargeWriteStage(PipelineStage):
    id = "large"
    name = "Large"
    description = "Test resource safety."
    produces = ("large_output",)
    estimated_disk_write = 2 * 1024 * 1024
    estimated_ram = 1024
    estimated_temp_storage = 512

    def expected_outputs(self, context):
        return {"large_output": context.output_path / "large.txt"}

    def run(self, context):
        path = self.expected_outputs(context)["large_output"]
        path.write_text("done", encoding="utf-8")
        return StageResult({"large_output": path})


class ResourceManagerTests(unittest.TestCase):
    def test_balanced_defaults_are_valid(self) -> None:
        manager = ResourceManager()

        self.assertEqual(manager.profile.name, "balanced")
        self.assertGreaterEqual(manager.worker_count, 1)
        self.assertEqual(manager.profile.cache_policy, "standard")
        self.assertTrue(manager.profile.adaptive_mode)

    def test_loads_json_and_yaml_profiles(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            json_path = root / "profiles.json"
            json_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "quiet": {
                                "max_workers": 2,
                                "cpu_target_percent": 40,
                                "ram_limit_mb": 2048,
                                "io_throttle": "low",
                                "cache_policy": "minimal",
                                "temporary_storage_policy": "cleanup",
                                "adaptive_mode": True,
                                "disk_limit_mb": 512,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            yaml_path = root / "profile.yaml"
            yaml_path.write_text(
                "\n".join(
                    [
                        "name: custom",
                        "max_workers: 3",
                        "cpu_target_percent: 65",
                        "ram_limit_mb: 3072",
                        "io_throttle: medium",
                        "cache_policy: standard",
                        "temporary_storage_policy: balanced",
                        "adaptive_mode: true",
                        "disk_limit_mb: 1024",
                    ]
                ),
                encoding="utf-8",
            )

            quiet = load_profile("quiet", json_path)
            custom = load_profile("custom", yaml_path)

            self.assertEqual(quiet.max_workers, 2)
            self.assertEqual(custom.max_workers, 3)
            self.assertTrue(custom.adaptive_mode)

    def test_profile_overrides_replace_selected_values(self) -> None:
        manager = ResourceManager.from_profile(
            "eco",
            overrides={
                "max_workers": 4,
                "cpu_target_percent": 60,
                "cache_policy": "aggressive",
                "adaptive_mode": False,
            },
        )

        self.assertEqual(manager.profile.max_workers, 4)
        self.assertEqual(manager.profile.cpu_target_percent, 60)
        self.assertEqual(manager.profile.cache_policy, "aggressive")
        self.assertFalse(manager.profile.adaptive_mode)

    def test_adaptive_mode_reduces_workers_under_high_load(self) -> None:
        manager = ResourceManager.from_profile(
            "balanced",
            overrides={"max_workers": 8, "adaptive_mode": True},
            system_load_provider=lambda: 95,
        )

        self.assertEqual(manager.worker_count, 1)

    def test_adaptive_mode_keeps_workers_when_disabled(self) -> None:
        manager = ResourceManager.from_profile(
            "max",
            overrides={"max_workers": 8, "adaptive_mode": False},
            system_load_provider=lambda: 99,
        )

        self.assertEqual(manager.worker_count, 8)

    def test_pipeline_refuses_disk_limit_without_force(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            manager = ResourceManager.from_profile(
                "custom",
                overrides={"disk_limit_mb": 1, "ram_limit_mb": 128},
            )
            pipeline = Pipeline("limited", [LargeWriteStage()])

            with self.assertRaisesRegex(ResourceLimitError, "exceeds.*limit"):
                pipeline.run(source, output, resource_manager=manager)

            self.assertFalse(output.exists())

    def test_force_bypasses_disk_limit(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            manager = ResourceManager.from_profile(
                "custom",
                overrides={"disk_limit_mb": 1, "ram_limit_mb": 128},
            )

            summary = Pipeline("limited", [LargeWriteStage()]).run(
                source,
                output,
                resource_manager=manager,
                force=True,
            )

            self.assertEqual(summary.status, "completed")
            self.assertTrue((output / "large.txt").is_file())

    def test_preview_displays_resource_profile_and_estimates(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            stream = io.StringIO()
            manager = ResourceManager.from_profile("eco")

            with redirect_stdout(stream):
                Pipeline("preview", [LargeWriteStage()]).preview(
                    source,
                    output,
                    resource_manager=manager,
                )

            text = stream.getvalue()
            self.assertIn("Execution profile: eco", text)
            self.assertIn("Worker count:", text)
            self.assertIn("Estimated temp storage:", text)
            self.assertIn("Adaptive mode: enabled", text)


def _paths(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    source.mkdir()
    Image.new("RGB", (8, 8), "black").save(source / "sample.png")
    return source, root / "output"


if __name__ == "__main__":
    unittest.main()

