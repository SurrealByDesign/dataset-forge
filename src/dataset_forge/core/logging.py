from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def create_file_logger(output_path: Path) -> logging.Logger:
    logs_path = output_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    logger = logging.getLogger(f"dataset_forge.{timestamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(logs_path / f"run-{timestamp}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

