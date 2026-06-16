import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_benchmark_defects.py"
GENERATED_NAMES = (
    "00_reference.png",
    "01_glitter_speckles.png",
    "02_recursive_microtexture.png",
    "03_crunchy_oversharpened.png",
    "04_color_noise.png",
    "05_mixed_artifacts.png",
)


class BenchmarkGeneratorTests(unittest.TestCase):
    def test_script_generates_deterministic_private_benchmark_set(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "private_reference.png"
            first_output = root / "first"
            second_output = root / "second"
            _write_reference(source)
            source_hash = _sha256(source)

            first = _run_generator(source, first_output, seed=77)
            second = _run_generator(source, second_output, seed=77)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(_sha256(source), source_hash)

            with Image.open(source) as opened:
                source_size = opened.size
            reference_hash = _sha256(first_output / "00_reference.png")
            for name in GENERATED_NAMES:
                first_path = first_output / name
                second_path = second_output / name
                self.assertTrue(first_path.is_file())
                with Image.open(first_path) as generated:
                    self.assertEqual(generated.size, source_size)
                self.assertEqual(_sha256(first_path), _sha256(second_path))
                if name != "00_reference.png":
                    self.assertNotEqual(_sha256(first_path), reference_hash)

            manifest_path = first_output / "benchmark_manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_image_path"], str(source.resolve()))
            self.assertEqual(manifest["source_image_hash"], source_hash)
            self.assertEqual(manifest["seed"], 77)
            self.assertEqual(manifest["strength"], "medium")
            self.assertEqual(len(manifest["generated_files"]), 6)
            self.assertTrue(manifest["timestamp"])
            for item in manifest["generated_files"]:
                self.assertIn("filename", item)
                self.assertIn("defect_type", item)
                self.assertIn("parameters", item)

    def test_gitignore_excludes_private_images_but_keeps_scaffolding(self) -> None:
        rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

        self.assertIn("benchmarks/reference/*", rules)
        self.assertIn("benchmarks/synthetic_defects/*", rules)
        self.assertIn("!benchmarks/reference/.gitkeep", rules)
        self.assertIn("!benchmarks/synthetic_defects/.gitkeep", rules)
        self.assertIn("!benchmarks/README.md", rules)
        self.assertTrue((ROOT / "benchmarks" / "reference" / ".gitkeep").is_file())
        self.assertTrue(
            (ROOT / "benchmarks" / "synthetic_defects" / ".gitkeep").is_file()
        )


def _run_generator(
    source: Path,
    output: Path,
    *,
    seed: int,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            "--seed",
            str(seed),
            "--strength",
            "medium",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_reference(path: Path) -> None:
    image = Image.new("RGB", (72, 56))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = (
                90 + (x * 130 // image.width),
                70 + (y * 150 // image.height),
                110 + ((x + y) * 90 // (image.width + image.height)),
            )
    image.save(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
