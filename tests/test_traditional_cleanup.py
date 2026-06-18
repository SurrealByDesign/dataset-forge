import csv
import hashlib
import json
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.cleanup import (
    CleanupProfileError,
    PlanControlManager,
    execute_plan,
    list_cleanup_profiles,
    load_cleanup_profile,
)
from dataset_forge.cleanup.execute import PRECLEANUP_DIR
from dataset_forge.cleanup.profiles import OPERATION_NAMES
from dataset_forge.cli import future_main as main
from dataset_forge.plugins.builtin.traditional_cleanup import (
    TraditionalCleanupTransform,
)
from dataset_forge.plugins.registry import PluginRegistry
from dataset_forge.plugins.sdk import PluginContext


class CleanupProfileTests(unittest.TestCase):
    def test_built_in_profiles_load_and_parse_operations(self) -> None:
        for name in (
            "watercolor_light",
            "watercolor_medium",
            "colored_pencil_light",
            "colored_pencil_medium",
            "anime_lineart_preserve",
            "photoreal_microcleanup",
            "watercolor_microcleanup_light",
        ):
            profile = load_cleanup_profile(name)
            self.assertEqual(profile.name, name)
            self.assertTrue(profile.operations)
            for operation in profile.operations:
                self.assertIn(operation.name, OPERATION_NAMES)
                self.assertIsInstance(operation.parameters, dict)

    def test_list_cleanup_profiles_includes_built_ins(self) -> None:
        profiles = {profile.name for profile in list_cleanup_profiles()}
        self.assertIn("watercolor_light", profiles)
        self.assertIn("anime_lineart_preserve", profiles)

    def test_unsupported_operation_name_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bad_profile.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "bad_profile",
                        "description": "invalid",
                        "operations": [{"name": "not_a_real_operation"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(CleanupProfileError):
                load_cleanup_profile(path)

    def test_unknown_profile_name_raises(self) -> None:
        with self.assertRaises(CleanupProfileError):
            load_cleanup_profile("does_not_exist_profile")

    def test_deprecated_watercolor_profile_alias_still_works(self) -> None:
        with self.assertLogs(
            "dataset_forge.cleanup.profiles",
            level=logging.WARNING,
        ) as captured:
            profile = load_cleanup_profile(
                "gpt_watercolor_microcleanup_light"
            )

        self.assertEqual(profile.name, "watercolor_microcleanup_light")
        self.assertIn("deprecated", " ".join(captured.output).lower())


class TraditionalCleanupPluginTests(unittest.TestCase):
    def test_plugin_is_registered(self) -> None:
        with TemporaryDirectory() as temp:
            registry = PluginRegistry(Path(temp) / "state.json")
            discovered = registry.discover("dataset_forge.plugins.builtin")
            self.assertIn("cleanup.traditional_cleanup", discovered)
            metadata = registry.info("cleanup.traditional_cleanup")
            self.assertEqual(metadata["category"], "transform")
            self.assertIn("traditional_cleanup", metadata["capabilities"])

    def test_plugin_run_copies_image_and_writes_sidecar(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source_dir = root / "source"
            source_dir.mkdir()
            image_path = source_dir / "sample.png"
            image_path.write_bytes(b"fake-image-bytes")

            registry = PluginRegistry(root / "state.json")
            registry.discover("dataset_forge.plugins.builtin")
            context = PluginContext(
                source_dir,
                root / "output",
                source_files=(image_path,),
                config={"profile": "watercolor_light"},
            )
            result = registry.execute("cleanup.traditional_cleanup", context)

            self.assertEqual(result.status, "success")
            self.assertEqual(result.details["profile"], "watercolor_light")
            self.assertTrue(result.details["requested_operations"])

            output_image = root / "output" / "precleanup" / "sample.png"
            self.assertTrue(output_image.is_file())
            self.assertEqual(output_image.read_bytes(), b"fake-image-bytes")

            metadata_path = output_image.with_name(output_image.name + ".json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["plugin_id"], TraditionalCleanupTransform.id)
            self.assertEqual(metadata["profile"], "watercolor_light")
            self.assertTrue(metadata["placeholder"])
            self.assertEqual(
                metadata["source_hash"],
                hashlib.sha256(b"fake-image-bytes").hexdigest(),
            )
            self.assertEqual(metadata["source_hash"], metadata["output_hash"])
            self.assertIn("requested_operations", metadata)
            self.assertIn("parameters", metadata)
            self.assertIn("timestamp", metadata)


class TraditionalCleanupExecutePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.output = Path(self.temp.name) / "output"
        self.output.mkdir(parents=True)
        self.images = Path(self.temp.name) / "images"
        self.images.mkdir(parents=True)

        self.sources = {
            "img_a.png": _write_source(self.images / "img_a.png", b"alpha"),
            "img_b.png": _write_source(self.images / "img_b.png", b"bravo"),
        }

        _write_plan(self.output)
        _write_manifest(self.output, self.sources)
        self.manager = PlanControlManager(self.output)
        self.manager.approve("img_a.png")
        self.manager.approve("img_b.png")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_execute_plan_dispatches_to_traditional_cleanup(self) -> None:
        summary = execute_plan(
            self.output,
            transform="traditional_cleanup",
            cleanup_profile="anime_lineart_preserve",
        )
        self.assertEqual(summary.transform, "traditional_cleanup")
        self.assertEqual(summary.cleanup_profile, "anime_lineart_preserve")
        self.assertTrue(summary.requested_operations)
        self.assertEqual(summary.executed, 2)

        precleanup = self.output / PRECLEANUP_DIR
        output_file = precleanup / "img_a_clean_light.png"
        self.assertTrue(output_file.is_file())
        self.assertEqual(output_file.read_bytes(), b"alpha")

        metadata = json.loads(
            output_file.with_name(output_file.name + ".json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(metadata["profile"], "anime_lineart_preserve")
        self.assertTrue(metadata["placeholder"])

    def test_source_images_unchanged_after_traditional_cleanup(self) -> None:
        before = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in self.sources.items()
        }
        execute_plan(
            self.output,
            transform="traditional_cleanup",
            cleanup_profile="watercolor_light",
        )
        after = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in self.sources.items()
        }
        self.assertEqual(before, after)

    def test_execution_report_records_profile_and_operations(self) -> None:
        execute_plan(
            self.output,
            transform="traditional_cleanup",
            cleanup_profile="watercolor_medium",
        )
        report = json.loads(
            (self.output / "execution_report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["transform"], "traditional_cleanup")
        self.assertEqual(report["cleanup_profile"], "watercolor_medium")
        self.assertTrue(report["requested_operations"])
        self.assertTrue(report["placeholder_execution"])
        self.assertEqual(report["output_location"], str(self.output / PRECLEANUP_DIR))

    def test_dry_run_traditional_cleanup_writes_nothing(self) -> None:
        summary = execute_plan(
            self.output,
            dry_run=True,
            transform="traditional_cleanup",
            cleanup_profile="watercolor_light",
        )
        self.assertTrue(summary.dry_run)
        self.assertFalse((self.output / PRECLEANUP_DIR).exists())
        self.assertFalse((self.output / "execution_report.json").exists())

    def test_cli_traditional_cleanup_preview(self) -> None:
        result = main(
            [
                "traditional-cleanup",
                "--output",
                str(self.output),
                "--profile",
                "watercolor_light",
                "--preview",
            ]
        )
        self.assertEqual(result, 0)
        self.assertFalse((self.output / PRECLEANUP_DIR).exists())
        self.assertFalse((self.output / "execution_report.json").exists())

    def test_cli_traditional_cleanup_run(self) -> None:
        result = main(
            [
                "traditional-cleanup",
                "--output",
                str(self.output),
                "--profile",
                "colored_pencil_light",
            ]
        )
        self.assertEqual(result, 0)
        precleanup = self.output / PRECLEANUP_DIR
        self.assertTrue((precleanup / "img_a_clean_light.png").is_file())
        self.assertTrue((precleanup / "img_b_clean_medium.png").is_file())


class RealTraditionalCleanupIntegrationTests(unittest.TestCase):
    def test_cli_direct_input_reaches_real_cleanup_and_preserves_source(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            images = root / "test_images"
            images.mkdir()
            source = images / "noisy.png"
            _write_noisy_image(source)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "df_test"

            result = main(
                [
                    "traditional-cleanup",
                    "--profile",
                    "watercolor_microcleanup_light",
                    "--input",
                    str(images),
                    "--output",
                    str(output),
                    "--limit",
                    "1",
                ]
            )

            self.assertEqual(result, 0)
            precleanup = output / PRECLEANUP_DIR
            sidecars = list(precleanup.glob("*.png.json"))
            self.assertEqual(len(sidecars), 1)
            metadata = json.loads(sidecars[0].read_text(encoding="utf-8"))
            self.assertFalse(metadata["placeholder"])
            self.assertIn("accepted", metadata)
            self.assertIn("preservation_metrics", metadata)
            self.assertTrue((precleanup / "comparison_sheet.html").is_file())
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(),
                source_hash,
            )
            if metadata["accepted"]:
                cleaned = sidecars[0].with_name(sidecars[0].name[:-5])
                self.assertTrue(cleaned.is_file())
                self.assertNotEqual(cleaned.read_bytes(), source.read_bytes())

    def test_execute_plan_rejection_has_no_accepted_output_artifact(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            images = root / "images"
            images.mkdir()
            source = images / "noisy.png"
            _write_noisy_image(source)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            _write_plan_for_sources(output, {"noisy.png": source})
            manager = PlanControlManager(output)
            manager.approve("noisy.png")
            profile = root / "reject.json"
            profile.write_text(
                json.dumps(
                    {
                        "name": "reject_real_cleanup",
                        "description": "Reject any changed candidate.",
                        "operations": [
                            {
                                "name": "local_contrast_normalization",
                                "parameters": {
                                    "clip_limit": 2.0,
                                    "tile_grid_size": 4,
                                    "blend": 1.0,
                                },
                            }
                        ],
                        "acceptance_checks": {
                            "max_average_pixel_difference": 0,
                            "max_color_histogram_difference": 0,
                            "max_edge_difference": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            summary = execute_plan(
                output,
                transform="traditional_cleanup",
                cleanup_profile=profile,
            )

            record = next(item for item in summary.records if item["filename"] == "noisy.png")
            self.assertEqual(record["status"], "rejected")
            self.assertEqual(record["output_path"], "")
            sidecar = output / PRECLEANUP_DIR / "noisy_clean_light.png.json"
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertFalse(metadata["placeholder"])
            self.assertFalse(metadata["accepted"])
            self.assertTrue(metadata["rejection_reason"])
            self.assertFalse(
                (output / PRECLEANUP_DIR / "noisy_clean_light.png").exists()
            )
            self.assertTrue(
                (output / PRECLEANUP_DIR / "comparison_sheet.html").is_file()
            )
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(),
                source_hash,
            )

    def test_placeholder_profile_remains_placeholder(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            source = root / "sample.png"
            _write_noisy_image(source)
            _write_plan_for_sources(output, {"sample.png": source})
            PlanControlManager(output).approve("sample.png")

            execute_plan(
                output,
                transform="traditional_cleanup",
                cleanup_profile="watercolor_light",
            )

            sidecar = output / PRECLEANUP_DIR / "sample_clean_light.png.json"
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertTrue(metadata["placeholder"])


def _write_source(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _write_plan(output: Path) -> None:
    decisions = [
        _decision("a-id", "img_a.png", "CLEAN_LIGHT"),
        _decision("b-id", "img_b.png", "CLEAN_MEDIUM"),
    ]
    (output / "cleanup_plan.json").write_text(
        json.dumps(
            {
                "version": 1,
                "total_images": len(decisions),
                "action_counts": {},
                "decisions": decisions,
            }
        ),
        encoding="utf-8",
    )


def _decision(image_id: str, filename: str, action: str) -> dict[str, object]:
    return {
        "image_id": image_id,
        "filename": filename,
        "action": action,
        "confidence": 90,
        "explanation": "Measured evidence supports this decision.",
        "expected_benefit": "+10 quality points",
        "before_quality_score": 50,
        "estimated_after_quality_score": 60,
        "estimated_quality_delta": 10,
        "recommended_plugin": "cleanup.traditional_cleanup",
        "recommended_preset": "watercolor_pencil_cleanup",
        "recommended_strength": "medium",
        "estimated_runtime": "seconds",
        "estimated_disk_write": 0,
        "estimated_gpu_required": False,
        "warnings": [],
    }


def _write_manifest(output: Path, sources: dict[str, Path]) -> None:
    path = output / "manifest_v1.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["filename", "original_path"],
        )
        writer.writeheader()
        for filename, source in sources.items():
            writer.writerow({"filename": filename, "original_path": str(source)})
    (output / "manifest_latest.json").write_text(
        json.dumps({"path": "manifest_v1.csv"}),
        encoding="utf-8",
    )


def _write_plan_for_sources(output: Path, sources: dict[str, Path]) -> None:
    decisions = [
        _decision(f"{index}-id", filename, "CLEAN_LIGHT")
        for index, filename in enumerate(sources, start=1)
    ]
    (output / "cleanup_plan.json").write_text(
        json.dumps(
            {
                "version": 1,
                "total_images": len(decisions),
                "action_counts": {"CLEAN_LIGHT": len(decisions)},
                "decisions": decisions,
            }
        ),
        encoding="utf-8",
    )
    _write_manifest(output, sources)


def _write_noisy_image(path: Path) -> None:
    image = Image.new("RGB", (96, 96), (210, 190, 165))
    pixels = image.load()
    for y in range(96):
        for x in range(96):
            wash = int(12 * ((x + y) / 192))
            pixels[x, y] = (210 - wash, 190 + wash // 2, 165 + wash)
    for x, y in ((8, 8), (17, 40), (31, 22), (55, 70), (78, 15), (84, 82)):
        pixels[x, y] = (255, 255, 255)
    image.save(path)


if __name__ == "__main__":
    unittest.main()
