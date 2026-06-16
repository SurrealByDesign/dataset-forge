from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dataset_forge.core.paths import discover_images, resolve_directory
from dataset_forge.execution.base import PipelineContext, PipelineStage
from dataset_forge.execution.hashing import (
    hash_json,
    hash_preset,
    hash_source_files,
    hash_source_list,
)
from dataset_forge.execution.state import (
    REPORT_FILENAME,
    STATE_FILENAME,
    load_state,
    write_json_atomic,
)
from dataset_forge.presets import Preset
from dataset_forge.resources import ResourceManager


class PipelineDependencyError(ValueError):
    """Raised when a pipeline stage dependency cannot be satisfied."""


class PipelineExecutionError(RuntimeError):
    """Raised when a pipeline stage fails."""


@dataclass(frozen=True)
class PipelineRunSummary:
    pipeline_name: str
    status: str
    stages_run: int
    stages_skipped: int
    total_duration: float
    state_path: Path | None
    report_path: Path | None


class Pipeline:
    def __init__(
        self,
        name: str,
        stages: Iterable[PipelineStage],
        *,
        description: str = "",
        config: dict[str, Any] | None = None,
        initial_artifacts: Iterable[str] = (),
    ) -> None:
        self.name = name
        self.description = description
        self.stages = tuple(stages)
        self.config = dict(config or {})
        self.initial_artifacts = tuple(initial_artifacts)
        self.validate()

    def validate(self) -> None:
        available = set(self.initial_artifacts)
        stage_ids: set[str] = set()
        produced_by: dict[str, str] = {}
        for stage in self.stages:
            if not stage.id:
                raise PipelineDependencyError("Pipeline stages must define an id.")
            if stage.id in stage_ids:
                raise PipelineDependencyError(f"Duplicate pipeline stage id: {stage.id}")
            stage_ids.add(stage.id)
            missing = [requirement for requirement in stage.requires if requirement not in available]
            if missing:
                raise PipelineDependencyError(
                    f"Stage '{stage.id}' is missing required artifact(s): "
                    f"{', '.join(missing)}."
                )
            for artifact in stage.produces:
                if artifact in produced_by:
                    raise PipelineDependencyError(
                        f"Artifact '{artifact}' is produced by both "
                        f"'{produced_by[artifact]}' and '{stage.id}'."
                    )
                produced_by[artifact] = stage.id
                available.add(artifact)

    def preview(
        self,
        input_path: Path,
        output_path: Path,
        *,
        preset: Preset | None = None,
        force_stage: str | None = None,
        resource_manager: ResourceManager | None = None,
    ) -> list[dict[str, Any]]:
        prepared = self._prepare(
            input_path,
            output_path,
            preset,
            resource_manager or ResourceManager(),
        )
        prior_state = self._load_prior_state(prepared.output_path)
        plan, _ = self._build_plan(prepared, prior_state, force_stage)
        self._print_preview(prepared, plan)
        return plan

    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        preset: Preset | None = None,
        dry_run: bool = False,
        force_stage: str | None = None,
        resource_manager: ResourceManager | None = None,
        force: bool = False,
    ) -> PipelineRunSummary:
        manager = resource_manager or ResourceManager()
        context = self._prepare(input_path, output_path, preset, manager)
        prior_state = self._load_prior_state(context.output_path)
        plan, hashes = self._build_plan(context, prior_state, force_stage)
        self._print_preview(context, plan)
        if dry_run:
            return PipelineRunSummary(
                self.name,
                "dry-run",
                0,
                sum(item["action"] == "skip" for item in plan),
                0.0,
                None,
                None,
            )
        estimates = _plan_estimates(plan)
        manager.validate_estimates(
            estimated_disk_write=estimates["disk"],
            estimated_ram=estimates["ram"],
            force=force,
        )

        context.output_path.mkdir(parents=True, exist_ok=True)
        started_at = _timestamp()
        state = self._initial_state(context, hashes, plan, started_at)
        state_path = context.output_path / STATE_FILENAME
        report_path = context.output_path / REPORT_FILENAME
        write_json_atomic(state_path, state)

        total_started = time.perf_counter()
        stages_run = 0
        stages_skipped = 0
        for index, (stage, planned) in enumerate(zip(self.stages, plan, strict=True)):
            stage_state = state["stages"][index]
            stage_state["started_at"] = _timestamp()
            if planned["action"] == "skip":
                stage_state["status"] = "skipped"
                stage_state["duration_seconds"] = 0.0
                stage_state["completed_at"] = _timestamp()
                context.artifacts.update(
                    {
                        name: Path(path)
                        for name, path in planned["outputs"].items()
                    }
                )
                stages_skipped += 1
                state["updated_at"] = _timestamp()
                write_json_atomic(state_path, state)
                continue

            stage_started = time.perf_counter()
            stage_state["status"] = "running"
            state["updated_at"] = _timestamp()
            write_json_atomic(state_path, state)
            try:
                result = stage.run(context)
                missing_artifacts = [
                    name for name in stage.produces if name not in result.artifacts
                ]
                if missing_artifacts:
                    raise PipelineExecutionError(
                        f"Stage '{stage.id}' did not return artifact(s): "
                        f"{', '.join(missing_artifacts)}."
                    )
                missing_outputs = [
                    name
                    for name in stage.produces
                    if not Path(result.artifacts[name]).exists()
                ]
                if missing_outputs:
                    raise PipelineExecutionError(
                        f"Stage '{stage.id}' did not create output(s): "
                        f"{', '.join(missing_outputs)}."
                    )
                context.artifacts.update(result.artifacts)
                duration = time.perf_counter() - stage_started
                stage_state.update(
                    {
                        "status": "completed",
                        "duration_seconds": round(duration, 6),
                        "completed_at": _timestamp(),
                        "outputs": {
                            name: str(path)
                            for name, path in result.artifacts.items()
                        },
                        "details": dict(result.details),
                    }
                )
                stages_run += 1
                state["updated_at"] = _timestamp()
                write_json_atomic(state_path, state)
            except Exception as exc:
                duration = time.perf_counter() - stage_started
                stage_state.update(
                    {
                        "status": "failed",
                        "duration_seconds": round(duration, 6),
                        "completed_at": _timestamp(),
                        "error": str(exc),
                    }
                )
                state["status"] = "failed"
                state["updated_at"] = _timestamp()
                state["total_duration_seconds"] = round(
                    time.perf_counter() - total_started,
                    6,
                )
                write_json_atomic(state_path, state)
                write_json_atomic(report_path, _report_from_state(state))
                raise PipelineExecutionError(
                    f"Stage '{stage.id}' failed: {exc}"
                ) from exc

        total_duration = time.perf_counter() - total_started
        state["status"] = "completed"
        state["updated_at"] = _timestamp()
        state["completed_at"] = _timestamp()
        state["total_duration_seconds"] = round(total_duration, 6)
        write_json_atomic(state_path, state)
        write_json_atomic(report_path, _report_from_state(state))
        print(f"\nPipeline completed in {total_duration:.2f}s")
        return PipelineRunSummary(
            self.name,
            "completed",
            stages_run,
            stages_skipped,
            total_duration,
            state_path,
            report_path,
        )

    def resume(
        self,
        output_path: Path,
        *,
        force_stage: str | None = None,
        resource_manager: ResourceManager | None = None,
        force: bool = False,
    ) -> PipelineRunSummary:
        resolved_output = resolve_directory(output_path)
        state = load_state(resolved_output)
        if state.get("pipeline") != self.name:
            raise ValueError(
                f"Pipeline state uses '{state.get('pipeline')}', not '{self.name}'."
            )
        preset_source = state.get("preset_source")
        preset = None
        if preset_source:
            from dataset_forge.presets import load_preset

            preset = load_preset(Path(preset_source))
        manager = resource_manager
        if manager is None:
            resource_values = state.get("resource_profile")
            manager = (
                ResourceManager.from_dict(resource_values)
                if isinstance(resource_values, dict)
                else ResourceManager()
            )
        return self.run(
            Path(state["input_path"]),
            resolved_output,
            preset=preset,
            force_stage=force_stage,
            resource_manager=manager,
            force=force,
        )

    def _prepare(
        self,
        input_path: Path,
        output_path: Path,
        preset: Preset | None,
        resource_manager: ResourceManager,
    ) -> PipelineContext:
        resolved_input = resolve_directory(input_path)
        resolved_output = resolve_directory(output_path)
        if not resolved_input.is_dir():
            raise ValueError(
                f"Input folder does not exist or is not a directory: {resolved_input}"
            )
        if resolved_input == resolved_output:
            raise ValueError("Input and output folders must be different.")
        recursive = bool(self.config.get("recursive", False))
        limit = self.config.get("limit")
        if limit is not None and (isinstance(limit, bool) or int(limit) < 1):
            raise ValueError("Pipeline limit must be at least 1.")
        discovery = discover_images(
            resolved_input,
            recursive=recursive,
            limit=int(limit) if limit is not None else None,
            excluded_root=resolved_output,
        )
        _, file_hashes = hash_source_files(discovery.images, resolved_input)
        return PipelineContext(
            input_path=resolved_input,
            output_path=resolved_output,
            pipeline_name=self.name,
            pipeline_config=self.config,
            preset=preset,
            source_files=tuple(discovery.images),
            source_file_hashes=file_hashes,
            resource_manager=resource_manager,
            data={"skipped_files": discovery.skipped_files},
        )

    def _build_plan(
        self,
        context: PipelineContext,
        prior_state: dict[str, Any] | None,
        force_stage: str | None,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        if force_stage is not None and force_stage not in {stage.id for stage in self.stages}:
            raise ValueError(f"Unknown force stage: {force_stage}")
        hashes = {
            "source_list": hash_source_list(context.source_files, context.input_path),
            "source_files": hash_json(context.source_file_hashes),
            "preset": hash_preset(context.preset),
            "pipeline_config": hash_json(self.config),
        }
        prior_stages = {
            item.get("id"): item
            for item in (prior_state or {}).get("stages", [])
            if isinstance(item, dict)
        }
        artifact_fingerprints = {
            name: hash_json({"initial_artifact": name, **hashes})
            for name in self.initial_artifacts
        }
        plan: list[dict[str, Any]] = []
        for stage in self.stages:
            expected = {
                name: path.resolve()
                for name, path in stage.expected_outputs(context).items()
            }
            dependency_hashes = {
                name: artifact_fingerprints[name]
                for name in stage.requires
            }
            fingerprint = hash_json(
                {
                    **hashes,
                    "stage_id": stage.id,
                    "stage_config": stage.config,
                    "dependencies": dependency_hashes,
                }
            )
            prior = prior_stages.get(stage.id, {})
            outputs_exist = all(path.exists() for path in expected.values())
            unchanged = (
                prior.get("fingerprint") == fingerprint
                and prior.get("status") in {"completed", "skipped"}
                and outputs_exist
            )
            forced = stage.id == force_stage
            action = "skip" if unchanged and not forced else "run"
            if forced:
                reason = "forced by --force-stage"
            elif unchanged:
                reason = "inputs, configuration, and outputs are unchanged"
            elif not outputs_exist:
                reason = "one or more outputs are missing"
            else:
                reason = "inputs or configuration changed"
            item = {
                "id": stage.id,
                "name": stage.name,
                "description": stage.description,
                "action": action,
                "reason": reason,
                "fingerprint": fingerprint,
                "stage_config": stage.config,
                "stage_config_hash": hash_json(stage.config),
                "requires": list(stage.requires),
                "produces": list(stage.produces),
                "estimated_runtime": stage.estimated_runtime,
                "estimated_ram": stage.estimated_ram,
                "estimated_vram": stage.estimated_vram,
                "estimated_disk_write": stage.estimated_disk_write,
                "estimated_temp_storage": stage.estimated_temp_storage,
                "outputs": {name: str(path) for name, path in expected.items()},
            }
            plan.append(item)
            artifact_fingerprints.update(
                {artifact: fingerprint for artifact in stage.produces}
            )
        return plan, hashes

    def _load_prior_state(self, output_path: Path) -> dict[str, Any] | None:
        path = output_path / STATE_FILENAME
        return load_state(output_path) if path.is_file() else None

    def _initial_state(
        self,
        context: PipelineContext,
        hashes: dict[str, str],
        plan: list[dict[str, Any]],
        started_at: str,
    ) -> dict[str, Any]:
        return {
            "version": 1,
            "pipeline": self.name,
            "description": self.description,
            "status": "running",
            "input_path": str(context.input_path),
            "output_path": str(context.output_path),
            "preset_source": str(context.preset.source) if context.preset else None,
            "pipeline_config": self.config,
            "resource_profile": context.resource_manager.to_dict(),
            "initial_artifacts": list(self.initial_artifacts),
            "hashes": hashes,
            "source_file_hashes": context.source_file_hashes,
            "started_at": started_at,
            "updated_at": started_at,
            "total_duration_seconds": 0.0,
            "stages": [
                {
                    **item,
                    "status": "pending",
                    "duration_seconds": 0.0,
                    "started_at": None,
                    "completed_at": None,
                    "details": {},
                    "error": None,
                }
                for item in plan
            ],
        }

    def _print_preview(
        self,
        context: PipelineContext,
        plan: list[dict[str, Any]],
    ) -> None:
        active = [item for item in plan if item["action"] == "run"]
        estimates = _plan_estimates(plan)
        manager = context.resource_manager
        print(f"Pipeline preview: {self.name}")
        print(f"Source images: {len(context.source_files)}")
        print("Source images are read-only and will not be modified.")
        print(f"Execution profile: {manager.profile.name}")
        print(f"Worker count: {manager.worker_count}")
        print(f"CPU target: {manager.profile.cpu_target_percent}%")
        print(f"RAM limit: {manager.profile.ram_limit_mb} MB")
        print(f"I/O throttle: {manager.profile.io_throttle}")
        print(f"Cache policy: {manager.profile.cache_policy}")
        print(
            "Temporary storage policy: "
            f"{manager.profile.temporary_storage_policy}"
        )
        print(f"Adaptive mode: {'enabled' if manager.profile.adaptive_mode else 'disabled'}")
        for item in plan:
            print(
                f"- {item['id']}: {item['action'].upper()} "
                f"({item['reason']})"
            )
        runtime_values = sorted(
            {item["estimated_runtime"] for item in active}
        )
        runtime = ", ".join(runtime_values) if runtime_values else "no stages scheduled"
        print(f"Estimated runtime: {runtime}")
        print(f"Estimated disk write: {_format_bytes(estimates['disk'])}")
        print(f"Estimated temp storage: {_format_bytes(estimates['temp'])}")
        print(f"Estimated peak RAM: {_format_bytes(estimates['ram'])}")
        print(f"Estimated peak VRAM: {_format_bytes(estimates['vram'])}")
        print("Expected output files:")
        for item in plan:
            for path in item["outputs"].values():
                print(f"- {path}")
        print(f"- {context.output_path / STATE_FILENAME}")
        print(f"- {context.output_path / REPORT_FILENAME}")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plan_estimates(plan: list[dict[str, Any]]) -> dict[str, int]:
    active = [item for item in plan if item["action"] == "run"]
    return {
        "disk": sum(item["estimated_disk_write"] for item in active),
        "temp": sum(item["estimated_temp_storage"] for item in active),
        "ram": max((item["estimated_ram"] for item in active), default=0),
        "vram": max((item["estimated_vram"] for item in active), default=0),
    }


def _format_bytes(value: int) -> str:
    if value <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GB"


def _report_from_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline": state["pipeline"],
        "status": state["status"],
        "input_path": state["input_path"],
        "output_path": state["output_path"],
        "started_at": state["started_at"],
        "completed_at": state.get("completed_at"),
        "total_duration_seconds": state["total_duration_seconds"],
        "hashes": state["hashes"],
        "resource_profile": state["resource_profile"],
        "stages": [
            {
                "id": stage["id"],
                "name": stage["name"],
                "status": stage["status"],
                "duration_seconds": stage["duration_seconds"],
                "fingerprint": stage["fingerprint"],
                "outputs": stage["outputs"],
                "details": stage["details"],
                "error": stage["error"],
            }
            for stage in state["stages"]
        ],
    }
