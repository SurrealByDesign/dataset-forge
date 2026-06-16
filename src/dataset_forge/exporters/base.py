from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping, Sequence


class Exporter(ABC):
    """Contract for a future dataset packaging strategy."""

    name: str
    description: str
    input_requirements: Sequence[str] = ()
    output_type: str
    parameters: Mapping[str, Any] = {}

    @abstractmethod
    def run(
        self,
        input_path: Path,
        output_path: Path,
        **parameters: Any,
    ) -> object:
        """Export generated dataset assets without mutating source images."""

