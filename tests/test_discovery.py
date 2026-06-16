import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dataset_forge.discovery import discover_images


class DiscoveryTests(unittest.TestCase):
    def test_discovers_supported_images_case_insensitively(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.JPG").touch()
            (root / "two.webp").touch()
            (root / "notes.txt").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "three.png").touch()

            flat = discover_images(root, recursive=False)
            recursive = discover_images(root, recursive=True)

            self.assertEqual([path.name for path in flat.images], ["one.JPG", "two.webp"])
            self.assertEqual(flat.skipped_files, 1)
            self.assertEqual(
                [path.name for path in recursive.images],
                ["three.png", "one.JPG", "two.webp"],
            )
            self.assertEqual(recursive.skipped_files, 1)

    def test_discovery_limit_is_deterministic(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("c.png", "a.png", "b.png"):
                (root / name).touch()

            result = discover_images(root, recursive=False, limit=2)

            self.assertEqual([path.name for path in result.images], ["a.png", "b.png"])


if __name__ == "__main__":
    unittest.main()
