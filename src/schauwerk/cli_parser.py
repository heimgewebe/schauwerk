"""Argument parser for the Schauwerk command line."""

from __future__ import annotations

import argparse


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

    logout = commands.add_parser("logout", help="clear local Miro state")
    logout.add_argument("--json", action="store_true")

    return parser
