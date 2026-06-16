from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping, Sequence


class Transform(ABC):
    """Contract for a future, explicitly invoked dataset transformation."""

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
        """Run the transform without mutating the input path."""

