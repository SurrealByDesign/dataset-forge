import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from dataset_forge.cli import main
from dataset_forge.presets import PresetError, list_presets, load_preset


def valid_preset_data() -> dict[str, object]:
    return {
        "name": "Test Cleanup",
        "description": "A test preset.",
        "prompt": "clean image",
        "negative_prompt": "artifacts",
        "strengths": {"light": 0.2, "medium": 0.5, "strong": 0.8},
        "notes": "Test only.",
    }


class PresetTests(unittest.TestCase):
    def test_loads_valid_preset(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "test.json"
            path.write_text(json.dumps(valid_preset_data()), encoding="utf-8")

            preset = load_preset(path)

            self.assertEqual(preset.name, "Test Cleanup")
            self.assertEqual(preset.strengths["medium"], 0.5)
            self.assertEqual(preset.source, path.resolve())

    def test_invalid_preset_reports_missing_fields(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            path.write_text('{"name": "Incomplete"}', encoding="utf-8")

            with self.assertRaisesRegex(PresetError, "missing required field"):
                load_preset(path)

    def test_loads_and_validates_transform_chain(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "chain.json"
            data = valid_preset_data()
            data["transforms"] = [
                {"name": "reduce_microtexture", "strength": 35},
                {"name": "preserve_lineart", "strength": 80},
            ]
            path.write_text(json.dumps(data), encoding="utf-8")

            preset = load_preset(path)

            self.assertEqual(
                [transform.name for transform in preset.transforms],
                ["reduce_microtexture", "preserve_lineart"],
            )
            self.assertEqual(preset.transforms[0].parameters["strength"], 35)

    def test_rejects_invalid_transform_chain_strength(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "invalid-chain.json"
            data = valid_preset_data()
            data["transforms"] = [{"name": "cleanup", "strength": 101}]
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(PresetError, "between 0 and 100"):
                load_preset(path)

    def test_new_format_does_not_require_legacy_strengths_or_notes(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "new.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "New Format",
                        "description": "Transform chain preset.",
                        "transforms": [{"name": "future_transform", "strength": 50}],
                        "prompt": "clean",
                        "negative_prompt": "artifacts",
                    }
                ),
                encoding="utf-8",
            )

            preset = load_preset(path)

            self.assertEqual(preset.strengths, {})
            self.assertEqual(preset.notes, "")

    def test_lists_presets_by_name(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for filename in ("second.json", "first.json"):
                (root / filename).write_text(
                    json.dumps(valid_preset_data()),
                    encoding="utf-8",
                )

            presets = list_presets(root)

            self.assertEqual(
                [preset.source.name for preset in presets],
                ["first.json", "second.json"],
            )

    def test_cli_lists_presets_without_input_or_output(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--list-presets"])

        self.assertEqual(exit_code, 0)
        self.assertIn("watercolor_pencil_cleanup", output.getvalue())
        self.assertIn("general_artifact_cleanup", output.getvalue())
        self.assertIn("anime_lineart_cleanup", output.getvalue())
        self.assertIn("general_ai_artifact_cleanup", output.getvalue())
        self.assertIn("photoreal_cleanup", output.getvalue())

    def test_cli_dry_run_still_works_with_transform_chain_preset(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--input",
                        str(source),
                        "--output",
                        str(root / "output"),
                        "--dry-run",
                        "--preset",
                        "watercolor_pencil_cleanup",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Source images are read-only", output.getvalue())


if __name__ == "__main__":
    unittest.main()
