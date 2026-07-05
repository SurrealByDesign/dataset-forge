from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    ReviewDecisionValue,
    load_review_decisions,
    parse_review_decisions,
    write_review_decisions_json,
)


def _decisions() -> dict:
    return {
        "schema": REVIEW_DECISIONS_SCHEMA,
        "decisions": [
            {
                "image_path": "b.png",
                "decision": "LOCKED",
                "reason": "Do not touch original character sheet.",
            },
            {
                "image_path": "a.png",
                "category": "artifact.crystalline_faceting",
                "analyzer": "crystalline_faceting_analyzer/v1",
                "decision": "CONFIRMED_ARTIFACT",
            },
            {
                "image_path": "a.png",
                "category": "texture.high_microtexture",
                "analyzer": "texture_analyzer/v1",
                "decision": "FALSE_POSITIVE",
            },
            {
                "image_path": "c.png",
                "category": "artifact.oversharpening_halo",
                "analyzer": "oversharpening_halo_analyzer/v1",
                "decision": "NEEDS_REVIEW",
            },
            {
                "image_path": "d.png",
                "decision": "IGNORE",
            },
        ],
    }


class ReviewDecisionParsingTests(unittest.TestCase):
    def test_valid_decision_file_parses_and_sorts_deterministically(self) -> None:
        decisions = parse_review_decisions(_decisions())

        self.assertEqual(decisions.schema, REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(len(decisions.decisions), 5)
        self.assertEqual(
            [decision.image_path for decision in decisions.decisions],
            ["a.png", "a.png", "b.png", "c.png", "d.png"],
        )

    def test_rejects_wrong_schema(self) -> None:
        raw = _decisions()
        raw["schema"] = "dataset-forge/review-decisions/v99"

        with self.assertRaises(ValueError):
            parse_review_decisions(raw)

    def test_rejects_unknown_decision_value(self) -> None:
        raw = _decisions()
        raw["decisions"][0]["decision"] = "AUTO_REPAIR"

        with self.assertRaises(ValueError):
            parse_review_decisions(raw)

    def test_rejects_unknown_future_fields(self) -> None:
        raw = _decisions()
        raw["decisions"][0]["future_field"] = "not yet"

        with self.assertRaises(ValueError):
            parse_review_decisions(raw)

    def test_allows_pending_template_entries_with_recommendation_and_notes(self) -> None:
        decisions = parse_review_decisions({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": [
                {
                    "image_path": "image.png",
                    "recommendation": "Needs Review",
                    "decision": None,
                    "notes": "",
                },
            ],
        })

        self.assertIsNone(decisions.decisions[0].decision)
        self.assertEqual(decisions.decisions[0].recommendation, "Needs Review")
        self.assertEqual(decisions.summary().to_dict()["total_decisions"], 0)

    def test_rejects_duplicate_image_scope(self) -> None:
        raw = _decisions()
        raw["decisions"].append({
            "image_path": "b.png",
            "decision": "IGNORE",
        })

        with self.assertRaises(ValueError):
            parse_review_decisions(raw)

    def test_rejects_duplicate_image_category_scope(self) -> None:
        raw = _decisions()
        raw["decisions"].append({
            "image_path": "a.png",
            "category": "texture.high_microtexture",
            "decision": "ACCEPTABLE_STYLE",
        })

        with self.assertRaises(ValueError):
            parse_review_decisions(raw)


class ReviewDecisionHelperTests(unittest.TestCase):
    def test_image_level_decision_matching_and_locked_helper(self) -> None:
        decisions = parse_review_decisions(_decisions())

        self.assertEqual(
            decisions.decision_for("b.png").decision,
            ReviewDecisionValue.LOCKED.value,
        )
        self.assertTrue(decisions.is_image_locked("b.png"))
        self.assertTrue(decisions.should_exclude_from_future_action("b.png"))

    def test_category_level_helpers_match_findings(self) -> None:
        decisions = parse_review_decisions(_decisions())

        self.assertTrue(
            decisions.is_finding_confirmed(
                "a.png",
                "artifact.crystalline_faceting",
            )
        )
        self.assertTrue(
            decisions.is_finding_false_positive(
                "a.png",
                "texture.high_microtexture",
            )
        )
        self.assertFalse(
            decisions.is_finding_confirmed(
                "a.png",
                "texture.high_microtexture",
            )
        )

    def test_decision_for_finding_accepts_dict_and_prefers_category_scope(self) -> None:
        decisions = parse_review_decisions({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": [
                {
                    "image_path": "image.png",
                    "decision": "NEEDS_REVIEW",
                },
                {
                    "image_path": "image.png",
                    "category": "artifact.high_frequency_isolated",
                    "decision": "FALSE_POSITIVE",
                },
            ],
        })

        decision = decisions.decision_for_finding({
            "image_path": "image.png",
            "category": "artifact.high_frequency_isolated",
        })

        self.assertEqual(decision.decision, ReviewDecisionValue.FALSE_POSITIVE.value)

    def test_ignore_and_acceptable_style_exclude_future_action(self) -> None:
        decisions = parse_review_decisions({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": [
                {
                    "image_path": "style.png",
                    "category": "artifact.oversharpening_halo",
                    "decision": "ACCEPTABLE_STYLE",
                },
                {
                    "image_path": "ignored.png",
                    "decision": "IGNORE",
                },
                {
                    "image_path": "confirmed.png",
                    "category": "artifact.crystalline_faceting",
                    "decision": "CONFIRMED_ARTIFACT",
                },
            ],
        })

        self.assertTrue(
            decisions.should_exclude_from_future_action(
                "style.png",
                "artifact.oversharpening_halo",
            )
        )
        self.assertTrue(decisions.should_exclude_from_future_action("ignored.png"))
        self.assertFalse(
            decisions.should_exclude_from_future_action(
                "confirmed.png",
                "artifact.crystalline_faceting",
            )
        )

    def test_summary_counts_are_deterministic_and_json_serializable(self) -> None:
        summary = parse_review_decisions(_decisions()).summary()
        payload = summary.to_dict()

        self.assertEqual(payload["total_decisions"], 5)
        self.assertEqual(payload["counts_by_decision"]["CONFIRMED_ARTIFACT"], 1)
        self.assertEqual(payload["counts_by_decision"]["FALSE_POSITIVE"], 1)
        self.assertEqual(payload["counts_by_decision"]["ACCEPTABLE_STYLE"], 0)
        self.assertEqual(
            payload["counts_by_analyzer"],
            {
                "crystalline_faceting_analyzer/v1": 1,
                "oversharpening_halo_analyzer/v1": 1,
                "texture_analyzer/v1": 1,
            },
        )
        self.assertEqual(payload["counts_by_category"]["texture.high_microtexture"], 1)
        self.assertEqual(payload["locked_image_count"], 1)
        self.assertEqual(payload["ignored_image_count"], 1)
        self.assertEqual(payload["unresolved_review_count"], 1)
        self.assertIn("counts_by_decision", json.loads(json.dumps(payload)))


class ReviewDecisionFileTests(unittest.TestCase):
    def test_file_api_loads_and_writes_normalized_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "review_decisions.json"
            output = root / "normalized_review_decisions.json"
            source.write_text(json.dumps(_decisions()), encoding="utf-8")

            decisions = load_review_decisions(source)
            write_review_decisions_json(decisions, output)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(payload["decisions"][0]["image_path"], "a.png")


if __name__ == "__main__":
    unittest.main()
