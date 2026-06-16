from __future__ import annotations

import json
from pathlib import Path

from dataset_forge.cleanup.controls import APPROVED_PLAN_JSON


class ApprovalRequiredError(RuntimeError):
    pass


def require_approved_plan(
    output_path: Path,
    *,
    yes: bool = False,
    force: bool = False,
) -> Path | None:
    if yes or force:
        return None
    path = output_path.expanduser().resolve() / APPROVED_PLAN_JSON
    if not path.is_file():
        raise ApprovalRequiredError(
            "An approved cleanup plan is required. Review and approve the plan "
            "or pass --yes/--force explicitly."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("approval_complete"):
        raise ApprovalRequiredError(
            "The approved cleanup plan is incomplete. Approve, reject, or lock "
            "every decision before expensive or destructive execution."
        )
    return path
