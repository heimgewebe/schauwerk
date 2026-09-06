"""Console front door adding the thin Classroom v1 workflow.

All existing Schauwerk commands are delegated unchanged to :mod:`schauwerk.runner`.
The classroom surface is intentionally separate so the first classroom slice can
compose existing contracts without widening the legacy dispatcher.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from .classroom import (
    close_classroom_session,
    continue_classroom,
    load_classroom_package,
    prepare_classroom,
    snapshot_contains_marker,
    stage_classroom_package,
    summarize_snapshots,
)
from .durable.common import (
    DurableError,
    bind_digest,
    read_json,
    require_bound_digest,
    write_json,
)
from .runner import emit
from .runner import main as legacy_main
from .surfaces.miro.client import MiroMCPClient
from .surfaces.miro.errors import MiroError, find_nested_miro_error, redact_text


def _bounded_integer(minimum: int, maximum: int):
    def parse(value: str) -> int:
        number = int(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def build_classroom_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="schauwerk classroom")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser(
        "prepare", help="build a provider-free classroom package from a Learning View"
    )
    prepare.add_argument("input")
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--groups", type=_bounded_integer(1, 12), default=6)
    prepare.add_argument(
        "--template",
        choices=("vibe-coding", "discover", "group-compare"),
        default="vibe-coding",
    )
    prepare.add_argument("--session-id")
    prepare.add_argument("--json", action="store_true")

    start = commands.add_parser(
        "start", help="snapshot, apply and verify one prepared classroom package"
    )
    start.add_argument("alias")
    start.add_argument("prepared_dir")
    start.add_argument("--session-dir", required=True)
    _add_snapshot_limits(start)
    start.add_argument("--json", action="store_true")

    read = commands.add_parser("read", help="take a verified read-only classroom snapshot")
    read.add_argument("alias")
    read.add_argument("--output", required=True)
    read.add_argument("--baseline")
    read.add_argument("--summary-output")
    _add_snapshot_limits(read)
    read.add_argument("--json", action="store_true")

    summarize = commands.add_parser(
        "summarize", help="compare verified snapshots without pedagogical judgement"
    )
    summarize.add_argument("before")
    summarize.add_argument("after")
    summarize.add_argument("--output")
    summarize.add_argument("--json", action="store_true")

    close = commands.add_parser(
        "close", help="take a final snapshot and close one classroom session locally"
    )
    close.add_argument("alias")
    close.add_argument("session_dir")
    _add_snapshot_limits(close)
    close.add_argument("--json", action="store_true")

    continuation = commands.add_parser(
        "continue", help="prepare the next lesson bound to one closed classroom session"
    )
    continuation.add_argument("previous_session_dir")
    continuation.add_argument("next_input")
    continuation.add_argument("--output-dir", required=True)
    continuation.add_argument("--groups", type=_bounded_integer(1, 12), default=6)
    continuation.add_argument(
        "--template",
        choices=("vibe-coding", "discover", "group-compare"),
        default="vibe-coding",
    )
    continuation.add_argument("--session-id")
    continuation.add_argument("--json", action="store_true")
    return parser


def _add_snapshot_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--item-limit", type=_bounded_integer(10, 1000), default=500)
    parser.add_argument("--comment-limit", type=_bounded_integer(1, 50), default=50)
    parser.add_argument("--max-pages", type=_bounded_integer(1, 100), default=50)
    parser.add_argument("--no-comments", action="store_true")


def _snapshot(
    *,
    client: MiroMCPClient,
    alias: str,
    output: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    receipt = asyncio.run(
        client.snapshot(
            alias=alias,
            output_path=output,
            item_limit=args.item_limit,
            comment_limit=args.comment_limit,
            max_pages=args.max_pages,
            include_comments=not args.no_comments,
        )
    )
    return receipt.to_dict()


def _load_bound_receipt(
    path: Path, *, schema: str, digest_field: str, label: str
) -> dict[str, Any]:
    value = read_json(path, label=label)
    if value.get("schema_version") != schema:
        raise DurableError(f"{label} schema is invalid")
    require_bound_digest(value, digest_field, label=label)
    return value


def _start(args: argparse.Namespace, client: MiroMCPClient) -> dict[str, Any]:
    session_dir = Path(args.session_dir).expanduser().absolute()
    package = stage_classroom_package(Path(args.prepared_dir), session_dir)
    receipt_path = session_dir / "start-receipt.json"
    if receipt_path.exists():
        receipt = _load_bound_receipt(
            receipt_path,
            schema="schauwerk-classroom-start-receipt.v1",
            digest_field="start_digest",
            label="classroom start receipt",
        )
        if (
            receipt.get("board_alias") != args.alias
            or receipt.get("package_digest") != package["package_digest"]
        ):
            raise DurableError("classroom start receipt does not match the requested session")
        replay_path = session_dir / "replay-readback.json"
        _snapshot(client=client, alias=args.alias, output=replay_path, args=args)
        if not snapshot_contains_marker(replay_path, str(package["session_marker"])):
            raise DurableError("classroom start receipt exists but the board marker drifted")
        return {**receipt, "replayed": True}

    for partial in (
        session_dir / "before.json",
        session_dir / "started.json",
        session_dir / "start-partial.json",
    ):
        if partial.exists() or partial.is_symlink():
            raise DurableError("classroom session has partial start state; reconcile before retry")

    before_path = session_dir / "before.json"
    before = _snapshot(client=client, alias=args.alias, output=before_path, args=args)
    marker = str(package["session_marker"])
    if snapshot_contains_marker(before_path, marker):
        raise DurableError("classroom session marker already exists on the board")

    dsl = (session_dir / "classroom.dsl").read_text(encoding="utf-8")
    layout = asyncio.run(
        client.layout_create(
            alias=args.alias,
            dsl=dsl,
            invocation_source="schauwerk-classroom-start-v1",
        )
    ).to_dict()
    started_path = session_dir / "started.json"
    started = _snapshot(client=client, alias=args.alias, output=started_path, args=args)
    if not snapshot_contains_marker(started_path, marker):
        partial: dict[str, Any] = {
            "schema_version": "schauwerk-classroom-start-partial.v1",
            "board_alias": args.alias,
            "package_digest": package["package_digest"],
            "session_id": package["session_id"],
            "before_content_digest": before["content_digest"],
            "observed_after_content_digest": started["content_digest"],
            "layout": layout,
            "mutation_attempted": True,
            "verified": False,
            "retry_allowed": False,
        }
        bind_digest(partial, "partial_digest")
        write_json(session_dir / "start-partial.json", partial)
        raise DurableError("classroom start mutated the provider but marker verification failed")

    receipt: dict[str, Any] = {
        "schema_version": "schauwerk-classroom-start-receipt.v1",
        "board_alias": args.alias,
        "session_id": package["session_id"],
        "package_digest": package["package_digest"],
        "before_content_digest": before["content_digest"],
        "started_content_digest": started["content_digest"],
        "layout": layout,
        "mutation_attempted": True,
        "verified": True,
        "student_work_modified": False,
        "replayed": False,
    }
    bind_digest(receipt, "start_digest")
    write_json(receipt_path, receipt)
    return receipt


def _read(args: argparse.Namespace, client: MiroMCPClient) -> dict[str, Any]:
    output = Path(args.output)
    snapshot = _snapshot(client=client, alias=args.alias, output=output, args=args)
    result: dict[str, Any] = {
        "schema_version": "schauwerk-classroom-read-receipt.v1",
        "snapshot": snapshot,
        "provider_mutation_attempted": False,
    }
    if args.baseline:
        summary_output = (
            Path(args.summary_output)
            if args.summary_output
            else output.with_name(f"{output.stem}.summary.json")
        )
        result["summary"] = summarize_snapshots(
            before_path=Path(args.baseline),
            after_path=output,
            output=summary_output,
        )
    return result


def _close(args: argparse.Namespace, client: MiroMCPClient) -> dict[str, Any]:
    session_dir = Path(args.session_dir).expanduser().absolute()
    package = load_classroom_package(session_dir)
    close_path = session_dir / "close-receipt.json"
    if close_path.exists():
        receipt = _load_bound_receipt(
            close_path,
            schema="schauwerk-classroom-close-receipt.v1",
            digest_field="close_digest",
            label="classroom close receipt",
        )
        if receipt.get("package_digest") != package["package_digest"]:
            raise DurableError("classroom close receipt package binding mismatch")
        return {**receipt, "replayed": True}

    start = _load_bound_receipt(
        session_dir / "start-receipt.json",
        schema="schauwerk-classroom-start-receipt.v1",
        digest_field="start_digest",
        label="classroom start receipt",
    )
    if (
        start.get("board_alias") != args.alias
        or start.get("package_digest") != package["package_digest"]
    ):
        raise DurableError("classroom close does not match the started session")
    final_path = session_dir / "final.json"
    _snapshot(client=client, alias=args.alias, output=final_path, args=args)
    receipt = close_classroom_session(session_dir=session_dir, final_snapshot=final_path)
    return {**receipt, "replayed": False}


def _run_classroom(args: argparse.Namespace, client: MiroMCPClient | None = None) -> dict[str, Any]:
    if args.command == "prepare":
        return prepare_classroom(
            input_path=Path(args.input),
            output_dir=Path(args.output_dir),
            group_count=args.groups,
            template=args.template,
            session_id=args.session_id,
        )
    if args.command == "summarize":
        return summarize_snapshots(
            before_path=Path(args.before),
            after_path=Path(args.after),
            output=Path(args.output) if args.output else None,
        )
    if args.command == "continue":
        return continue_classroom(
            previous_session_dir=Path(args.previous_session_dir),
            next_input_path=Path(args.next_input),
            output_dir=Path(args.output_dir),
            group_count=args.groups,
            template=args.template,
            session_id=args.session_id,
        )
    active = client or MiroMCPClient()
    if args.command == "start":
        return _start(args, active)
    if args.command == "read":
        return _read(args, active)
    if args.command == "close":
        return _close(args, active)
    raise AssertionError(f"unhandled classroom command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] != "classroom":
        return legacy_main(argv)
    args = build_classroom_parser().parse_args(values[1:])
    try:
        result = _run_classroom(args)
        emit(result, as_json=args.json)
        return 0
    except (MiroError, DurableError, ValueError) as exc:
        print(f"error: {redact_text(exc)}", file=sys.stderr)
        return 2
    except Exception as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            print(f"error: {redact_text(nested)}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
