from __future__ import annotations

from dataset_forge.execution.base import PipelineStage


class StageRegistry:
    def __init__(self) -> None:
        self._stages: dict[str, type[PipelineStage]] = {}

    def register(self, stage: type[PipelineStage]) -> type[PipelineStage]:
        stage_id = getattr(stage, "id", "")
        if not isinstance(stage_id, str) or not stage_id.strip():
            raise ValueError("Pipeline stages must define a non-empty id.")
        if stage_id in self._stages:
            raise ValueError(f"Pipeline stage already registered: {stage_id}")
        self._stages[stage_id] = stage
        return stage

    def get(self, stage_id: str) -> type[PipelineStage]:
        try:
            return self._stages[stage_id]
        except KeyError as exc:
            raise KeyError(f"Unknown pipeline stage: {stage_id}") from exc

    def create(
        self,
        stage_id: str,
        config: dict[str, object] | None = None,
    ) -> PipelineStage:
        return self.get(stage_id)(config)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._stages))

    def clear(self) -> None:
        self._stages.clear()


stage_registry = StageRegistry()

