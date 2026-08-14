"""CLI surface for the isolated Schauwerk Fundus core."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import Fundus, FundusPaths
from .package_contract import verify_consumer_lock, verify_package_directory
from .review import build_review_bundle, build_review_plan, check_review_bundle


def _state_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-root")


def _registry_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry-root")


def _fixture_map(values: list[str]) -> dict[str, Path]:
    fixtures: dict[str, Path] = {}
    for raw in values:
        fixture_id, separator, path = raw.partition("=")
        if not separator or not fixture_id or not path:
            raise ValueError("review fixture must use ID=PATH")
        if fixture_id in fixtures:
            raise ValueError(f"duplicate review fixture id: {fixture_id}")
        fixtures[fixture_id] = Path(path)
    return fixtures


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
        "--source-mode",
        choices=("manual", "generated", "edited", "unknown"),
    )
    ingest.add_argument("--image-brief")
    ingest.add_argument(
        "--rights-status",
        choices=("owned", "licensed", "unknown", "restricted"),
        default="unknown",
    )
    _state_option(ingest)
    ingest.add_argument("--json", action="store_true")

    brief = commands.add_parser(
        "brief",
        help="validate and digest one Fundus image-operation brief",
    )
    brief.add_argument("brief")
    _state_option(brief)
    brief.add_argument("--json", action="store_true")

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

    review = commands.add_parser(
        "review",
        help="build portable project-independent Fundus demo pages",
    )
    review_commands = review.add_subparsers(
        dest="review_command",
        required=True,
    )
    review_plan = review_commands.add_parser(
        "plan",
        help="materialize the exact current build set for one Fundus family",
    )
    review_plan.add_argument("family")
    _state_option(review_plan)
    _registry_option(review_plan)
    review_plan.add_argument("--json", action="store_true")

    review_build = review_commands.add_parser(
        "build",
        help="create one static digest-bound review bundle",
    )
    review_build.add_argument("family")
    review_build.add_argument("--output-dir", required=True)
    review_build.add_argument("--title")
    review_build.add_argument("--description")
    review_build.add_argument("--template")
    review_build.add_argument("--css")
    review_build.add_argument(
        "--fixture",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="bind one local raster review fixture; repeatable",
    )
    _state_option(review_build)
    _registry_option(review_build)
    review_build.add_argument("--json", action="store_true")

    review_check = review_commands.add_parser(
        "check",
        help="verify one portable Fundus review bundle",
    )
    review_check.add_argument("bundle_dir")
    review_check.add_argument("--json", action="store_true")

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

    package_verify = commands.add_parser(
        "package-verify",
        help="verify one immutable Fundus package without live registry state",
    )
    package_verify.add_argument("package_dir")
    package_verify.add_argument("--json", action="store_true")

    consumer_lock = commands.add_parser(
        "consumer-lock",
        help="write immutable Fundus consumer-lock metadata for a verified package",
    )
    consumer_lock.add_argument("package_dir")
    _state_option(consumer_lock)
    consumer_lock.add_argument("--json", action="store_true")

    consumer_check = commands.add_parser(
        "consumer-check",
        help="verify one vendored Fundus package against a portable consumer lock",
    )
    consumer_check.add_argument("lock")
    consumer_check.add_argument("package_dir")
    consumer_check.add_argument("--json", action="store_true")


def _fundus(args) -> Fundus:
    return Fundus(
        FundusPaths.from_overrides(
            data_root=getattr(args, "data_root", None),
            registry_root=getattr(args, "registry_root", None),
        )
    )


def handle_fundus_command(args) -> dict:
    if args.command == "review" and args.review_command == "check":
        return check_review_bundle(Path(args.bundle_dir))
    if args.command == "package-verify":
        return verify_package_directory(Path(args.package_dir))
    if args.command == "consumer-check":
        return verify_consumer_lock(Path(args.lock), Path(args.package_dir))

    fundus = _fundus(args)
    if args.command == "doctor":
        return fundus.doctor()
    if args.command == "ingest":
        return fundus.ingest(
            Path(args.source),
            origin=args.origin,
            rights_status=args.rights_status,
            source_mode=args.source_mode,
            image_brief_path=args.image_brief,
        )
    if args.command == "brief":
        return fundus.image_brief(Path(args.brief))
    if args.command == "inspect":
        return fundus.inspect(args.asset)
    if args.command == "build":
        return fundus.build(args.asset)
    if args.command == "preview":
        return fundus.preview(
            args.asset,
            build_digest=args.build,
        )
    if args.command == "review":
        if args.review_command == "plan":
            return build_review_plan(fundus, args.family).to_dict()
        if args.review_command == "build":
            kwargs = {
                "title": args.title,
                "consumer_template": Path(args.template) if args.template else None,
                "consumer_css": Path(args.css) if args.css else None,
                "fixtures": _fixture_map(args.fixture),
            }
            if args.description is not None:
                kwargs["description"] = args.description
            return build_review_bundle(
                fundus,
                args.family,
                Path(args.output_dir),
                **kwargs,
            )
        raise AssertionError(f"unhandled Fundus review command: {args.review_command}")
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
    if args.command == "consumer-lock":
        return fundus.consumer_lock(Path(args.package_dir))
    raise AssertionError(f"unhandled Fundus command: {args.command}")
