"""Executable Schauwerk command dispatcher."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .cli_handlers import handle_login, handle_logout, handle_status, handle_tools
from .cli_parser import build_parser
from .surfaces.miro.errors import MiroError, redact_text
from .surfaces.miro.readonly import inspect_default


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
            result = handle_status()
        elif args.command == "login":
            result = handle_login(
                open_browser=not args.no_browser,
                manual_callback=args.manual_callback,
            )
        elif args.command == "tools":
            result = handle_tools()
        elif args.command == "inspect":
            report = asyncio.run(
                inspect_default(
                    query=args.query,
                    owned_by_me=args.owned_by_me,
                    limit=args.limit,
                    max_pages=args.max_pages,
                )
            )
            result = report.to_dict()
        elif args.command == "logout":
            result = handle_logout()
        else:
            raise AssertionError(f"unhandled command: {args.command}")
        emit(result, as_json=args.json)
        return 0
    except MiroError as exc:
        print(f"error: {redact_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
