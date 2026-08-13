"""CLI surface for the isolated Schauwerk Fundus core."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import Fundus, FundusPaths


def _state_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-root")


def _registry_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry-root")


def add_fundus_parser(providers) -> None:
    fundus = providers.add_parser(
        "fundus",
        help="build reusable Miro-independent visual assets",
    )
    commands = fundus.add_subparsers(
        dest="command",
        required=True,
    )

    doctor = commands.add_parser(
        "doctor",
        help="validate Fundus state, registry and extraction seam",
    )
    _state_option(doctor)
    _registry_option(doctor)
    doctor.add_argument("--json", action="store_true")

    ingest = commands.add_parser(
        "ingest",
        help="store one immutable content-addressed source",
    )
    ingest.add_argument("source")
    ingest.add_argument("--origin", default="unknown")
    ingest.add_argument(
        "--rights-status",
        choices=("owned", "licensed", "unknown", "restricted"),
        default="unknown",
    )
    _state_option(ingest)
    ingest.add_argument("--json", action="store_true")

    inspect = commands.add_parser(
        "inspect",
        help="inspect one declared Fundus asset",
    )
    inspect.add_argument("asset")
    _state_option(inspect)
    _registry_option(inspect)
    inspect.add_argument("--json", action="store_true")

    build = commands.add_parser(
        "build",
        help="build one asset from its exact source and recipe",
    )
    build.add_argument("asset")
    _state_option(build)
    _registry_option(build)
    build.add_argument("--json", action="store_true")

    preview = commands.add_parser(
        "preview",
        help="write a self-contained digest-bound visual preview",
    )
    preview.add_argument("asset")
    preview.add_argument("--build")
    _state_option(preview)
    _registry_option(preview)
    preview.add_argument("--json", action="store_true")

    accept = commands.add_parser(
        "accept",
        help="bind a visual decision to one exact build",
    )
    accept.add_argument("asset")
    accept.add_argument("--build", required=True)
    accept.add_argument("--reviewer", required=True)
    accept.add_argument(
        "--decision",
        choices=("accepted", "rejected"),
        required=True,
    )
    accept.add_argument("--note", default="")
    _state_option(accept)
    _registry_option(accept)
    accept.add_argument("--json", action="store_true")

    package = commands.add_parser(
        "package",
        help="create an immutable package from an accepted build",
    )
    package.add_argument("asset")
    package.add_argument("--build", required=True)
    package.add_argument("--acceptance", required=True)
    _state_option(package)
    _registry_option(package)
    package.add_argument("--json", action="store_true")


def _fundus(args) -> Fundus:
    return Fundus(
        FundusPaths.from_overrides(
            data_root=getattr(args, "data_root", None),
            registry_root=getattr(args, "registry_root", None),
        )
    )


def handle_fundus_command(args) -> dict:
    fundus = _fundus(args)
    if args.command == "doctor":
        return fundus.doctor()
    if args.command == "ingest":
        return fundus.ingest(
            Path(args.source),
            origin=args.origin,
            rights_status=args.rights_status,
        )
    if args.command == "inspect":
        return fundus.inspect(args.asset)
    if args.command == "build":
        return fundus.build(args.asset)
    if args.command == "preview":
        return fundus.preview(
            args.asset,
            build_digest=args.build,
        )
    if args.command == "accept":
        return fundus.accept(
            args.asset,
            build_digest=args.build,
            reviewer=args.reviewer,
            decision=args.decision,
            note=args.note,
        )
    if args.command == "package":
        return fundus.package(
            args.asset,
            build_digest=args.build,
            acceptance_digest=args.acceptance,
        )
    raise AssertionError(f"unhandled Fundus command: {args.command}")
