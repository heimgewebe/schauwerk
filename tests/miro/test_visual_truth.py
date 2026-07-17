from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import schauwerk.cli_handlers as cli_handlers
from schauwerk.runner import main
from schauwerk.surfaces.miro.board_registry import BoardAllowlist, reference_digest
from schauwerk.surfaces.miro.snapshot_model import content_digest as snapshot_content_digest
from schauwerk.surfaces.miro.visual_truth import (
    VisualTruthError,
    check_visual_truth_receipt,
    create_visual_truth_receipt,
)

NOW = datetime(2026, 7, 17, 5, 0, tzinfo=UTC)
ALIAS = "operator-system-map-showcase-20260714"
BOARD_URL = "https://miro.com/app/board/uXjVTestBoardIdentity=/"
REFERENCE = reference_digest(BOARD_URL)
SNAPSHOT_CONTENT = {
    "schema_version": 1,
    "board_alias": ALIAS,
    "items": [],
    "comments": [],
}
CONTENT = snapshot_content_digest(SNAPSHOT_CONTENT)


def _png(width: int = 1280, height: int = 720) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _snapshot(path: Path, **changes: object) -> Path:
    value = {
        **SNAPSHOT_CONTENT,
        "repeatability_verified": True,
        "sanitized_references": True,
        "verified_reads": 2,
    }
    value.update(changes)
    if "content_digest" not in changes:
        value["content_digest"] = snapshot_content_digest(
            {
                "schema_version": value.get("schema_version"),
                "board_alias": value.get("board_alias"),
                "items": value.get("items"),
                "comments": value.get("comments"),
            }
        )
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _context(path: Path, **changes: object) -> Path:
    value = {
        "schema_version": "schauwerk-miro-visual-truth-context.v1",
        "provider": "miro",
        "page_kind": "board",
        "authenticated": True,
        "board_alias": ALIAS,
        "board_reference_digest": REFERENCE,
        "board_content_digest": CONTENT,
        "provider_url": BOARD_URL,
        "captured_at": "2026-07-17T04:55:00Z",
        "capture_tool": "authenticated-browser-capture",
        "operator_attestation": (
            "I observed the allowlisted Miro board in an authenticated provider session."
        ),
        "visible_board_markers": [
            "01 Systemkarte des Operator-Oekosystems",
            "Schauwerk Representation Router",
        ],
    }
    value.update(changes)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _capture(path: Path, payload: bytes | None = None) -> Path:
    path.write_bytes(payload or _png())
    return path


def test_visual_truth_receipt_binds_snapshot_capture_context_and_allowlist(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "snapshot.json")
    capture = _capture(tmp_path / "capture.png")
    context = _context(tmp_path / "context.json")
    output = tmp_path / "receipt.json"

    result = create_visual_truth_receipt(
        snapshot=snapshot,
        capture=capture,
        context=context,
        expected_board_reference_digest=REFERENCE,
        output=output,
        now=NOW,
    )

    assert result["success"] is True
    assert result["capture"]["media_type"] == "image/png"
    assert result["capture"]["width"] == 1280
    assert result["capture"]["height"] == 720
    assert result["evidence_strength"]["cryptographic_provider_attestation"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    encoded = output.read_text(encoding="utf-8")
    assert BOARD_URL not in encoded
    assert "uXjVTestBoardIdentity" not in encoded
    assert check_visual_truth_receipt(receipt=output)["receipt_digest"] == result["receipt_digest"]
    with pytest.raises(VisualTruthError, match="already exists"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=capture,
            context=context,
            expected_board_reference_digest=REFERENCE,
            output=output,
            now=NOW,
        )


def test_visual_truth_rejects_unverified_or_mismatched_snapshot(tmp_path: Path) -> None:
    capture = _capture(tmp_path / "capture.png")
    context = _context(tmp_path / "context.json")
    with pytest.raises(VisualTruthError, match="repeatability"):
        create_visual_truth_receipt(
            snapshot=_snapshot(tmp_path / "snapshot.json", repeatability_verified=False),
            capture=capture,
            context=context,
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "receipt.json",
            now=NOW,
        )

    _snapshot(tmp_path / "snapshot-two.json")
    _context(tmp_path / "context-two.json", board_content_digest="e" * 64)
    with pytest.raises(VisualTruthError, match="content digest"):
        create_visual_truth_receipt(
            snapshot=tmp_path / "snapshot-two.json",
            capture=capture,
            context=tmp_path / "context-two.json",
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "receipt-two.json",
            now=NOW,
        )


def test_visual_truth_rejects_snapshot_content_tampering(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "snapshot.json")
    value = json.loads(snapshot.read_text(encoding="utf-8"))
    value["items"] = [{"ref": "tampered", "type": "shape"}]
    snapshot.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(VisualTruthError, match="does not match its content"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=_capture(tmp_path / "capture.png"),
            context=_context(tmp_path / "context.json"),
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "receipt.json",
            now=NOW,
        )


def test_visual_truth_rejects_login_access_error_and_wrong_board_reference(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "snapshot.json")
    capture = _capture(tmp_path / "capture.png")
    bad = _context(
        tmp_path / "bad.json",
        visible_board_markers=["Sign in to Miro", "Request access"],
    )
    with pytest.raises(VisualTruthError, match="non-board page"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=capture,
            context=bad,
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "bad-receipt.json",
            now=NOW,
        )

    mismatched_url = _context(
        tmp_path / "mismatched-url.json",
        provider_url="https://miro.com/app/board/uXjVDifferentBoard=/",
    )
    with pytest.raises(VisualTruthError, match="provider URL"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=capture,
            context=mismatched_url,
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "mismatched-url-receipt.json",
            now=NOW,
        )

    good = _context(tmp_path / "good.json")
    with pytest.raises(VisualTruthError, match="allowlisted"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=capture,
            context=good,
            expected_board_reference_digest="a" * 16,
            output=tmp_path / "wrong-board.json",
            now=NOW,
        )


def test_visual_truth_rejects_stale_future_unsupported_and_hardlinked_inputs(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "snapshot.json")
    capture = _capture(tmp_path / "capture.png")
    for name, timestamp, message in (
        ("stale", (NOW - timedelta(days=2)).isoformat(), "older"),
        ("future", (NOW + timedelta(minutes=10)).isoformat(), "future"),
    ):
        context = _context(tmp_path / f"{name}.json", captured_at=timestamp)
        with pytest.raises(VisualTruthError, match=message):
            create_visual_truth_receipt(
                snapshot=snapshot,
                capture=capture,
                context=context,
                expected_board_reference_digest=REFERENCE,
                output=tmp_path / f"{name}-receipt.json",
                now=NOW,
            )

    unsupported = _capture(tmp_path / "capture.bin", b"not an image")
    context = _context(tmp_path / "context.json")
    with pytest.raises(VisualTruthError, match="PNG, JPEG, or WebP"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=unsupported,
            context=context,
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "unsupported.json",
            now=NOW,
        )

    linked = tmp_path / "capture-linked.png"
    os.link(capture, linked)
    with pytest.raises(VisualTruthError, match="hard links"):
        create_visual_truth_receipt(
            snapshot=snapshot,
            capture=linked,
            context=context,
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / "linked.json",
            now=NOW,
        )


def test_visual_truth_accepts_minimal_jpeg_and_webp_headers(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "snapshot.json")
    context = _context(tmp_path / "context.json")
    jpeg = (
        b"\xff\xd8\xff\xc0\x00\x07\x08"
        + (720).to_bytes(2, "big")
        + (1280).to_bytes(2, "big")
        + b"\xff\xd9"
    )
    webp_chunk = b"\x00\x00\x00\x00" + (1279).to_bytes(3, "little") + (719).to_bytes(3, "little")
    webp = (
        b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X" + (10).to_bytes(4, "little") + webp_chunk
    )
    for suffix, payload, media_type in (
        ("jpg", jpeg, "image/jpeg"),
        ("webp", webp, "image/webp"),
    ):
        result = create_visual_truth_receipt(
            snapshot=snapshot,
            capture=_capture(tmp_path / f"capture.{suffix}", payload),
            context=context,
            expected_board_reference_digest=REFERENCE,
            output=tmp_path / f"receipt-{suffix}.json",
            now=NOW,
        )
        assert result["capture"]["media_type"] == media_type
        assert result["capture"]["width"] == 1280
        assert result["capture"]["height"] == 720


def test_public_and_packaged_visual_truth_schemas_are_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in (
        "miro-visual-truth-context.v1.schema.json",
        "miro-visual-truth-receipt.v1.schema.json",
    ):
        assert (root / "schemas" / name).read_bytes() == (
            root / "src/schauwerk/schemas" / name
        ).read_bytes()


def test_visual_truth_cli_uses_local_allowlist_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allowlist = tmp_path / "boards.json"
    board = BoardAllowlist(allowlist).add(ALIAS, BOARD_URL)
    assert board.reference_digest == reference_digest(BOARD_URL)

    class FakeClient:
        def __init__(self) -> None:
            self.settings = SimpleNamespace(board_allowlist_path=allowlist)

    monkeypatch.setattr(cli_handlers, "MiroMCPClient", FakeClient)
    snapshot = _snapshot(tmp_path / "snapshot.json")
    capture = _capture(tmp_path / "capture.png")
    context = _context(
        tmp_path / "context.json",
        board_reference_digest=board.reference_digest,
        captured_at=datetime.now(UTC).isoformat(),
    )
    receipt = tmp_path / "receipt.json"

    assert (
        main(
            [
                "miro",
                "visual-truth",
                "create",
                str(snapshot),
                str(capture),
                str(context),
                "--output",
                str(receipt),
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["success"] is True
    assert created["board_reference_digest"] == board.reference_digest

    assert (
        main(
            [
                "miro",
                "visual-truth",
                "check",
                str(receipt),
                "--json",
            ]
        )
        == 0
    )
    checked = json.loads(capsys.readouterr().out)
    assert checked["receipt_digest"] == created["receipt_digest"]
