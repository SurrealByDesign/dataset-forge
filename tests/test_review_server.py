from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA
from dataset_forge.review_server import (
    LOCAL_REVIEW_HOST,
    ReviewServerError,
    atomic_write_json,
    build_review_data,
    create_review_server,
    load_review_workspace,
    update_review_decision,
)


def _write_workspace(root: Path) -> tuple[Path, Path]:
    output = root / "inspect_output"
    output.mkdir()
    image = root / "priority.png"
    ready = root / "ready.png"
    Image.fromarray(np.full((24, 24, 3), 128, dtype=np.uint8)).save(image)
    Image.fromarray(np.full((24, 24, 3), 64, dtype=np.uint8)).save(ready)
    (output / "inspection_report.json").write_text(
        json.dumps({
            "schema": "dataset-forge/inspection/v1",
            "dataset_path": str(root),
            "findings": [],
        }),
        encoding="utf-8",
    )
    (output / "recommendation_summary.json").write_text(
        json.dumps({
            "schema": "dataset-forge/recommendation-summary/v1",
            "source_report_schema": "dataset-forge/inspection/v1",
            "summary": {
                "image_count": 2,
                "ready_for_training_count": 1,
                "needs_review_count": 0,
                "priority_review_count": 1,
                "analyzer_error_count": 0,
            },
            "recommendations": [
                {
                    "image_path": str(image),
                    "recommendation": "PRIORITY_REVIEW",
                    "display_label": "Priority Review",
                    "primary_reason": "High-severity finding detected.",
                    "reason_codes": ["finding.high_severity"],
                    "finding_refs": [
                        {
                            "analyzer": "texture_analyzer/v1",
                            "category": "artifact.texture",
                            "severity": "HIGH",
                        },
                        {
                            "analyzer": "oversharpening_halo_analyzer/v1",
                            "category": "artifact.oversharpening_halo",
                            "severity": "MEDIUM",
                        },
                    ],
                    "guidance": "Review this image early before training.",
                    "confidence_note": "Recommendations are advisory.",
                },
                {
                    "image_path": str(ready),
                    "recommendation": "READY_FOR_TRAINING",
                    "display_label": "No Findings Emitted",
                    "primary_reason": "No findings were emitted for this image.",
                    "reason_codes": ["no_findings"],
                    "finding_refs": [],
                    "guidance": "No current evidence requiring review.",
                    "confidence_note": "Recommendations are advisory.",
                },
            ],
        }),
        encoding="utf-8",
    )
    return output, image


class ReviewServerDataTests(unittest.TestCase):
    def test_requires_inspection_and_recommendation_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ReviewServerError):
                load_review_workspace(Path(tmp))

    def test_builds_rows_from_flagged_recommendations_only(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))

            data = build_review_data(output)

        self.assertEqual(data["summary"]["review_row_count"], 2)
        self.assertEqual(data["summary"]["pending_review_count"], 2)
        self.assertEqual(
            {row["category"] for row in data["rows"]},
            {"artifact.texture", "artifact.oversharpening_halo"},
        )
        self.assertNotIn("ready.png", json.dumps(data))

    def test_existing_decisions_load_into_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            (output / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [
                        {
                            "image_path": str(image),
                            "category": "artifact.texture",
                            "analyzer": "texture_analyzer/v1",
                            "decision": "ACCEPTABLE_STYLE",
                            "notes": "intentional style",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            data = build_review_data(output)

        texture = [
            row for row in data["rows"]
            if row["category"] == "artifact.texture"
        ][0]
        self.assertEqual(texture["current_decision"], "ACCEPTABLE_STYLE")
        self.assertEqual(texture["notes"], "intentional style")

    def test_post_update_writes_review_decisions_json(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))

            update_review_decision(output, {
                "image_path": str(image),
                "category": "artifact.texture",
                "analyzer": "texture_analyzer/v1",
                "recommendation": "Priority Review",
                "decision": "CONFIRMED_ARTIFACT",
                "notes": "visible artifact",
            })
            payload = json.loads((output / "review_decisions.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(payload["decisions"][0]["decision"], "CONFIRMED_ARTIFACT")
        self.assertEqual(payload["decisions"][0]["notes"], "visible artifact")

    def test_same_scope_decision_updates_and_unrelated_decisions_are_preserved(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            (output / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [
                        {
                            "image_path": str(image),
                            "category": "artifact.texture",
                            "analyzer": "texture_analyzer/v1",
                            "decision": "NEEDS_REVIEW",
                        },
                        {
                            "image_path": "unmatched.png",
                            "decision": "LOCKED",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            update_review_decision(output, {
                "image_path": str(image),
                "category": "artifact.texture",
                "analyzer": "texture_analyzer/v1",
                "decision": "FALSE_POSITIVE",
                "notes": "not an artifact",
            })
            payload = json.loads((output / "review_decisions.json").read_text(encoding="utf-8"))

        self.assertEqual(len(payload["decisions"]), 2)
        self.assertIn("LOCKED", json.dumps(payload))
        self.assertIn("FALSE_POSITIVE", json.dumps(payload))
        self.assertNotIn("NEEDS_REVIEW", json.dumps(payload))

    def test_duplicate_existing_decisions_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            duplicate = {
                "image_path": str(image),
                "category": "artifact.texture",
                "analyzer": "texture_analyzer/v1",
                "decision": "NEEDS_REVIEW",
            }
            (output / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [duplicate, dict(duplicate)],
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_review_workspace(output)

    def test_invalid_decision_and_notes_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            with self.assertRaises(ReviewServerError):
                update_review_decision(output, {
                    "image_path": str(image),
                    "category": "artifact.texture",
                    "analyzer": "texture_analyzer/v1",
                    "decision": "AUTO_FIX",
                })
            with self.assertRaises(ReviewServerError):
                update_review_decision(output, {
                    "image_path": str(image),
                    "category": "artifact.texture",
                    "analyzer": "texture_analyzer/v1",
                    "decision": "NEEDS_REVIEW",
                    "notes": ["not", "plain", "text"],
                })

    def test_atomic_write_helper_replaces_json(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_decisions.json"
            atomic_write_json(path, {"schema": REVIEW_DECISIONS_SCHEMA, "decisions": []})

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["schema"],
                REVIEW_DECISIONS_SCHEMA,
            )
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_updates_do_not_modify_source_or_existing_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            image_before = image.read_bytes()
            report = output / "inspection_report.json"
            summary = output / "recommendation_summary.json"
            report_before = report.read_text(encoding="utf-8")
            summary_before = summary.read_text(encoding="utf-8")

            update_review_decision(output, {
                "image_path": str(image),
                "category": "artifact.texture",
                "analyzer": "texture_analyzer/v1",
                "decision": "NEEDS_REVIEW",
                "notes": "",
            })

            self.assertEqual(image.read_bytes(), image_before)
            self.assertEqual(report.read_text(encoding="utf-8"), report_before)
            self.assertEqual(summary.read_text(encoding="utf-8"), summary_before)


class ReviewServerHttpTests(unittest.TestCase):
    def test_server_binds_only_to_localhost(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))
            with self.assertRaises(ReviewServerError):
                create_review_server(output, host="0.0.0.0", port=0)

    def test_get_serves_html_and_data(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
                data = json.loads(
                    urllib.request.urlopen(base + "/api/review-data", timeout=5)
                    .read()
                    .decode("utf-8")
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("Dataset Forge Review Decisions", html)
        self.assertIn("review_decisions.json", html)
        for forbidden in ("cleanup", "repair", "export", "<form", "localStorage"):
            self.assertNotIn(forbidden, html)
        self.assertEqual(data["summary"]["review_row_count"], 2)

    def test_post_writes_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                request = urllib.request.Request(
                    base + "/api/decision",
                    data=json.dumps({
                        "image_path": str(image),
                        "category": "artifact.texture",
                        "analyzer": "texture_analyzer/v1",
                        "decision": "LOCKED",
                        "notes": "approved by human",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                response = urllib.request.urlopen(request, timeout=5)
                data = json.loads(response.read().decode("utf-8"))
                payload = json.loads(
                    (output / "review_decisions.json").read_text(encoding="utf-8")
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(data["summary"]["already_reviewed_count"], 1)
        self.assertEqual(payload["decisions"][0]["decision"], "LOCKED")

    def test_post_rejects_invalid_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                request = urllib.request.Request(
                    base + "/api/decision",
                    data=json.dumps({
                        "image_path": str(image),
                        "category": "artifact.texture",
                        "analyzer": "texture_analyzer/v1",
                        "decision": "AUTO_FIX",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
