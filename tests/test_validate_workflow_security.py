from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"
CHECKOUT_ACTION = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_ACTION = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


def test_validate_workflow_is_least_privilege_and_sha_pinned() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["validate"]["steps"]
    uses = [step["uses"] for step in steps if isinstance(step, dict) and "uses" in step]
    assert uses == [CHECKOUT_ACTION, SETUP_PYTHON_ACTION]
    assert all(PINNED_ACTION.fullmatch(action) for action in uses)
