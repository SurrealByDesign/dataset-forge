"""Tests for the internal disk-backed measurement cache."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analysis.texture import TextureImageResult
from dataset_forge.measurement_cache import (
    ENV_CACHE_DIR,
    ENV_DISABLE_CACHE,
    build_cache_key,
    file_sha256,
)
from dataset_forge.measurements import (
    MEASUREMENT_SCHEMA_VERSION,
    TEXTURE_MEASUREMENT_VERSION,
    measure_image,
)


def _write_image(path: Path, value: int = 128) -> None:
    arr = np.full((64, 64, 3), value, dtype=np.uint8)
    Image.fromarray(arr).save(path)


def _texture(path: Path, micro: float = 12.0) -> TextureImageResult:
    resolved = path.expanduser().resolve()
    return TextureImageResult(
        filename=resolved.name,
        original_path=str(resolved),
        status="analyzed",
        microtexture_density_score=micro,
        watercolor_smoothness_score=88.0,
        highlight_speck_score=2.0,
        pencil_grain_score=4.0,
    )


def _db_path(cache_dir: Path) -> Path:
    return cache_dir / "measurements.sqlite"


def _row_count(cache_dir: Path) -> int:
    with closing(sqlite3.connect(_db_path(cache_dir))) as conn:
        return conn.execute("SELECT count(*) FROM measurement_cache").fetchone()[0]


class TestMeasurementCache(unittest.TestCase):
    def test_cache_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "image.png"
            _write_image(path)
            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: "", ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    side_effect=[_texture(path, 1.0), _texture(path, 2.0)],
                ) as eval_mock:
                    first = measure_image(path)
                    second = measure_image(path)

        self.assertEqual(first.texture.microtexture_density_score, 1.0)
        self.assertEqual(second.texture.microtexture_density_score, 2.0)
        self.assertEqual(eval_mock.call_count, 2)

    def test_cache_miss_writes_and_cache_hit_skips_evaluate_texture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir = root / "cache"
            path = root / "image.png"
            _write_image(path)

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir), ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 11.0),
                ) as eval_mock:
                    first = measure_image(path)
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    side_effect=AssertionError("cache hit should not remeasure"),
                ):
                    second = measure_image(path)
                row_count = _row_count(cache_dir)

        self.assertEqual(first.texture.microtexture_density_score, 11.0)
        self.assertEqual(second.texture.microtexture_density_score, 11.0)
        self.assertEqual(eval_mock.call_count, 1)
        self.assertEqual(row_count, 1)

    def test_changed_image_bytes_miss(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir = root / "cache"
            path = root / "image.png"

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir), ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                _write_image(path, value=32)
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 3.0),
                ) as first_eval:
                    first = measure_image(path)

                _write_image(path, value=224)
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 9.0),
                ) as second_eval:
                    second = measure_image(path)
                row_count = _row_count(cache_dir)

        self.assertEqual(first.texture.microtexture_density_score, 3.0)
        self.assertEqual(second.texture.microtexture_density_score, 9.0)
        self.assertEqual(first_eval.call_count, 1)
        self.assertEqual(second_eval.call_count, 1)
        self.assertEqual(row_count, 2)

    def test_version_change_misses(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir = root / "cache"
            path = root / "image.png"
            _write_image(path)

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir), ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 5.0),
                ) as first_eval:
                    first = measure_image(path)

                with (
                    patch(
                        "dataset_forge.measurements.TEXTURE_MEASUREMENT_VERSION",
                        "texture-v2",
                    ),
                    patch(
                        "dataset_forge.measurements.evaluate_texture",
                        return_value=_texture(path, 6.0),
                    ) as second_eval,
                ):
                    second = measure_image(path)
                row_count = _row_count(cache_dir)

        self.assertEqual(first.texture.microtexture_density_score, 5.0)
        self.assertEqual(second.texture.microtexture_density_score, 6.0)
        self.assertEqual(first_eval.call_count, 1)
        self.assertEqual(second_eval.call_count, 1)
        self.assertEqual(row_count, 2)

    def test_same_bytes_under_renamed_path_can_hit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir = root / "cache"
            first_path = root / "first.png"
            second_path = root / "second.png"
            _write_image(first_path)
            shutil.copyfile(first_path, second_path)

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir), ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(first_path, 7.0),
                ):
                    measure_image(first_path)
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    side_effect=AssertionError("renamed identical file should hit"),
                ):
                    measurements = measure_image(second_path)
                row_count = _row_count(cache_dir)

        self.assertEqual(measurements.image_path, second_path.resolve())
        self.assertEqual(measurements.texture.filename, second_path.name)
        self.assertEqual(measurements.texture.original_path, str(second_path.resolve()))
        self.assertEqual(measurements.texture.microtexture_density_score, 7.0)
        self.assertEqual(row_count, 1)

    def test_disable_env_bypasses_cache_even_when_dir_is_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir = root / "cache"
            path = root / "image.png"
            _write_image(path)

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir), ENV_DISABLE_CACHE: "1"},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    side_effect=[_texture(path, 1.0), _texture(path, 2.0)],
                ) as eval_mock:
                    measure_image(path)
                    measure_image(path)

        self.assertEqual(eval_mock.call_count, 2)
        self.assertFalse(_db_path(cache_dir).exists())

    def test_corrupt_cache_entry_is_ignored_and_recomputed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir = root / "cache"
            path = root / "image.png"
            _write_image(path)

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir), ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 4.0),
                ):
                    measure_image(path)

                file_hash = file_sha256(path)
                cache_key = build_cache_key(
                    file_hash,
                    MEASUREMENT_SCHEMA_VERSION,
                    TEXTURE_MEASUREMENT_VERSION,
                )
                with closing(sqlite3.connect(_db_path(cache_dir))) as conn:
                    conn.execute(
                        """
                        UPDATE measurement_cache
                        SET payload_json = ?
                        WHERE cache_key = ?
                        """,
                        ("not valid json", cache_key),
                    )
                    conn.commit()

                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 8.0),
                ) as eval_mock:
                    measurements = measure_image(path)
                row_count = _row_count(cache_dir)

        self.assertEqual(eval_mock.call_count, 1)
        self.assertEqual(measurements.texture.microtexture_density_score, 8.0)
        self.assertEqual(row_count, 1)

    def test_cache_write_failure_does_not_fail_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_dir_as_file = root / "cache-file"
            cache_dir_as_file.write_text("not a directory", encoding="utf-8")
            path = root / "image.png"
            _write_image(path)

            with patch.dict(
                os.environ,
                {ENV_CACHE_DIR: str(cache_dir_as_file), ENV_DISABLE_CACHE: ""},
                clear=False,
            ):
                with patch(
                    "dataset_forge.measurements.evaluate_texture",
                    return_value=_texture(path, 13.0),
                ):
                    measurements = measure_image(path)

        self.assertEqual(measurements.texture.microtexture_density_score, 13.0)


if __name__ == "__main__":
    unittest.main()
