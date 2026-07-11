from __future__ import annotations

import json
import shutil
from pathlib import Path

from schauwerk import runner
from schauwerk.cli_handlers import (
    handle_regie_context_compile,
    handle_regie_context_template,
    handle_regie_review,
)
from schauwerk.regie.model import load_regie_context, load_review_bundle

EVIDENCE = Path("docs/operators/evidence/sw009-live-executor-20260711")


def owner_copy(source: Path, destination: Path) -> Path:
    shutil.copyfile(source, destination)
    destination.chmod(0o600)
    return destination


def test_context_template_compile_and_review_handlers(tmp_path: Path) -> None:
    draft_path = tmp_path / "context-draft.json"
    context_path = tmp_path / "context.json"
    review_path = tmp_path / "review.json"
    template = handle_regie_context_template(
        review_id="regie-cli-test",
        title="CLI review",
        output=str(draft_path),
    )
    assert template["mutation_attempted"] is False
    assert draft_path.stat().st_mode & 0o077 == 0

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["summary"] = "Review one fixture operation without provider effect."
    draft["instructions"] = ["Inspect the source and decide the operation."]
    draft["sources"][0].update(
        {
            "title": "Repository main",
            "revision": "b54f3ef1",
            "freshness": "fresh",
            "visibility": "internal",
            "citation": "repo:schauwerk@b54f3ef1",
            "uncertainty": 0.02,
        }
    )
    draft["context"][0].update(
        {
            "label": "Scope",
            "value": "One managed fixture region",
        }
    )
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    draft_path.chmod(0o600)
    compiled = handle_regie_context_compile(
        draft_path=str(draft_path), output=str(context_path)
    )
    assert compiled["ok"] is True
    context = load_regie_context(context_path)
    assert context["review_id"] == "regie-cli-test"

    gate_path = owner_copy(EVIDENCE / "gate-receipt.json", tmp_path / "gate.json")
    bundle_path = owner_copy(
        EVIDENCE / "operation-bundle.json", tmp_path / "bundle.json"
    )
    receipt = handle_regie_review(
        context_path=str(context_path),
        gate_path=str(gate_path),
        bundle_path=str(bundle_path),
        output=str(review_path),
    )
    assert receipt["operation_count"] == 1
    assert receipt["mutation_attempted"] is False
    review = load_review_bundle(review_path)
    assert review["source_receipts"]["context_digest"] == context["context_digest"]


def test_runner_dispatches_regie_commands(monkeypatch, capsys) -> None:
    observed: dict[str, dict] = {}

    def fake_template(*, review_id, title, output):
        observed["template"] = {
            "review_id": review_id,
            "title": title,
            "output": output,
        }
        return {"ok": True}

    def fake_compile(*, draft_path, output):
        observed["compile"] = {"draft_path": draft_path, "output": output}
        return {"ok": True}

    def fake_review(*, context_path, gate_path, bundle_path, output):
        observed["review"] = {
            "context_path": context_path,
            "gate_path": gate_path,
            "bundle_path": bundle_path,
            "output": output,
        }
        return {"ok": True}

    def fake_serve(*, review_bundle, port, open_browser):
        observed["serve"] = {
            "review_bundle": review_bundle,
            "port": port,
            "open_browser": open_browser,
        }
        return {"ok": True, "loopback_only": True}

    monkeypatch.setattr(runner, "handle_regie_context_template", fake_template)
    monkeypatch.setattr(runner, "handle_regie_context_compile", fake_compile)
    monkeypatch.setattr(runner, "handle_regie_review", fake_review)
    monkeypatch.setattr(runner, "handle_regie_serve", fake_serve)

    assert (
        runner.main(
            [
                "regie",
                "context-template",
                "--review-id",
                "regie-test",
                "--title",
                "Review",
                "--output",
                "draft.json",
                "--json",
            ]
        )
        == 0
    )
    json.loads(capsys.readouterr().out)
    assert (
        runner.main(
            [
                "regie",
                "context-compile",
                "draft.json",
                "--output",
                "context.json",
                "--json",
            ]
        )
        == 0
    )
    json.loads(capsys.readouterr().out)
    assert (
        runner.main(
            [
                "regie",
                "review",
                "--context",
                "context.json",
                "--gate",
                "gate.json",
                "--bundle",
                "bundle.json",
                "--output",
                "review.json",
                "--json",
            ]
        )
        == 0
    )
    json.loads(capsys.readouterr().out)
    assert (
        runner.main(
            [
                "regie",
                "serve",
                "review.json",
                "--port",
                "8123",
                "--no-browser",
                "--json",
            ]
        )
        == 0
    )
    json.loads(capsys.readouterr().out)

    assert observed == {
        "template": {
            "review_id": "regie-test",
            "title": "Review",
            "output": "draft.json",
        },
        "compile": {"draft_path": "draft.json", "output": "context.json"},
        "review": {
            "context_path": "context.json",
            "gate_path": "gate.json",
            "bundle_path": "bundle.json",
            "output": "review.json",
        },
        "serve": {
            "review_bundle": "review.json",
            "port": 8123,
            "open_browser": False,
        },
    }
