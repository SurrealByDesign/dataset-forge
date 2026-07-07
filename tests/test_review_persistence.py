from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.recommendation_summary import build_recommendation_summary
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA, parse_review_decisions
from dataset_forge.review_persistence import (
    REVIEW_DECISIONS_TEMPLATE_FILENAME,
    review_status_by_image,
    write_review_decisions_template_if_absent,
)


def _context() -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
        image_paths=(Path("img_0.png"), Path("img_1.png")),
        image_count=2,
        error_count=0,
        resolution_stats=ResolutionStats.empty(),
        aspect_ratio_stats=AspectRatioStats.empty(),
        texture_distributions=TextureDistributions.empty(),
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


class ReviewPersistenceTests(unittest.TestCase):
    def test_template_is_generated_with_pending_decisions(self) -> None:
        summary = build_recommendation_summary([], _context())
        with tempfile.TemporaryDirectory() as tmp:
            path = write_review_decisions_template_if_absent(summary, Path(tmp))
            assert path is not None
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(len(payload["decisions"]), 2)
        self.assertEqual(payload["decisions"][0]["recommendation"], "No Findings Emitted")
        self.assertIsNone(payload["decisions"][0]["decision"])
        self.assertIn("notes", payload["decisions"][0])
        parse_review_decisions(payload)

    def test_existing_template_is_never_overwritten(self) -> None:
        summary = build_recommendation_summary([], _context())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / REVIEW_DECISIONS_TEMPLATE_FILENAME
            template.write_text("human draft\n", encoding="utf-8")

            written = write_review_decisions_template_if_absent(summary, root)

            self.assertIsNone(written)
            self.assertEqual(template.read_text(encoding="utf-8"), "human draft\n")

    def test_review_status_marks_real_decision_as_already_reviewed(self) -> None:
        summary = build_recommendation_summary([], _context())
        decisions = parse_review_decisions({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": [
                {
                    "image_path": "img_0.png",
                    "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                    "workflow_state": "REVIEWED",
                },
                {
                    "image_path": "img_1.png",
                    "decision": None,
                    "workflow_state": "IN_DATASET",
                    "recommendation": "No Findings Emitted",
                    "notes": "",
                },
            ],
        })

        statuses = review_status_by_image(summary, decisions)

        self.assertEqual(statuses["img_0.png"].status, "Already Reviewed")
        self.assertEqual(statuses["img_0.png"].decisions, ("Accepted Style / False Positive",))
        self.assertEqual(statuses["img_1.png"].status, "Pending Review")
        self.assertEqual(statuses["img_1.png"].decisions, ())


if __name__ == "__main__":
    unittest.main()
