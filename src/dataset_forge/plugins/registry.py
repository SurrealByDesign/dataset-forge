from __future__ import annotations

import importlib
import inspect
import json
import logging
import os
import pkgutil
from pathlib import Path
from typing import Any, Iterable

from dataset_forge.plugins.config import load_plugin_configuration
from dataset_forge.plugins.sdk import (
    Plugin,
    PluginContext,
    PluginExecutionResult,
)

LOGGER = logging.getLogger("dataset_forge.plugins")


def default_plugin_state_path() -> Path:
    override = os.environ.get("DATASET_FORGE_PLUGIN_STATE")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".dataset_forge" / "plugins.json"


class PluginRegistry:
    def __init__(self, state_path: Path | None = None) -> None:
        self._plugins: dict[str, type[Plugin]] = {}
        self._configurations: dict[str, dict[str, Any]] = {}
        self.state_path = (state_path or default_plugin_state_path()).expanduser()
        self._disabled = self._load_disabled()

    def register(self, plugin: type[Plugin]) -> type[Plugin]:
        if not inspect.isclass(plugin) or not issubclass(plugin, Plugin):
            raise TypeError("Registered plugins must inherit from Plugin.")
        if inspect.isabstract(plugin):
            raise TypeError("Abstract plugin classes cannot be registered.")
        plugin.validate_metadata()
        if plugin.id in self._plugins and self._plugins[plugin.id] is not plugin:
            raise ValueError(f"Plugin already registered: {plugin.id}")
        self._plugins[plugin.id] = plugin
        return plugin

    def discover(self, package_name: str = "dataset_forge.plugins") -> tuple[str, ...]:
        package = importlib.import_module(package_name)
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            raise ValueError(f"Plugin discovery package has no path: {package_name}")
        before = set(self._plugins)
        modules = [package]
        for module_info in pkgutil.walk_packages(
            package_path,
            prefix=f"{package_name}.",
        ):
            modules.append(importlib.import_module(module_info.name))
        for module in modules:
            for _, plugin in inspect.getmembers(module, inspect.isclass):
                if (
                    plugin is not Plugin
                    and issubclass(plugin, Plugin)
                    and not inspect.isabstract(plugin)
                    and plugin.__module__.startswith(package_name)
                ):
                    self.register(plugin)
        return tuple(sorted(set(self._plugins) - before))

    def list_plugins(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        plugins = []
        for plugin_id in sorted(self._plugins):
            if enabled_only and not self.is_enabled(plugin_id):
                continue
            metadata = self._plugins[plugin_id].metadata()
            metadata["enabled"] = self.is_enabled(plugin_id)
            plugins.append(metadata)
        return plugins

    def info(self, plugin_id: str) -> dict[str, Any]:
        metadata = self.get(plugin_id).metadata()
        metadata["enabled"] = self.is_enabled(plugin_id)
        metadata["configuration"] = dict(self._configurations.get(plugin_id, {}))
        return metadata

    def get(self, plugin_id: str) -> type[Plugin]:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Unknown plugin: {plugin_id}") from exc

    def create(self, plugin_id: str, config: dict[str, Any] | None = None) -> Plugin:
        if not self.is_enabled(plugin_id):
            raise ValueError(f"Plugin is disabled: {plugin_id}")
        merged = dict(self._configurations.get(plugin_id, {}))
        merged.update(config or {})
        return self.get(plugin_id)(merged)

    def enable(self, plugin_id: str) -> None:
        self.get(plugin_id)
        self._disabled.discard(plugin_id)
        self._save_state()

    def disable(self, plugin_id: str) -> None:
        self.get(plugin_id)
        self._disabled.add(plugin_id)
        self._save_state()

    def is_enabled(self, plugin_id: str) -> bool:
        self.get(plugin_id)
        return plugin_id not in self._disabled

    def configure(self, path: Path) -> None:
        configurations = load_plugin_configuration(path)
        unknown = sorted(set(configurations) - set(self._plugins))
        if unknown:
            raise ValueError(
                f"Configuration references unknown plugin(s): {', '.join(unknown)}"
            )
        self._configurations.update(configurations)

    def validate_dependencies(
        self,
        plugin_ids: Iterable[str],
        *,
        initial_artifacts: Iterable[str] = (),
    ) -> None:
        available = set(initial_artifacts)
        for plugin_id in plugin_ids:
            plugin = self.get(plugin_id)
            if not self.is_enabled(plugin_id):
                raise ValueError(f"Plugin is disabled: {plugin_id}")
            missing = [name for name in plugin.requires if name not in available]
            if missing:
                raise ValueError(
                    f"Plugin '{plugin_id}' is missing required artifact(s): "
                    f"{', '.join(missing)}."
                )
            available.update(plugin.produces)

    def execute(
        self,
        plugin_id: str,
        context: PluginContext,
        *,
        config: dict[str, Any] | None = None,
        fail_fast: bool = False,
    ) -> PluginExecutionResult:
        try:
            plugin = self.create(plugin_id, config)
            result = plugin.run(context)
            if result.plugin_id != plugin_id:
                raise ValueError(
                    f"Plugin '{plugin_id}' returned result for '{result.plugin_id}'."
                )
            return result
        except Exception as exc:
            LOGGER.exception("Plugin failed: %s", plugin_id)
            if fail_fast:
                raise
            return PluginExecutionResult(
                plugin_id=plugin_id,
                status="failed",
                error=str(exc),
            )

    def clear(self) -> None:
        self._plugins.clear()
        self._configurations.clear()

    def _load_disabled(self) -> set[str]:
        if not self.state_path.is_file():
            return set()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Could not read plugin state: %s", self.state_path)
            return set()
        disabled = data.get("disabled", []) if isinstance(data, dict) else []
        return {item for item in disabled if isinstance(item, str)}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"disabled": sorted(self._disabled)}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)


plugin_registry = PluginRegistry()


def discover_builtin_plugins() -> PluginRegistry:
    plugin_registry.discover("dataset_forge.plugins.builtin")
    return plugin_registry

