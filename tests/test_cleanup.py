import csv
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from dataset_forge.cleanup import CleanupAction, CleanupOrchestrator
from dataset_forge.cleanup.io import write_cleanup_plan
from dataset_forge.cleanup.rules import default_cleanup_rules_path, load_cleanup_rules
from dataset_forge.cli import main
from dataset_forge.plugins import PluginRegistry
from dataset_forge.resources import ResourceManager


class CleanupOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PluginRegistry(Path("unused-plugin-state.json"))
        self.registry.discover("dataset_forge.plugins.builtin")
        self.plugins = self.registry.list_plugins(enabled_only=True)
        self.orchestrator = CleanupOrchestrator()

    def test_selects_actions_from_configured_signals(self) -> None:
        rows = [
            _row("keep.png", quality=90, artifact=10, texture=20),
            _row("light.png", quality=70, artifact=50, texture=30),
            _row("medium.png", quality=55, artifact=65, texture=40),
            _row("strong.png", quality=35, artifact=85, texture=50),
            _row("texture.png", quality=60, artifact=20, texture=85),
            _row("probable.png", probable_duplicate_of="keep.png"),
            _row("exact.png", exact_duplicate_of="keep.png"),
            _row("tiny.png", quality=20, megapixels=0.1),
        ]

        plan = self.orchestrator.create_plan(
            rows,
            plugin_metadata=self.plugins,
        )
        actions = {decision.filename: decision.action for decision in plan.decisions}

        self.assertEqual(actions["keep.png"], CleanupAction.KEEP)
        self.assertEqual(actions["light.png"], CleanupAction.CLEAN_LIGHT)
        self.assertEqual(actions["medium.png"], CleanupAction.CLEAN_MEDIUM)
        self.assertEqual(actions["strong.png"], CleanupAction.CLEAN_STRONG)
        self.assertEqual(
            actions["texture.png"],
            CleanupAction.TEXTURE_NORMALIZE_LIGHT,
        )
        self.assertEqual(
            actions["probable.png"],
            CleanupAction.DUPLICATE_REVIEW,
        )
        self.assertEqual(actions["exact.png"], CleanupAction.EXCLUDE)
        self.assertEqual(actions["tiny.png"], CleanupAction.REGENERATE)

    def test_confidence_increases_with_threshold_margin(self) -> None:
        plan = self.orchestrator.create_plan(
            [
                _row("near.png", artifact=76),
                _row("far.png", artifact=95),
            ],
            plugin_metadata=self.plugins,
        )

        self.assertGreater(
            plan.decisions[1].confidence,
            plan.decisions[0].confidence,
        )

    def test_missing_analysis_routes_to_manual_review(self) -> None:
        row = _row("incomplete.png")
        row["artifact_score"] = ""

        decision = self.orchestrator.create_plan(
            [row],
            plugin_metadata=self.plugins,
        ).decisions[0]

        self.assertEqual(decision.action, CleanupAction.MANUAL_REVIEW)
        self.assertIn("metrics are missing", decision.explanation)

    def test_expected_benefit_and_projected_quality_are_explainable(self) -> None:
        decision = self.orchestrator.create_plan(
            [_row("cleanup.png", quality=40, artifact=80)],
            health_report={"dataset_health_score": 50},
            plugin_metadata=self.plugins,
        ).decisions[0]

        self.assertGreater(decision.estimated_quality_delta, 0)
        self.assertEqual(
            decision.estimated_after_quality_score,
            decision.before_quality_score + decision.estimated_quality_delta,
        )
        self.assertIn("quality points", decision.expected_benefit)

    def test_loads_json_and_yaml_rules(self) -> None:
        json_rules = load_cleanup_rules()
        with TemporaryDirectory() as temp:
            data = json.loads(
                default_cleanup_rules_path().read_text(encoding="utf-8")
            )
            data["thresholds"]["artifact_light"] = 40
            yaml_path = Path(temp) / "rules.yaml"
            yaml_path.write_text(_to_yaml(data), encoding="utf-8")

            yaml_rules = load_cleanup_rules(yaml_path)

            self.assertEqual(json_rules.artifact_light, 45)
            self.assertEqual(yaml_rules.artifact_light, 40)

    def test_matches_plugin_by_capability_and_preset(self) -> None:
        decision = self.orchestrator.create_plan(
            [_row("painting.png", artifact=80)],
            recommendations=[
                {
                    "filename": "painting.png",
                    "suggested_preset": "watercolor_pencil_cleanup",
                }
            ],
            plugin_metadata=self.plugins,
        ).decisions[0]

        self.assertEqual(
            decision.recommended_plugin,
            "cleanup.watercolor_placeholder",
        )
        self.assertEqual(
            decision.recommended_preset,
            "watercolor_pencil_cleanup",
        )

    def test_user_preference_changes_plugin_ranking(self) -> None:
        decision = self.orchestrator.create_plan(
            [_row("generic.png", artifact=80)],
            plugin_metadata=self.plugins,
            user_config={
                "preferred_plugins": ["cleanup.anime_placeholder"],
            },
        ).decisions[0]

        self.assertEqual(
            decision.recommended_plugin,
            "cleanup.anime_placeholder",
        )

    def test_resource_profile_affects_plugin_ranking(self) -> None:
        plugins = [
            {
                "id": "test.large",
                "category": "transform",
                "enabled": True,
                "capabilities": ["artifact_cleanup"],
                "tags": [],
                "compatible_presets": [],
                "estimated_quality_gain": 20,
                "estimated_memory": 8 * 1024**3,
                "estimated_gpu": 0,
                "estimated_runtime": "minutes",
            },
            {
                "id": "test.small",
                "category": "transform",
                "enabled": True,
                "capabilities": ["artifact_cleanup"],
                "tags": [],
                "compatible_presets": [],
                "estimated_quality_gain": 8,
                "estimated_memory": 128 * 1024**2,
                "estimated_gpu": 0,
                "estimated_runtime": "seconds",
            },
        ]

        decision = self.orchestrator.create_plan(
            [_row("limited.png", artifact=80)],
            plugin_metadata=plugins,
            resource_profile={"name": "eco", "ram_limit_mb": 512},
        ).decisions[0]

        self.assertEqual(decision.recommended_plugin, "test.small")

    def test_writes_cleanup_plan_json_and_csv(self) -> None:
        with TemporaryDirectory() as temp:
            output = Path(temp)
            plan = self.orchestrator.create_plan(
                [_row("sample.png", artifact=50)],
                plugin_metadata=self.plugins,
            )

            json_path, csv_path = write_cleanup_plan(output, plan)

            data = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(data["decisions"][0]["filename"], "sample.png")
            self.assertEqual(rows[0]["action"], "CLEAN_LIGHT")

    def test_plan_summary_and_explain_cli(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            _write_manifest(output / "manifest_v3.csv", [_row("castle.png", artifact=80)])
            (output / "manifest_latest.json").write_text(
                '{"version": 3, "path": "manifest_v3.csv"}\n',
                encoding="utf-8",
            )
            (output / "dataset_health.json").write_text(
                '{"dataset_health_score": 55, "average_artifact_score": 40}\n',
                encoding="utf-8",
            )
            old_state = os.environ.get("DATASET_FORGE_PLUGIN_STATE")
            os.environ["DATASET_FORGE_PLUGIN_STATE"] = str(root / "plugins.json")
            try:
                stream = io.StringIO()
                with redirect_stdout(stream):
                    plan_exit = main(["plan", "--output", str(output)])
                    summary_exit = main(
                        ["summarize-plan", "--output", str(output)]
                    )
                    explain_exit = main(
                        ["explain", "castle.png", "--output", str(output)]
                    )
                text = stream.getvalue()
            finally:
                if old_state is None:
                    os.environ.pop("DATASET_FORGE_PLUGIN_STATE", None)
                else:
                    os.environ["DATASET_FORGE_PLUGIN_STATE"] = old_state

            self.assertEqual((plan_exit, summary_exit, explain_exit), (0, 0, 0))
            self.assertIn("Strong Cleanup: 1", text)
            self.assertIn("Image: castle.png", text)
            self.assertIn("Decision: CLEAN_STRONG", text)
            self.assertTrue((output / "cleanup_plan.json").is_file())
            self.assertTrue((output / "cleanup_plan.csv").is_file())


def _row(
    filename: str,
    *,
    quality: float = 85,
    artifact: float = 10,
    texture: float = 20,
    megapixels: float = 2,
    exact_duplicate_of: str = "",
    probable_duplicate_of: str = "",
) -> dict[str, object]:
    return {
        "original_path": filename,
        "filename": filename,
        "file_hash": (filename.encode().hex() * 16)[:64],
        "file_size": 2048,
        "status": "analyzed",
        "overall_quality_score": quality,
        "artifact_score": artifact,
        "texture_score": texture,
        "megapixels": megapixels,
        "exact_duplicate_of": exact_duplicate_of,
        "probable_duplicate_of": probable_duplicate_of,
    }


def _write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _to_yaml(data: dict[str, object], indent: int = 0) -> str:
    lines: list[str] = []
    for key, value in data.items():
        prefix = " " * indent + f"{key}:"
        if isinstance(value, dict):
            lines.append(prefix)
            lines.append(_to_yaml(value, indent + 2).rstrip())
        elif isinstance(value, bool):
            lines.append(f"{prefix} {'true' if value else 'false'}")
        elif value == "":
            lines.append(f'{prefix} ""')
        else:
            lines.append(f"{prefix} {value}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    unittest.main()
