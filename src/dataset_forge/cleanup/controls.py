from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from dataset_forge.cleanup.io import load_cleanup_plan
from dataset_forge.cleanup.models import CleanupAction

OVERRIDES_JSON = "user_overrides.json"
APPROVED_PLAN_JSON = "approved_cleanup_plan.json"
APPROVED_PLAN_CSV = "approved_cleanup_plan.csv"
AUDIT_LOG = "decision_audit_log.jsonl"

VALID_APPROVALS = {"proposed", "approved", "rejected"}


@dataclass(frozen=True)
class SelectionFilter:
    key: str
    value: str


class PlanControlError(ValueError):
    pass


class PlanControlManager:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path.expanduser().resolve()

    def override(
        self,
        selector: str | None,
        action: CleanupAction | str,
        *,
        filters: Iterable[SelectionFilter] = (),
        reason: str = "",
        command: str = "override",
    ) -> list[dict[str, Any]]:
        action_value = CleanupAction(action).value
        return self._mutate(
            selector,
            filters,
            command,
            reason,
            lambda control, _decision: control.update(
                {"override_action": action_value}
            ),
        )

    def lock(
        self,
        selector: str | None,
        action: CleanupAction | str | None = None,
        *,
        filters: Iterable[SelectionFilter] = (),
        reason: str = "",
    ) -> list[dict[str, Any]]:
        action_value = CleanupAction(action).value if action else None

        def apply(control: dict[str, Any], decision: Mapping[str, Any]) -> None:
            current_action = self._effective_action(decision, control)
            control["locked"] = True
            control["approval"] = "approved"
            if action_value:
                control["override_action"] = action_value
            control["locked_action"] = action_value or current_action

        return self._mutate(selector, filters, "lock", reason, apply)

    def unlock(self, selector: str, *, reason: str = "") -> list[dict[str, Any]]:
        def apply(control: dict[str, Any], _decision: Mapping[str, Any]) -> None:
            control["locked"] = False
            control.pop("locked_action", None)

        return self._mutate(
            selector,
            (),
            "unlock",
            reason,
            apply,
            allow_locked=True,
        )

    def approve(
        self,
        selector: str | None,
        *,
        filters: Iterable[SelectionFilter] = (),
        reason: str = "",
        command: str = "approve",
    ) -> list[dict[str, Any]]:
        return self._mutate(
            selector,
            filters,
            command,
            reason,
            lambda control, _decision: control.update({"approval": "approved"}),
            allow_locked=True,
        )

    def reject(
        self,
        selector: str | None,
        *,
        filters: Iterable[SelectionFilter] = (),
        reason: str = "",
    ) -> list[dict[str, Any]]:
        return self._mutate(
            selector,
            filters,
            "reject",
            reason,
            lambda control, _decision: control.update({"approval": "rejected"}),
        )

    def approve_all(self, *, reason: str = "") -> list[dict[str, Any]]:
        return self.approve(
            None,
            reason=reason,
            command="approve-all",
            filters=(SelectionFilter("all", "true"),),
        )

    def reset(self, *, reason: str = "") -> None:
        plan = load_cleanup_plan(self.output_path)
        controls = self.load_controls()
        decisions = self._decision_index(plan)
        for image_id, control in controls.items():
            decision = decisions.get(image_id)
            if decision:
                self._audit(
                    decision,
                    self._effective_action(decision, control),
                    str(decision["action"]),
                    "reset-overrides",
                    reason,
                )
        path = self.output_path / OVERRIDES_JSON
        if path.exists():
            path.unlink()
        self.write_approved_plan(plan, {})

    def load_controls(self) -> dict[str, dict[str, Any]]:
        path = self.output_path / OVERRIDES_JSON
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        decisions = data.get("decisions", {})
        if not isinstance(decisions, dict):
            raise PlanControlError("user_overrides.json has an invalid decisions map.")
        return {
            str(image_id): dict(control)
            for image_id, control in decisions.items()
            if isinstance(control, dict)
        }

    def effective_plan(self) -> dict[str, Any]:
        return self._merge(load_cleanup_plan(self.output_path), self.load_controls())

    def write_approved_plan(
        self,
        plan: Mapping[str, Any] | None = None,
        controls: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> tuple[Path, Path]:
        merged = self._merge(
            dict(plan) if plan is not None else load_cleanup_plan(self.output_path),
            controls if controls is not None else self.load_controls(),
        )
        self.output_path.mkdir(parents=True, exist_ok=True)
        json_path = self.output_path / APPROVED_PLAN_JSON
        csv_path = self.output_path / APPROVED_PLAN_CSV
        json_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        decisions = list(merged.get("decisions", []))
        fieldnames = list(decisions[0]) if decisions else [
            "image_id",
            "filename",
            "generated_action",
            "action",
            "status",
            "approval_status",
            "override_status",
            "locked",
            "execution_eligible",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for decision in decisions:
                row = dict(decision)
                row["warnings"] = " | ".join(row.get("warnings", []))
                writer.writerow(row)
        return json_path, csv_path

    def _mutate(
        self,
        selector: str | None,
        filters: Iterable[SelectionFilter],
        command: str,
        reason: str,
        mutation: Callable[[dict[str, Any], Mapping[str, Any]], None],
        *,
        allow_locked: bool = False,
    ) -> list[dict[str, Any]]:
        plan = load_cleanup_plan(self.output_path)
        controls = self.load_controls()
        matches = self.select(plan, selector, filters, controls)
        if not matches:
            raise PlanControlError("No cleanup-plan decisions matched the request.")
        changed: list[dict[str, Any]] = []
        for decision in matches:
            image_id = str(decision["image_id"])
            control = controls.setdefault(
                image_id,
                {
                    "image_id": image_id,
                    "filename": str(decision["filename"]),
                    "override_action": None,
                    "locked_action": None,
                    "approval": "proposed",
                    "locked": False,
                    "reason": "",
                },
            )
            if control.get("locked") and not allow_locked:
                raise PlanControlError(
                    f"{decision['filename']} is locked; unlock it before changing it."
                )
            previous = self._effective_action(decision, control)
            mutation(control, decision)
            control["reason"] = reason
            control["updated_at"] = _timestamp()
            current = self._effective_action(decision, control)
            self._audit(decision, previous, current, command, reason)
            changed.append(self._merge_decision(decision, control))
        self._save_controls(controls)
        self.write_approved_plan(plan, controls)
        return changed

    def select(
        self,
        plan: Mapping[str, Any],
        selector: str | None,
        filters: Iterable[SelectionFilter],
        controls: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        decisions = [
            dict(item)
            for item in plan.get("decisions", [])
            if isinstance(item, Mapping)
        ]
        if selector:
            matches = [
                item
                for item in decisions
                if str(item.get("image_id")) == selector
                or str(item.get("filename")) == selector
            ]
            if len(matches) > 1:
                raise PlanControlError(
                    f"Filename is ambiguous; use an image ID instead: {selector}"
                )
            if not matches:
                raise PlanControlError(f"Image not found in cleanup plan: {selector}")
            decisions = matches
        filter_list = list(filters)
        if not selector and not filter_list:
            raise PlanControlError("Provide an image or at least one filter.")
        evidence = self._evidence()
        active_controls = controls or {}
        return [
            decision
            for decision in decisions
            if all(
                self._matches_filter(
                    decision,
                    active_controls.get(str(decision.get("image_id")), {}),
                    item,
                    evidence,
                )
                for item in filter_list
            )
        ]

    def _matches_filter(
        self,
        decision: Mapping[str, Any],
        control: Mapping[str, Any],
        item: SelectionFilter,
        evidence: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        key = item.key.strip().lower()
        expected = item.value.strip()
        if key == "all":
            return True
        filename = str(decision.get("filename", ""))
        row = evidence.get(filename, {})
        if key == "filename_contains":
            return expected.lower() in filename.lower()
        if key == "action":
            return self._effective_action(decision, control) == expected.upper()
        if key == "severity":
            return str(row.get("severity", "")).upper() == expected.upper()
        comparisons = {
            "artifact_score": row.get("artifact_score"),
            "quality_score": row.get("overall_quality_score"),
            "texture_score": row.get("texture_score"),
            "confidence": decision.get("confidence"),
        }
        for suffix, comparator in (("_gt", lambda a, b: a > b), ("_lt", lambda a, b: a < b)):
            if key.endswith(suffix):
                field = key[: -len(suffix)]
                if field not in comparisons:
                    break
                try:
                    return comparator(float(comparisons[field]), float(expected))
                except (TypeError, ValueError):
                    return False
        raise PlanControlError(f"Unsupported filter: {item.key}")

    def _evidence(self) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        manifest = _latest_manifest(self.output_path)
        if manifest:
            with manifest.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    rows[str(row.get("filename", ""))] = dict(row)
        recommendations = self.output_path / "recommendations.csv"
        if recommendations.is_file():
            with recommendations.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    rows.setdefault(str(row.get("filename", "")), {}).update(row)
        return rows

    def _merge(
        self,
        plan: Mapping[str, Any],
        controls: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        merged = dict(plan)
        decisions = [
            self._merge_decision(
                dict(decision),
                controls.get(str(decision.get("image_id")), {}),
            )
            for decision in plan.get("decisions", [])
        ]
        resolved = sum(
            decision["approval_status"] in {"approved", "rejected"}
            or decision["locked"]
            for decision in decisions
        )
        merged["source_plan"] = "cleanup_plan.json"
        merged["approval_complete"] = resolved == len(decisions)
        merged["approved_count"] = sum(
            decision["approval_status"] == "approved" for decision in decisions
        )
        merged["rejected_count"] = sum(
            decision["approval_status"] == "rejected" for decision in decisions
        )
        merged["decisions"] = decisions
        return merged

    def _merge_decision(
        self,
        decision: Mapping[str, Any],
        control: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged = dict(decision)
        generated_action = str(decision.get("action", ""))
        action = self._effective_action(decision, control)
        approval = str(control.get("approval", "proposed"))
        if approval not in VALID_APPROVALS:
            approval = "proposed"
        overridden = bool(control.get("override_action"))
        locked = bool(control.get("locked"))
        if locked:
            status = "locked"
        elif overridden:
            status = "overridden"
        else:
            status = approval
        merged.update(
            {
                "generated_action": generated_action,
                "action": action,
                "status": status,
                "approval_status": approval,
                "override_status": overridden,
                "locked": locked,
                "execution_eligible": approval == "approved" or locked,
                "user_reason": str(control.get("reason", "")),
            }
        )
        return merged

    @staticmethod
    def _effective_action(
        decision: Mapping[str, Any],
        control: Mapping[str, Any],
    ) -> str:
        if control.get("locked") and control.get("locked_action"):
            return str(control["locked_action"])
        return str(control.get("override_action") or decision.get("action", ""))

    @staticmethod
    def _decision_index(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item["image_id"]): dict(item)
            for item in plan.get("decisions", [])
        }

    def _save_controls(self, controls: Mapping[str, Mapping[str, Any]]) -> None:
        self.output_path.mkdir(parents=True, exist_ok=True)
        path = self.output_path / OVERRIDES_JSON
        path.write_text(
            json.dumps({"version": 1, "decisions": controls}, indent=2) + "\n",
            encoding="utf-8",
        )

    def _audit(
        self,
        decision: Mapping[str, Any],
        previous_action: str,
        new_action: str,
        command: str,
        reason: str,
    ) -> None:
        record = {
            "timestamp": _timestamp(),
            "image_id": decision.get("image_id"),
            "filename": decision.get("filename"),
            "previous_action": previous_action,
            "new_action": new_action,
            "user_command": command,
            "reason": reason,
        }
        self.output_path.mkdir(parents=True, exist_ok=True)
        with (self.output_path / AUDIT_LOG).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def parse_filter(value: str) -> SelectionFilter:
    if "=" not in value:
        raise PlanControlError(f"Filter must use key=value syntax: {value}")
    key, expected = value.split("=", 1)
    if not key.strip() or not expected.strip():
        raise PlanControlError(f"Filter must use key=value syntax: {value}")
    return SelectionFilter(key.strip(), expected.strip())


def review_plan(
    manager: PlanControlManager,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> int:
    plan = manager.effective_plan()
    evidence = manager._evidence()
    reviewed = 0
    choices = {
        "k": CleanupAction.KEEP,
        "l": CleanupAction.CLEAN_LIGHT,
        "m": CleanupAction.CLEAN_MEDIUM,
        "s": CleanupAction.CLEAN_STRONG,
        "x": CleanupAction.EXCLUDE,
    }
    for decision in plan.get("decisions", []):
        row = evidence.get(str(decision.get("filename")), {})
        output_func(
            "\n".join(
                [
                    f"\nImage: {decision.get('filename')}",
                    f"Current action: {decision.get('action')}",
                    f"Quality score: {row.get('overall_quality_score', 'n/a')}",
                    f"Artifact score: {row.get('artifact_score', 'n/a')}",
                    f"Texture score: {row.get('texture_score', 'n/a')}",
                    f"Confidence: {decision.get('confidence')}",
                    f"Explanation: {decision.get('explanation')}",
                    f"Recommended plugin: {decision.get('recommended_plugin')}",
                    f"Estimated benefit: {decision.get('expected_benefit')}",
                ]
            )
        )
        choice = input_func(
            "[a] approve [k] keep [l] light [m] medium [s] strong "
            "[r] reject [x] exclude [n] next [q] quit: "
        ).strip().lower()
        image_id = str(decision["image_id"])
        if choice == "q":
            break
        if choice == "a":
            manager.approve(image_id, command="review-plan approve")
            reviewed += 1
        elif choice == "r":
            manager.reject(image_id, reason="Interactive review")
            reviewed += 1
        elif choice in choices:
            manager.override(
                image_id,
                choices[choice],
                reason="Interactive review",
                command="review-plan override",
            )
            manager.approve(
                image_id,
                reason="Interactive review",
                command="review-plan approve",
            )
            reviewed += 1
    return reviewed


def _latest_manifest(output_path: Path) -> Path | None:
    pointer = output_path / "manifest_latest.json"
    if pointer.is_file():
        data = json.loads(pointer.read_text(encoding="utf-8"))
        candidate = output_path / str(data.get("path", ""))
        if candidate.is_file():
            return candidate
    for name in ("manifest.csv", "manifest_v3.csv", "manifest_v2.csv", "manifest_v1.csv"):
        candidate = output_path / name
        if candidate.is_file():
            return candidate
    return None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
