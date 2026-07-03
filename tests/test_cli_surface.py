import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from dataset_forge.cli import main


class PublicCliSurfaceTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_root_help_exposes_only_alpha_surface(self) -> None:
        exit_code, stdout, stderr = self._run(["--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Dataset Forge v0.4.0-alpha", stdout)
        self.assertIn("inspect", stdout)
        self.assertIn("--help", stdout)
        self.assertIn("--version", stdout)
        for hidden in (
            "cleanup",
            "plugins",
            "export",
            "texture-report",
            "health-report",
            "run",
            "resume",
            "simulate",
        ):
            self.assertNotIn(hidden, stdout)

    def test_inspect_help_is_read_only_alpha_help(self) -> None:
        exit_code, stdout, stderr = self._run(["inspect", "--help"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dataset-forge inspect", stdout)
        self.assertIn("Dataset ->", stdout)
        self.assertIn("DatasetContext -> Analyzer -> Finding -> Report", stdout)
        self.assertIn("--output", stdout)
        self.assertIn("--gallery", stdout)
        self.assertNotIn("cleanup", stdout.lower())
        self.assertNotIn("export", stdout.lower())

    def test_version_is_public(self) -> None:
        exit_code, stdout, stderr = self._run(["--version"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.strip(), "dataset-forge 0.4.0a0")

    def test_future_commands_are_not_public(self) -> None:
        for command in (
            "run",
            "resume",
            "simulate",
            "plugins",
            "texture-report",
            "health-report",
            "plan",
            "execute-plan",
            "traditional-cleanup",
        ):
            with self.subTest(command=command):
                exit_code, stdout, stderr = self._run([command, "--help"])

                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("not part of the public v0.4.0-alpha CLI", stderr)


if __name__ == "__main__":
    unittest.main()
