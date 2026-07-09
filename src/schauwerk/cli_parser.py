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
    ecosystem = providers.add_parser("ecosystem", help="ecosystem visualizations")
    ecosystem_commands = ecosystem.add_subparsers(dest="command", required=True)
    ecosystem_render = ecosystem_commands.add_parser(
        "render", help="write an ecosystem map HTML handoff"
    )
    ecosystem_render.add_argument("manifest")
    ecosystem_render.add_argument("--output", required=True)
    ecosystem_render.add_argument("--source-root")
    ecosystem_render.add_argument("--json", action="store_true")

    miro = providers.add_parser("miro", help="direct Miro MCP connection")
    commands = miro.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="show local connection state")
    status.add_argument("--live", action="store_true", help="check live Miro MCP access")
    status.add_argument("--json", action="store_true")

    login = commands.add_parser("login", help="authorize and discover tools")
    login.add_argument("--no-browser", action="store_true")
    login.add_argument("--manual-callback", action="store_true")
    login.add_argument("--json", action="store_true")

    tools = commands.add_parser("tools", help="show the Miro tool catalogue")
    tools.add_argument("--json", action="store_true")

    doctor = commands.add_parser("doctor", help="diagnose local and live Miro auth state")
    doctor.add_argument("--no-live", action="store_true", help="skip the live MCP check")
    doctor.add_argument("--json", action="store_true")

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

    quality = commands.add_parser("quality", help="inspect a local Miro snapshot quality receipt")
    quality.add_argument("alias")
    quality.add_argument("snapshot")
    quality.add_argument("--output")
    quality.add_argument("--expected-min-connectors", type=_bounded_integer(0, 1000), default=0)
    quality.add_argument("--expected-min-docs", type=_bounded_integer(0, 1000), default=0)
    quality.add_argument("--expected-min-tables", type=_bounded_integer(0, 1000), default=0)
    quality.add_argument("--json", action="store_true")

    learn = commands.add_parser("learn", help="render learning views for Miro")
    learn_commands = learn.add_subparsers(dest="learn_command", required=True)
    learn_render = learn_commands.add_parser(
        "render", help="render a learning-view input to Miro DSL"
    )
    learn_render.add_argument("input")
    learn_render.add_argument("--output")
    learn_render.add_argument("--template", choices=("classic", "zoomlandkarte"), default="classic")
    learn_render.add_argument("--json", action="store_true")
    learn_apply = learn_commands.add_parser(
        "apply", help="render and apply a learning-view input to an allowlisted board"
    )
    learn_apply.add_argument("alias")
    learn_apply.add_argument("input")
    learn_apply.add_argument("--template", choices=("classic", "zoomlandkarte"), default="classic")
    learn_apply.add_argument("--json", action="store_true")

    learn_live = learn_commands.add_parser(
        "live-test", help="create a fresh board and run a verified learning-view live test"
    )
    learn_live.add_argument("input")
    learn_live.add_argument("--alias")
    learn_live.add_argument("--board-name")
    learn_live.add_argument("--output-dir")
    learn_live.add_argument("--replace-alias", action="store_true")
    learn_live.add_argument("--item-limit", type=_bounded_integer(10, 1000), default=200)
    learn_live.add_argument("--comment-limit", type=_bounded_integer(1, 50), default=50)
    learn_live.add_argument("--max-pages", type=_bounded_integer(1, 100), default=20)
    learn_live.add_argument("--no-comments", action="store_true")
    learn_live.add_argument("--template", choices=("classic", "zoomlandkarte"), default="classic")
    learn_live.add_argument("--json", action="store_true")

    learn_prune = learn_commands.add_parser(
        "live-prune", help="prune local learning live-test artefact records"
    )
    learn_prune.add_argument("--keep", type=_bounded_integer(0, 1000), default=5)
    learn_prune.add_argument("--dry-run", action="store_true")
    learn_prune.add_argument("--json", action="store_true")

    region = commands.add_parser("region")
    rc = region.add_subparsers(dest="region_command", required=True)
    rp = rc.add_parser("plan")
    rp.add_argument("input")
    rp.add_argument(
        "--operation", choices=("render-update", "replace-region"), default="render-update"
    )
    rp.add_argument("--output")
    rp.add_argument("--json", action="store_true")

    rpf = rc.add_parser("preflight")
    rpf.add_argument("input")
    rpf.add_argument("--snapshot", required=True)
    rpf.add_argument(
        "--operation", choices=("render-update", "replace-region"), default="render-update"
    )
    rpf.add_argument("--output")
    rpf.add_argument("--json", action="store_true")

    ras = rc.add_parser("apply-scaffold")
    ras.add_argument("preflight")
    ras.add_argument("--output")
    ras.add_argument("--json", action="store_true")

    rar = rc.add_parser("apply-receipt")
    rar.add_argument("scaffold")
    rar.add_argument("--fixture", required=True)
    rar.add_argument("--output")
    rar.add_argument("--json", action="store_true")

    operation_contract = rc.add_parser(
        "operation-contract", help="compile a fixture-only operation contract"
    )
    operation_contract.add_argument("scaffold")
    operation_contract.add_argument("--fixture", required=True)
    operation_contract.add_argument("--output")
    operation_contract.add_argument("--json", action="store_true")

    apply_simulation = rc.add_parser(
        "apply-simulation",
        help="verify simulation-only apply evidence; this is the current simulation endpoint",
    )
    apply_simulation.add_argument("operation_contract")
    apply_simulation.add_argument("--after-snapshot", required=True)
    apply_simulation.add_argument("--output")
    apply_simulation.add_argument("--json", action="store_true")

    simulation_postflight = rc.add_parser(
        "simulation-postflight",
        help="convert a simulation-only apply receipt into restore-ready postflight evidence",
    )
    simulation_postflight.add_argument("apply_simulation_receipt")
    simulation_postflight.add_argument("--output")
    simulation_postflight.add_argument("--json", action="store_true")

    simulation_closeout = rc.add_parser(
        "simulation-closeout",
        help="close a restored SW-009 simulation chain without live apply readiness",
    )
    simulation_closeout.add_argument("restore_receipt")
    simulation_closeout.add_argument("--output")
    simulation_closeout.add_argument("--json", action="store_true")

    sw009_live_apply_gate = rc.add_parser(
        "sw009-live-apply-gate",
        help="compile a local SW-009 live-apply gate receipt without Miro mutation",
    )
    sw009_live_apply_gate.add_argument("scaffold")
    sw009_live_apply_gate.add_argument("--sw003-evidence-packet", required=True)
    sw009_live_apply_gate.add_argument("--ack-allowlisted-scope", action="store_true")
    sw009_live_apply_gate.add_argument("--ack-preflight-receipt-digest", action="store_true")
    sw009_live_apply_gate.add_argument("--ack-before-snapshot", action="store_true")
    sw009_live_apply_gate.add_argument("--ack-review-packet", action="store_true")
    sw009_live_apply_gate.add_argument("--ack-restore-strategy", action="store_true")
    sw009_live_apply_gate.add_argument("--ack-postflight-plan", action="store_true")
    sw009_live_apply_gate.add_argument("--ack-provider-redaction", action="store_true")
    sw009_live_apply_gate.add_argument("--output")
    sw009_live_apply_gate.add_argument("--json", action="store_true")

    sw009_candidate_template = rc.add_parser(
        "sw009-live-apply-candidate-template",
        help="emit a local SW-009 live-apply candidate manifest template",
    )
    sw009_candidate_template.add_argument("--output")
    sw009_candidate_template.add_argument("--json", action="store_true")

    sw009_candidate_check = rc.add_parser(
        "sw009-live-apply-candidate-check",
        help="check one local SW-009 live-apply candidate manifest without mutation",
    )
    sw009_candidate_check.add_argument("candidate")
    sw009_candidate_check.add_argument("--output")
    sw009_candidate_check.add_argument("--json", action="store_true")

    postflight_receipt = rc.add_parser("postflight")
    postflight_receipt.add_argument("apply_receipt")
    postflight_receipt.add_argument("--after-snapshot", required=True)
    postflight_receipt.add_argument("--output")
    postflight_receipt.add_argument("--json", action="store_true")

    restore_receipt = rc.add_parser("restore-receipt")
    restore_receipt.add_argument("postflight")
    restore_receipt.add_argument("--restored-snapshot", required=True)
    restore_receipt.add_argument("--output")
    restore_receipt.add_argument("--json", action="store_true")

    sw003_closeout = rc.add_parser(
        "sw003-closeout",
        help="compile a fixture-only SW-003 closeout receipt without Miro mutation",
    )
    sw003_closeout.add_argument("restore_receipt")
    sw003_closeout.add_argument("--evidence", required=True)
    sw003_closeout.add_argument("--marker", required=True)
    sw003_closeout.add_argument("--output")
    sw003_closeout.add_argument("--json", action="store_true")

    sw003_live_gate = rc.add_parser(
        "sw003-live-gate",
        help="locally evaluate sanitized SW-003 live-gate evidence without Miro access",
    )
    sw003_live_gate.add_argument("evidence")
    sw003_live_gate.add_argument("--output")
    sw003_live_gate.add_argument("--json", action="store_true")

    sw003_live_gate_status = rc.add_parser(
        "sw003-live-gate-status",
        help="compile a local SW-003 live-gate status receipt without Miro access",
    )
    sw003_live_gate_status.add_argument("evaluation_receipt")
    sw003_live_gate_status.add_argument("--output")
    sw003_live_gate_status.add_argument("--json", action="store_true")

    sw003_live_gate_review_packet = rc.add_parser(
        "sw003-live-gate-review-packet",
        help="compile a local SW-003 live-gate review packet without Miro access",
    )
    sw003_live_gate_review_packet.add_argument("status_receipt")
    sw003_live_gate_review_packet.add_argument("--output")
    sw003_live_gate_review_packet.add_argument("--json", action="store_true")

    sw003_live_gate_evidence_packet = rc.add_parser(
        "sw003-live-gate-evidence-packet",
        help="compile a local SW-003 live-gate evidence packet without Miro access",
    )
    sw003_live_gate_evidence_packet.add_argument("review_packet")
    sw003_live_gate_evidence_packet.add_argument("--output")
    sw003_live_gate_evidence_packet.add_argument("--json", action="store_true")

    sw003_live_gate_requirements = rc.add_parser(
        "sw003-live-gate-requirements",
        help="emit the local SW-003 live-gate evidence checklist without Miro access",
    )
    sw003_live_gate_requirements.add_argument("--output")
    sw003_live_gate_requirements.add_argument("--json", action="store_true")

    sw003_live_gate_template = rc.add_parser(
        "sw003-live-gate-template",
        help="emit a sanitized SW-003 live-gate evidence template without Miro access",
    )
    sw003_live_gate_template.add_argument("--output")
    sw003_live_gate_template.add_argument("--json", action="store_true")

    logout = commands.add_parser("logout", help="clear local Miro state")
    logout.add_argument("--json", action="store_true")
    return parser
