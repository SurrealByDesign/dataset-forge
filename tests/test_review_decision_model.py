from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    REVIEW_DECISIONS_SCHEMA_V1,
    ReviewDecisionValue,
    ReviewWorkflowState,
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
                "decision": "KEEP",
                "workflow_state": "REVIEWED",
                "reason": "Keep original character sheet.",
            },
            {
                "image_path": "a.png",
                "decision": "IMPROVEMENT_CANDIDATE",
                "workflow_state": "QUARANTINE_PLANNED",
                "notes": "visible artifact",
            },
            {
                "image_path": "c.png",
                "decision": "UNDECIDED",
                "workflow_state": "IN_DATASET",
            },
        ],
    }


class ReviewDecisionParsingTests(unittest.TestCase):
    def test_valid_v2_decision_file_parses_and_sorts_deterministically(self) -> None:
        decisions = parse_review_decisions(_decisions())

        self.assertEqual(decisions.schema, REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(
            [decision.image_path for decision in decisions.decisions],
            ["a.png", "b.png", "c.png"],
        )
        self.assertEqual(
            decisions.decisions[0].decision,
            ReviewDecisionValue.IMPROVEMENT_CANDIDATE.value,
        )
        self.assertEqual(
            decisions.decisions[0].workflow_state,
            ReviewWorkflowState.QUARANTINE_PLANNED.value,
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

    def test_rejects_unknown_workflow_state(self) -> None:
        raw = _decisions()
        raw["decisions"][0]["workflow_state"] = "MOVED_TO_QUARANTINE"

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
                    "workflow_state": "IN_DATASET",
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
            "decision": "KEEP",
            "workflow_state": "REVIEWED",
        })

        with self.assertRaises(ValueError):
            parse_review_decisions(raw)


class ReviewDecisionMigrationTests(unittest.TestCase):
    def test_v1_finding_scoped_decisions_migrate_to_v2_image_scope(self) -> None:
        decisions = parse_review_decisions({
            "schema": REVIEW_DECISIONS_SCHEMA_V1,
            "decisions": [
                {
                    "image_path": "a.png",
                    "category": "artifact.crystalline_faceting",
                    "analyzer": "crystalline_faceting_analyzer/v1",
                    "decision": "CONFIRMED_ARTIFACT",
                    "notes": "visible facets",
                },
                {
                    "image_path": "a.png",
                    "category": "texture.high_microtexture",
                    "analyzer": "texture_analyzer/v1",
                    "decision": "FALSE_POSITIVE",
                    "notes": "style grain",
                },
                {
                    "image_path": "b.png",
                    "decision": "LOCKED",
                },
            ],
        })

        self.assertEqual(decisions.schema, REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(len(decisions.decisions), 2)
        first = decisions.decision_for("a.png")
        assert first is not None
        self.assertEqual(first.decision, "IMPROVEMENT_CANDIDATE")
        self.assertEqual(first.workflow_state, "REVIEWED")
        self.assertIn("visible facets", first.notes)
        self.assertIn("style grain", first.notes)
        self.assertEqual(len(first.decision_history), 2)
        second = decisions.decision_for("b.png")
        assert second is not None
        self.assertEqual(second.decision, "KEEP")


class ReviewDecisionHelperTests(unittest.TestCase):
    def test_image_level_matching_and_future_action_helpers(self) -> None:
        decisions = parse_review_decisions(_decisions())

        self.assertEqual(
            decisions.decision_for("b.png").decision,
            ReviewDecisionValue.KEEP.value,
        )
        self.assertTrue(decisions.should_exclude_from_future_action("b.png"))
        self.assertFalse(decisions.should_exclude_from_future_action("a.png"))

    def test_finding_helpers_use_image_level_decision(self) -> None:
        decisions = parse_review_decisions(_decisions())

        self.assertTrue(
            decisions.is_finding_confirmed(
                "a.png",
                "artifact.crystalline_faceting",
            )
        )
        self.assertFalse(
            decisions.is_finding_false_positive(
                "a.png",
                "texture.high_microtexture",
            )
        )

    def test_accepted_style_false_positive_excludes_future_action(self) -> None:
        decisions = parse_review_decisions({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": [
                {
                    "image_path": "style.png",
                    "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                    "workflow_state": "REVIEWED",
                },
                {
                    "image_path": "candidate.png",
                    "decision": "REMOVAL_CANDIDATE",
                    "workflow_state": "QUARANTINE_PLANNED",
                },
            ],
        })

        self.assertTrue(decisions.should_exclude_from_future_action("style.png"))
        self.assertFalse(decisions.should_exclude_from_future_action("candidate.png"))

    def test_summary_counts_are_deterministic_and_json_serializable(self) -> None:
        summary = parse_review_decisions(_decisions()).summary()
        payload = summary.to_dict()

        self.assertEqual(payload["total_decisions"], 3)
        self.assertEqual(payload["counts_by_decision"]["KEEP"], 1)
        self.assertEqual(payload["counts_by_decision"]["IMPROVEMENT_CANDIDATE"], 1)
        self.assertEqual(payload["counts_by_decision"]["UNDECIDED"], 1)
        self.assertEqual(payload["counts_by_workflow_state"]["REVIEWED"], 1)
        self.assertEqual(payload["counts_by_workflow_state"]["QUARANTINE_PLANNED"], 1)
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
