from __future__ import annotations

from dataset_forge.transforms.base import Transform


class TransformRegistry:
    def __init__(self) -> None:
        self._transforms: dict[str, type[Transform]] = {}

    def register(self, transform: type[Transform]) -> type[Transform]:
        name = getattr(transform, "name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Transform classes must define a non-empty name.")
        if name in self._transforms:
            raise ValueError(f"Transform already registered: {name}")
        self._transforms[name] = transform
        return transform

    def get(self, name: str) -> type[Transform]:
        try:
            return self._transforms[name]
        except KeyError as exc:
            raise KeyError(f"Unknown transform: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._transforms))

    def clear(self) -> None:
        self._transforms.clear()


transform_registry = TransformRegistry()

