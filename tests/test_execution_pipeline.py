import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.execution import (
    Pipeline,
    PipelineDependencyError,
    PipelineExecutionError,
    PipelineStage,
    StageRegistry,
    StageResult,
)


class RecordingStage(PipelineStage):
    id = "record"
    name = "Record"
    description = "Write a test artifact."
    produces = ("recorded",)
    estimated_runtime = "instant"
    estimated_ram = 1024
    estimated_vram = 0
    estimated_disk_write = 16

    def __init__(self, config=None):
        super().__init__(config)
        self.runs = 0

    def expected_outputs(self, context):
        return {"recorded": context.output_path / "recorded.txt"}

    def run(self, context):
        self.runs += 1
        path = self.expected_outputs(context)["recorded"]
        path.write_text(f"run {self.runs}", encoding="utf-8")
        return StageResult({"recorded": path})


class DependentStage(PipelineStage):
    id = "dependent"
    name = "Dependent"
    description = "Consume the recorded artifact."
    requires = ("recorded",)
    produces = ("finished",)

    def __init__(self, config=None):
        super().__init__(config)
        self.runs = 0

    def expected_outputs(self, context):
        return {"finished": context.output_path / "finished.txt"}

    def run(self, context):
        self.runs += 1
        value = context.artifacts["recorded"].read_text(encoding="utf-8")
        path = self.expected_outputs(context)["finished"]
        path.write_text(value, encoding="utf-8")
        return StageResult({"finished": path})


class MissingDependencyStage(PipelineStage):
    id = "missing"
    name = "Missing"
    description = "Invalid test stage."
    requires = ("not_produced",)

    def expected_outputs(self, context):
        return {}

    def run(self, context):
        return StageResult({})


class FailOnceStage(DependentStage):
    id = "fail_once"
    name = "Fail Once"

    def __init__(self, config=None):
        super().__init__(config)
        self.failed = False

    def run(self, context):
        if not self.failed:
            self.failed = True
            raise RuntimeError("intentional interruption")
        return super().run(context)


class PipelineExecutionTests(unittest.TestCase):
    def test_constructs_ordered_pipeline(self) -> None:
        first = RecordingStage()
        second = DependentStage()

        pipeline = Pipeline("test", [first, second])

        self.assertEqual([stage.id for stage in pipeline.stages], ["record", "dependent"])

    def test_stage_registry_registers_and_creates_stage(self) -> None:
        registry = StageRegistry()

        registry.register(RecordingStage)
        created = registry.create("record", {"mode": "test"})

        self.assertIsInstance(created, RecordingStage)
        self.assertEqual(created.config["mode"], "test")

    def test_dependency_validation_reports_missing_artifact(self) -> None:
        with self.assertRaisesRegex(
            PipelineDependencyError,
            "missing required artifact.*not_produced",
        ):
            Pipeline("invalid", [MissingDependencyStage()])

    def test_dry_run_writes_nothing(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            stage = RecordingStage()

            summary = Pipeline("test", [stage]).run(
                source,
                output,
                dry_run=True,
            )

            self.assertEqual(summary.status, "dry-run")
            self.assertEqual(stage.runs, 0)
            self.assertFalse(output.exists())

    def test_creates_checkpoint_and_report(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))

            summary = Pipeline("test", [RecordingStage()]).run(source, output)

            state = json.loads(
                (output / "pipeline_state.json").read_text(encoding="utf-8")
            )
            report = json.loads(
                (output / "pipeline_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["stages"][0]["status"], "completed")
            self.assertEqual(report["stages"][0]["id"], "record")
            self.assertIsNotNone(summary.report_path)

    def test_resume_continues_after_interrupted_stage(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            first = RecordingStage()
            second = FailOnceStage()
            pipeline = Pipeline("test", [first, second])

            with self.assertRaisesRegex(PipelineExecutionError, "intentional interruption"):
                pipeline.run(source, output)

            checkpoint = json.loads(
                (output / "pipeline_state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(checkpoint["stages"][0]["status"], "completed")
            self.assertEqual(checkpoint["stages"][1]["status"], "failed")

            summary = pipeline.resume(output)

            self.assertEqual(summary.status, "completed")
            self.assertEqual(first.runs, 1)
            self.assertEqual(second.runs, 1)

    def test_skips_when_inputs_and_configs_are_unchanged(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            stage = RecordingStage()
            pipeline = Pipeline("test", [stage], config={"mode": "stable"})
            pipeline.run(source, output)

            summary = pipeline.run(source, output)

            self.assertEqual(stage.runs, 1)
            self.assertEqual(summary.stages_run, 0)
            self.assertEqual(summary.stages_skipped, 1)

    def test_force_stage_runs_unchanged_stage(self) -> None:
        with TemporaryDirectory() as temp:
            source, output = _paths(Path(temp))
            stage = RecordingStage()
            pipeline = Pipeline("test", [stage])
            pipeline.run(source, output)

            summary = pipeline.run(source, output, force_stage="record")

            self.assertEqual(stage.runs, 2)
            self.assertEqual(summary.stages_run, 1)
            self.assertEqual(summary.stages_skipped, 0)


def _paths(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    source.mkdir()
    Image.new("RGB", (8, 8), "navy").save(source / "sample.png")
    return source, root / "output"


if __name__ == "__main__":
    unittest.main()

