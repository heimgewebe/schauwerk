"""Argument parser for the Schauwerk command line."""

from __future__ import annotations

import argparse


def _bounded_integer(minimum: int, maximum: int):
    def parse(value: str) -> int:
        number = int(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="schauwerk")
    providers = parser.add_subparsers(dest="provider", required=True)
    miro = providers.add_parser("miro", help="direct Miro MCP connection")
    commands = miro.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="show local connection state")
    status.add_argument("--json", action="store_true")

    login = commands.add_parser("login", help="authorize and discover tools")
    login.add_argument("--no-browser", action="store_true")
    login.add_argument("--manual-callback", action="store_true")
    login.add_argument("--json", action="store_true")

    tools = commands.add_parser("tools", help="show the Miro tool catalogue")
    tools.add_argument("--json", action="store_true")

    inspect = commands.add_parser("inspect", help="run sanitized read-only checks")
    inspect.add_argument("--query", default="")
    inspect.add_argument("--owned-by-me", action="store_true")
    inspect.add_argument("--limit", type=_bounded_integer(1, 50), default=20)
    inspect.add_argument("--max-pages", type=_bounded_integer(1, 20), default=5)
    inspect.add_argument("--json", action="store_true")

    board = commands.add_parser("board", help="manage the local board allowlist")
    board_commands = board.add_subparsers(dest="board_command", required=True)
    board_add = board_commands.add_parser("add", help="allowlist one board URL")
    board_add.add_argument("alias")
    board_add.add_argument("miro_url")
    board_add.add_argument("--replace", action="store_true")
    board_add.add_argument("--json", action="store_true")
    board_list = board_commands.add_parser("list", help="list allowlisted aliases")
    board_list.add_argument("--json", action="store_true")
    board_remove = board_commands.add_parser("remove", help="remove one board alias")
    board_remove.add_argument("alias")
    board_remove.add_argument("--json", action="store_true")

    snapshot = commands.add_parser("snapshot", help="verify one allowlisted board twice")
    snapshot.add_argument("alias")
    snapshot.add_argument("--output")
    snapshot.add_argument("--item-limit", type=_bounded_integer(10, 1000), default=100)
    snapshot.add_argument("--comment-limit", type=_bounded_integer(1, 50), default=50)
    snapshot.add_argument("--max-pages", type=_bounded_integer(1, 100), default=20)
    snapshot.add_argument("--no-comments", action="store_true")
    snapshot.add_argument("--json", action="store_true")

    learn = commands.add_parser("learn", help="render learning views for Miro")
    learn_commands = learn.add_subparsers(dest="learn_command", required=True)
    learn_render = learn_commands.add_parser(
        "render", help="render a learning-view input to Miro DSL"
    )
    learn_render.add_argument("input")
    learn_render.add_argument("--output")
    learn_render.add_argument("--json", action="store_true")

    logout = commands.add_parser("logout", help="clear local Miro state")
    logout.add_argument("--json", action="store_true")
    return parser
