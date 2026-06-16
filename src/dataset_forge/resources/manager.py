from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from dataset_forge.core.structured import load_structured_file


class ResourceLimitError(RuntimeError):
    """Raised when a pipeline exceeds configured resource safety limits."""


@dataclass(frozen=True)
class ResourceProfile:
    name: str
    max_workers: int
    cpu_target_percent: int
    ram_limit_mb: int
    io_throttle: str
    cache_policy: str
    temporary_storage_policy: str
    adaptive_mode: bool
    disk_limit_mb: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def built_in_profiles() -> dict[str, ResourceProfile]:
    cpus = _cpu_count()
    return {
        "eco": ResourceProfile(
            "eco", 1, 35, 1024, "low", "minimal", "cleanup", True, 1024
        ),
        "balanced": ResourceProfile(
            "balanced",
            max(1, cpus // 2),
            70,
            4096,
            "medium",
            "standard",
            "balanced",
            True,
            4096,
        ),
        "max": ResourceProfile(
            "max",
            cpus,
            95,
            16384,
            "unlimited",
            "aggressive",
            "performance",
            False,
            16384,
        ),
        "overnight": ResourceProfile(
            "overnight",
            max(1, cpus // 3),
            50,
            8192,
            "low",
            "standard",
            "cleanup",
            True,
            8192,
        ),
        "custom": ResourceProfile(
            "custom",
            max(1, cpus // 2),
            70,
            4096,
            "medium",
            "standard",
            "balanced",
            True,
            4096,
        ),
    }


def load_profile(
    name: str = "balanced",
    path: Path | None = None,
) -> ResourceProfile:
    profiles = built_in_profiles()
    if path is not None:
        source = path.expanduser().resolve()
        data = load_structured_file(source)
        if "max_workers" in data:
            direct_name = str(data.get("name", name))
            custom_profiles = {direct_name: data}
        else:
            custom_profiles = data.get("profiles", data)
        if not isinstance(custom_profiles, dict):
            raise ValueError(f"Profile config must contain an object: {source}")
        for profile_name, values in custom_profiles.items():
            if not isinstance(profile_name, str) or not isinstance(values, dict):
                raise ValueError(f"Invalid profile definition in {source}")
            base = profiles.get(profile_name, profiles["custom"])
            profiles[profile_name] = _profile_from_mapping(
                profile_name,
                values,
                base,
                source,
            )
    try:
        return profiles[name]
    except KeyError as exc:
        raise ValueError(f"Unknown execution profile: {name}") from exc


class ResourceManager:
    def __init__(
        self,
        profile: ResourceProfile | None = None,
        *,
        system_load_provider: Callable[[], float] | None = None,
    ) -> None:
        self.profile = profile or load_profile("balanced")
        self._system_load_provider = system_load_provider or (lambda: 0.0)
        self._validate_profile(self.profile)

    @classmethod
    def from_profile(
        cls,
        name: str = "balanced",
        *,
        profile_config: Path | None = None,
        overrides: Mapping[str, Any] | None = None,
        system_load_provider: Callable[[], float] | None = None,
    ) -> ResourceManager:
        profile = load_profile(name, profile_config)
        if overrides:
            profile = _apply_overrides(profile, overrides)
        return cls(profile, system_load_provider=system_load_provider)

    @classmethod
    def from_dict(
        cls,
        values: Mapping[str, Any],
        *,
        system_load_provider: Callable[[], float] | None = None,
    ) -> ResourceManager:
        name = str(values.get("name", "custom"))
        profile = _profile_from_mapping(
            name,
            dict(values),
            built_in_profiles()["custom"],
            Path("<saved pipeline state>"),
        )
        return cls(profile, system_load_provider=system_load_provider)

    @property
    def worker_count(self) -> int:
        workers = self.profile.max_workers
        if not self.profile.adaptive_mode:
            return workers
        load = min(100.0, max(0.0, float(self._system_load_provider())))
        if load >= 90:
            return 1
        if load > self.profile.cpu_target_percent:
            return max(1, workers // 2)
        return workers

    def validate_estimates(
        self,
        *,
        estimated_disk_write: int,
        estimated_ram: int,
        force: bool = False,
    ) -> None:
        disk_limit = self.profile.disk_limit_mb * 1024 * 1024
        if estimated_disk_write > disk_limit and not force:
            raise ResourceLimitError(
                "Estimated disk write "
                f"({_format_mb(estimated_disk_write)}) exceeds profile "
                f"'{self.profile.name}' limit ({self.profile.disk_limit_mb} MB). "
                "Use --force to proceed."
            )
        ram_limit = self.profile.ram_limit_mb * 1024 * 1024
        if estimated_ram > ram_limit and not force:
            raise ResourceLimitError(
                "Estimated peak RAM "
                f"({_format_mb(estimated_ram)}) exceeds profile "
                f"'{self.profile.name}' limit ({self.profile.ram_limit_mb} MB). "
                "Use --force to proceed."
            )

    def to_dict(self) -> dict[str, Any]:
        values = self.profile.to_dict()
        values["effective_workers"] = self.worker_count
        return values

    @staticmethod
    def _validate_profile(profile: ResourceProfile) -> None:
        if profile.max_workers < 1:
            raise ValueError("Profile max_workers must be at least 1.")
        if not 1 <= profile.cpu_target_percent <= 100:
            raise ValueError("Profile cpu_target_percent must be from 1 through 100.")
        if profile.ram_limit_mb < 1:
            raise ValueError("Profile ram_limit_mb must be at least 1.")
        if profile.disk_limit_mb < 1:
            raise ValueError("Profile disk_limit_mb must be at least 1.")
        if profile.io_throttle not in {"low", "medium", "high", "unlimited"}:
            raise ValueError("Profile io_throttle is invalid.")
        if profile.cache_policy not in {
            "none",
            "minimal",
            "standard",
            "aggressive",
        }:
            raise ValueError("Profile cache_policy is invalid.")
        if profile.temporary_storage_policy not in {
            "cleanup",
            "balanced",
            "performance",
        }:
            raise ValueError("Profile temporary_storage_policy is invalid.")


def _apply_overrides(
    profile: ResourceProfile,
    overrides: Mapping[str, Any],
) -> ResourceProfile:
    accepted = {
        "max_workers",
        "cpu_target_percent",
        "ram_limit_mb",
        "io_throttle",
        "cache_policy",
        "temporary_storage_policy",
        "adaptive_mode",
        "disk_limit_mb",
    }
    values = {
        key: value
        for key, value in overrides.items()
        if key in accepted and value is not None
    }
    return replace(profile, **values)


def _profile_from_mapping(
    name: str,
    values: Mapping[str, Any],
    base: ResourceProfile,
    source: Path,
) -> ResourceProfile:
    normalized = dict(values)
    normalized.pop("name", None)
    normalized.pop("effective_workers", None)
    allowed = {
        "max_workers",
        "cpu_target_percent",
        "ram_limit_mb",
        "io_throttle",
        "cache_policy",
        "temporary_storage_policy",
        "adaptive_mode",
        "disk_limit_mb",
    }
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ValueError(
            f"Unknown profile field(s) in {source}: {', '.join(unknown)}"
        )
    try:
        profile = replace(_apply_overrides(base, normalized), name=name)
        ResourceManager._validate_profile(profile)
        return profile
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid profile '{name}' in {source}: {exc}") from exc


def _format_mb(value: int) -> str:
    return f"{value / 1024 / 1024:.1f} MB"
