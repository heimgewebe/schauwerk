# ruff: noqa: E501
"""Executable Schauwerk command dispatcher."""

from __future__ import annotations

import json
import sys
from typing import Any

from .cli_handlers import (
    handle_board_add,
    handle_board_list,
    handle_board_remove,
    handle_inspect,
    handle_learn_apply,
    handle_learn_live_prune,
    handle_learn_live_test,
    handle_learn_render,
    handle_login,
    handle_logout,
    handle_quality,
    handle_snapshot,
    handle_status,
    handle_tools,
)
from .cli_parser import build_parser
from .surfaces.miro.errors import MiroError, find_nested_miro_error, redact_text


def emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = handle_status(live=args.live)
        elif args.command == "login":
            result = handle_login(
                open_browser=not args.no_browser,
                manual_callback=args.manual_callback,
            )
        elif args.command == "tools":
            result = handle_tools()
        elif args.command == "inspect":
            result = handle_inspect(
                query=args.query,
                owned_by_me=args.owned_by_me,
                limit=args.limit,
                max_pages=args.max_pages,
            )
        elif args.command == "board" and args.board_command == "add":
            result = handle_board_add(
                alias=args.alias, miro_url=args.miro_url, replace=args.replace
            )
        elif args.command == "board" and args.board_command == "list":
            result = handle_board_list()
        elif args.command == "board" and args.board_command == "remove":
            result = handle_board_remove(alias=args.alias)
        elif args.command == "snapshot":
            result = handle_snapshot(
                alias=args.alias,
                output=args.output,
                item_limit=args.item_limit,
                comment_limit=args.comment_limit,
                max_pages=args.max_pages,
                include_comments=not args.no_comments,
            )
        elif args.command == "quality":
            result = handle_quality(
                alias=args.alias,
                snapshot=args.snapshot,
                output=args.output,
                expected_min_connectors=args.expected_min_connectors,
                expected_min_docs=args.expected_min_docs,
                expected_min_tables=args.expected_min_tables,
            )
        elif args.command == "learn" and args.learn_command == "render":
            result = handle_learn_render(
                input_path=args.input, output=args.output, template=args.template
            )
        elif args.command == "learn" and args.learn_command == "apply":
            result = handle_learn_apply(
                input_path=args.input, alias=args.alias, template=args.template
            )
        elif args.command == "learn" and args.learn_command == "live-test":
            result = handle_learn_live_test(
                input_path=args.input,
                alias=args.alias,
                board_name=args.board_name,
                output_dir=args.output_dir,
                replace_alias=args.replace_alias,
                item_limit=args.item_limit,
                comment_limit=args.comment_limit,
                max_pages=args.max_pages,
                include_comments=not args.no_comments,
                template=args.template,
            )
        elif args.command == "learn" and args.learn_command == "live-prune":
            result = handle_learn_live_prune(keep=args.keep, dry_run=args.dry_run)
        elif args.command == "logout":
            result = handle_logout()
        else:
            raise AssertionError(f"unhandled command: {args.command}")
        emit(result, as_json=args.json)
        return 0
    except (MiroError, ValueError) as exc:
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
