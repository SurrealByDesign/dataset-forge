from __future__ import annotations

import re
from pathlib import Path
import unittest

from dataset_forge import __version__


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_GUIDES = (
    "README.md",
    "docs/README.md",
    "docs/getting-started.md",
    "docs/philosophy.md",
    "docs/user-guide.md",
    "docs/review-desk-guide.md",
    "docs/improvement-preview-guide.md",
    "docs/provider-overview.md",
    "docs/developer-guide.md",
    "docs/json-schema-guide.md",
    "docs/faq.md",
    "docs/troubleshooting.md",
    "docs/terminology.md",
)
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _maintained_markdown() -> list[Path]:
    paths = list(ROOT.glob("*.md"))
    paths.extend((ROOT / "docs").rglob("*.md"))
    paths.extend((ROOT / "benchmarks").glob("README.md"))
    paths.extend((ROOT / "benchmarks" / "real_world").glob("README.md"))
    paths.extend((ROOT / "scripts" / "research").glob("README.md"))
    return sorted(set(paths))


class DocumentationTests(unittest.TestCase):
    def test_required_guides_exist(self) -> None:
        missing = [path for path in REQUIRED_GUIDES if not (ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_local_markdown_links_resolve(self) -> None:
        broken: list[str] = []
        for source in _maintained_markdown():
            text = source.read_text(encoding="utf-8")
            for raw_target in LINK_PATTERN.findall(text):
                target = raw_target.strip()
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path_text = target.split("#", 1)[0]
                if path_text and not (source.parent / path_text).resolve().exists():
                    broken.append(f"{source.relative_to(ROOT)} -> {path_text}")
        self.assertEqual(broken, [])

    def test_current_release_version_is_synchronized_in_public_docs(self) -> None:
        for relative in ("README.md", "CURRENT_STATUS.md", "CHANGELOG.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(__version__, text, relative)


if __name__ == "__main__":
    unittest.main()

