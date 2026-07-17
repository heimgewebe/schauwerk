from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "companion-pages.yml"
CHECKOUT_ACTION = "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
SETUP_PYTHON_ACTION = (
    "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
)
CONFIGURE_PAGES_ACTION = (
    "actions/configure-pages@983d7736d9b0ae728b81ab479565c72886d7745b"
)
UPLOAD_PAGES_ACTION = (
    "actions/upload-pages-artifact@"
    "7b1f4a764d45c48632c6b24a0339c27f5614fb0b"
)
DEPLOY_PAGES_ACTION = (
    "actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e"
)


def _load_workflow() -> dict[str, object]:
    value = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_companion_pages_workflow_is_main_bound_and_least_privilege() -> None:
    workflow = _load_workflow()
    trigger = workflow[True]
    assert isinstance(trigger, dict)
    assert trigger["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in trigger
    assert "pyproject.toml" in trigger["push"]["paths"]
    assert "src/schauwerk/**" in trigger["push"]["paths"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "companion-pages",
        "cancel-in-progress": False,
    }


def test_companion_pages_workflow_builds_the_canonical_fixture() -> None:
    workflow = _load_workflow()
    jobs = workflow["jobs"]
    build = jobs["build"]
    steps = build["steps"]
    assert build["if"] == "github.ref == 'refs/heads/main'"
    commands = "\n".join(
        step.get("run", "") for step in steps if isinstance(step, dict)
    )
    assert "docs/operators/fixtures/miro-web-sdk-companion-v1.json" in commands
    assert "--output-dir _site" in commands
    assert "rm -f _site/_headers" in commands
    assert "touch _site/.nojekyll" in commands
    assert steps[0]["uses"] == CHECKOUT_ACTION
    assert steps[1]["uses"] == SETUP_PYTHON_ACTION
    assert build["permissions"] == {
        "contents": "read",
        "pages": "read",
    }
    assert steps[2]["uses"] == CONFIGURE_PAGES_ACTION
    upload = next(
        step for step in steps
        if step.get("uses") == UPLOAD_PAGES_ACTION
    )
    assert upload["with"]["path"] == "_site"


def test_companion_pages_workflow_deploys_only_the_built_artifact() -> None:
    workflow = _load_workflow()
    deploy = workflow["jobs"]["deploy"]
    assert deploy["needs"] == "build"
    assert deploy["if"] == "github.ref == 'refs/heads/main'"
    assert deploy["environment"]["name"] == "github-pages"
    assert deploy["permissions"] == {
        "pages": "write",
        "id-token": "write",
    }
    expected_url = chr(36) + "{{ steps.deployment.outputs.page_url }}"
    assert deploy["environment"]["url"] == expected_url
    assert deploy["steps"] == [
        {
            "name": "Deploy companion",
            "id": "deployment",
            "uses": DEPLOY_PAGES_ACTION,
        }
    ]
