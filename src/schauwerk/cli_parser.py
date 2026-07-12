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

    registry = providers.add_parser("registry", help="inspect the declared Schauwerk registry")
    registry_commands = registry.add_subparsers(dest="command", required=True)
    registry_status = registry_commands.add_parser(
        "status", help="validate and summarize registry truth"
    )
    registry_status.add_argument("--json", action="store_true")
    registry_show = registry_commands.add_parser(
        "show", help="show one registry collection or item"
    )
    registry_show.add_argument(
        "kind",
        choices=("sources", "projects", "surfaces", "views", "regions", "policies", "publications"),
    )
    registry_show.add_argument("identifier", nargs="?")
    registry_show.add_argument("--json", action="store_true")

    pilot = providers.add_parser("pilot", help="render deterministic useful-pilot projections")
    pilot_commands = pilot.add_subparsers(dest="command", required=True)
    grabowski = pilot_commands.add_parser(
        "grabowski", help="render the Grabowski operator overview from its declared context"
    )
    grabowski.add_argument("operator_context")
    grabowski.add_argument("--snapshot-output")
    grabowski.add_argument("--dsl-output")
    grabowski.add_argument("--json", action="store_true")

    grabowski_operational = pilot_commands.add_parser(
        "grabowski-operational",
        help="render static Grabowski contract facts beside sanitized live observations",
    )
    grabowski_operational.add_argument("static_snapshot")
    grabowski_operational.add_argument("observation")
    grabowski_operational.add_argument("--snapshot-output")
    grabowski_operational.add_argument("--dsl-output")
    grabowski_operational.add_argument("--json", action="store_true")

    software = pilot_commands.add_parser(
        "software", help="render a generic software-project overview from a declared snapshot"
    )
    software.add_argument("input")
    software.add_argument("--snapshot-output")
    software.add_argument("--dsl-output")
    software.add_argument("--json", action="store_true")

    education = providers.add_parser(
        "education", help="render audience-specific learning variants and offline packages"
    )
    education_commands = education.add_subparsers(dest="command", required=True)
    education_render = education_commands.add_parser(
        "render", help="render one audience-specific static HTML variant"
    )
    education_render.add_argument("input")
    education_render.add_argument(
        "--variant",
        required=True,
        choices=("teacher", "projection", "assignment", "student", "presentation"),
    )
    education_render.add_argument("--output")
    education_render.add_argument("--json", action="store_true")
    education_offline = education_commands.add_parser(
        "offline", help="write a self-contained offline learning package"
    )
    education_offline.add_argument("input")
    education_offline.add_argument(
        "--variant",
        required=True,
        choices=("teacher", "projection", "assignment", "student", "presentation"),
    )
    education_offline.add_argument("--output-dir", required=True)
    education_offline.add_argument("--json", action="store_true")

    visual = providers.add_parser("visual", help="inspect the versioned visual grammar")
    visual_commands = visual.add_subparsers(dest="command", required=True)
    visual_grammar = visual_commands.add_parser(
        "grammar", help="validate or write the canonical visual grammar manifest"
    )
    visual_grammar.add_argument("--output")
    visual_grammar.add_argument("--json", action="store_true")
    visual_system_v2 = visual_commands.add_parser(
        "system-v2", help="validate or write the semantic Visual System v2 manifest"
    )
    visual_system_v2.add_argument("--output")
    visual_system_v2.add_argument("--json", action="store_true")
    visual_reference_v2 = visual_commands.add_parser(
        "reference-v2", help="compile the canonical Visual System v2 reference board"
    )
    visual_reference_v2.add_argument("--spec-output")
    visual_reference_v2.add_argument("--dsl-output")
    visual_reference_v2.add_argument("--quality-output")
    visual_reference_v2.add_argument("--json", action="store_true")
    visual_review_v2 = visual_commands.add_parser(
        "review-v2", help="bind a human visual review to one live Visual System v2 receipt"
    )
    visual_review_v2.add_argument("live_receipt")
    visual_review_v2.add_argument("review_input")
    visual_review_v2.add_argument("--output", required=True)
    visual_review_v2.add_argument("--json", action="store_true")

    regie = providers.add_parser("regie", help="local receipt-bound review interface")
    regie_commands = regie.add_subparsers(dest="command", required=True)
    regie_context_template = regie_commands.add_parser(
        "context-template", help="write an owner-only editable Regie context draft"
    )
    regie_context_template.add_argument("--review-id", required=True)
    regie_context_template.add_argument("--title", required=True)
    regie_context_template.add_argument("--output", required=True)
    regie_context_template.add_argument("--json", action="store_true")
    regie_context_compile = regie_commands.add_parser(
        "context-compile", help="validate and digest-bind one Regie context draft"
    )
    regie_context_compile.add_argument("draft")
    regie_context_compile.add_argument("--output", required=True)
    regie_context_compile.add_argument("--json", action="store_true")
    regie_review = regie_commands.add_parser(
        "review", help="compile a source-bound review bundle without provider effect"
    )
    regie_review.add_argument("--context", required=True)
    regie_review.add_argument("--gate", required=True)
    regie_review.add_argument("--bundle", required=True)
    regie_review.add_argument("--output", required=True)
    regie_review.add_argument("--json", action="store_true")
    regie_serve = regie_commands.add_parser("serve", help="run the Regie interface on 127.0.0.1")
    regie_serve.add_argument("review_bundle")
    regie_serve.add_argument("--port", type=_bounded_integer(0, 65535), default=0)
    regie_serve.add_argument("--no-browser", action="store_true")
    regie_serve.add_argument("--json", action="store_true")

    overview = providers.add_parser(
        "overview", help="registry-backed resilient overview and live views"
    )
    overview_commands = overview.add_subparsers(dest="command", required=True)
    overview_snapshot = overview_commands.add_parser(
        "snapshot", help="write a validated owner-only overview snapshot"
    )
    overview_snapshot.add_argument("--output", required=True)
    overview_snapshot.add_argument("--probe-provider", action="store_true")
    overview_snapshot.add_argument("--json", action="store_true")
    overview_serve = overview_commands.add_parser(
        "serve", help="serve read-only overview on 127.0.0.1"
    )
    overview_serve.add_argument("--port", type=_bounded_integer(0, 65535), default=0)
    overview_serve.add_argument("--probe-provider", action="store_true")
    overview_serve.add_argument("--no-browser", action="store_true")
    overview_serve.add_argument("--json", action="store_true")

    stage = providers.add_parser("stage", help="build separated SW-012 presentation packages")
    stage_commands = stage.add_subparsers(dest="command", required=True)
    stage_build = stage_commands.add_parser(
        "build", help="render public and presenter outputs from one presentation model"
    )
    stage_build.add_argument("model")
    stage_build.add_argument("--variant", required=True)
    stage_build.add_argument("--public-dir", required=True)
    stage_build.add_argument("--presenter-dir", required=True)
    stage_build.add_argument("--source-root", default=".")
    stage_build.add_argument("--json", action="store_true")

    publish = providers.add_parser(
        "publish", help="build and operate local immutable SW-013 publications"
    )
    publish_commands = publish.add_subparsers(dest="command", required=True)
    publish_preview = publish_commands.add_parser(
        "preview", help="compile a privacy-checked publication preview"
    )
    publish_preview.add_argument("declaration")
    publish_preview.add_argument("--source-package", required=True)
    publish_preview.add_argument("--output", required=True)
    publish_preview.add_argument("--json", action="store_true")
    publish_release = publish_commands.add_parser(
        "release", help="release one reviewed immutable version into a local store"
    )
    publish_release.add_argument("declaration")
    publish_release.add_argument("preview")
    publish_release.add_argument("--source-package", required=True)
    publish_release.add_argument("--store-root", required=True)
    publish_release.add_argument("--json", action="store_true")
    publish_status = publish_commands.add_parser(
        "status", help="verify one stable publication link and immutable object"
    )
    publish_status.add_argument("stable_slug")
    publish_status.add_argument("--store-root", required=True)
    publish_status.add_argument("--at")
    publish_status.add_argument("--json", action="store_true")
    publish_withdraw = publish_commands.add_parser(
        "withdraw", help="withdraw a stable link without deleting its immutable object"
    )
    publish_withdraw.add_argument("stable_slug")
    publish_withdraw.add_argument("--store-root", required=True)
    publish_withdraw.add_argument("--expected-link-digest", required=True)
    publish_withdraw.add_argument("--reason", required=True)
    publish_withdraw.add_argument("--at")
    publish_withdraw.add_argument("--json", action="store_true")
    publish_serve = publish_commands.add_parser(
        "serve", help="serve active publications read-only on 127.0.0.1"
    )
    publish_serve.add_argument("--store-root", required=True)
    publish_serve.add_argument("--port", type=_bounded_integer(0, 65535), default=0)
    publish_serve.add_argument("--no-browser", action="store_true")
    publish_serve.add_argument("--json", action="store_true")

    durable = providers.add_parser(
        "durable", help="local SW-014 to SW-017 integration and recovery contracts"
    )
    durable_commands = durable.add_subparsers(dest="command", required=True)

    adapter_catalog = durable_commands.add_parser(
        "adapter-catalog", help="show the deterministic local adapter catalogue"
    )
    adapter_catalog.add_argument("--output")
    adapter_catalog.add_argument("--json", action="store_true")

    adapter_collect = durable_commands.add_parser(
        "adapter-collect", help="compile one declared local adapter input"
    )
    adapter_collect.add_argument("input")
    adapter_collect.add_argument("--at", required=True)
    adapter_collect.add_argument("--output", required=True)
    adapter_collect.add_argument("--json", action="store_true")

    adapter_set = durable_commands.add_parser(
        "adapter-set", help="compile a deterministic set of source observations"
    )
    adapter_set.add_argument("observations", nargs="+")
    adapter_set.add_argument("--created-at", required=True)
    adapter_set.add_argument("--output", required=True)
    adapter_set.add_argument("--json", action="store_true")

    maintenance = durable_commands.add_parser(
        "maintenance-propose", help="compare observations and emit a review-only proposal"
    )
    maintenance.add_argument("previous")
    maintenance.add_argument("current")
    maintenance.add_argument("--region", required=True)
    maintenance.add_argument("--created-at", required=True)
    maintenance.add_argument("--output", required=True)
    maintenance.add_argument("--json", action="store_true")

    search_index = durable_commands.add_parser(
        "search-index", help="compile an optional visibility-aware local index"
    )
    search_index.add_argument("observation_set")
    search_index.add_argument("--created-at", required=True)
    search_index.add_argument("--disabled-reason")
    search_index.add_argument("--output", required=True)
    search_index.add_argument("--json", action="store_true")

    search_query = durable_commands.add_parser(
        "search-query", help="query one local index with a visibility boundary"
    )
    search_query.add_argument("index")
    search_query.add_argument("query")
    search_query.add_argument(
        "--visibility",
        choices=("private", "shared", "classroom", "public", "archived"),
        required=True,
    )
    search_query.add_argument("--limit", type=_bounded_integer(1, 100), default=20)
    search_query.add_argument("--json", action="store_true")

    search_suggest = durable_commands.add_parser(
        "search-suggest", help="derive cited relationship, orphan and contradiction hints"
    )
    search_suggest.add_argument("index")
    search_suggest.add_argument(
        "--visibility",
        choices=("private", "shared", "classroom", "public", "archived"),
        required=True,
    )
    search_suggest.add_argument("--json", action="store_true")

    profiles = durable_commands.add_parser(
        "profiles", help="show deterministic local operation profiles"
    )
    profiles.add_argument("--output")
    profiles.add_argument("--json", action="store_true")

    health = durable_commands.add_parser(
        "health", help="aggregate declared component health without probing"
    )
    health.add_argument("input")
    health.add_argument("--at", required=True)
    health.add_argument("--output", required=True)
    health.add_argument("--json", action="store_true")

    backup = durable_commands.add_parser(
        "backup-manifest", help="checksum declared non-secret files without copying them"
    )
    backup.add_argument("declaration")
    backup.add_argument("--root", required=True)
    backup.add_argument("--created-at", required=True)
    backup.add_argument("--output", required=True)
    backup.add_argument("--json", action="store_true")

    restore = durable_commands.add_parser(
        "restore-verify", help="verify a staged restore without overwriting live state"
    )
    restore.add_argument("manifest")
    restore.add_argument("--staged-root", required=True)
    restore.add_argument("--verified-at", required=True)
    restore.add_argument("--output", required=True)
    restore.add_argument("--json", action="store_true")

    rotation = durable_commands.add_parser(
        "oauth-rotation-plan", help="compile a no-token OAuth rotation plan"
    )
    rotation.add_argument("input")
    rotation.add_argument("--created-at", required=True)
    rotation.add_argument("--output", required=True)
    rotation.add_argument("--json", action="store_true")

    drill = durable_commands.add_parser(
        "kill-switch-drill", help="compile evidence for a completed kill-switch drill"
    )
    drill.add_argument("input")
    drill.add_argument("--created-at", required=True)
    drill.add_argument("--output", required=True)
    drill.add_argument("--json", action="store_true")

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

    visual_live = commands.add_parser(
        "visual-v2-live-test", help="create and verify the canonical Visual System v2 board"
    )
    visual_live.add_argument("--alias", default="schauwerk-visual-system-v2-20260712")
    visual_live.add_argument(
        "--board-name", default="Schauwerk Visual System v2 – Klarheit vor Dekoration"
    )
    visual_live.add_argument("--output-dir")
    visual_live.add_argument("--replace-alias", action="store_true")
    visual_live.add_argument(
        "--reuse-existing-alias",
        action="store_true",
        help="continue a previously created Visual System v2 test board",
    )
    visual_live.add_argument(
        "--resume-after-layout",
        action="store_true",
        help="verify and close a partial run whose layout was already created",
    )
    visual_live.add_argument("--item-limit", type=_bounded_integer(10, 1000), default=200)
    visual_live.add_argument("--comment-limit", type=_bounded_integer(1, 50), default=50)
    visual_live.add_argument("--max-pages", type=_bounded_integer(1, 100), default=20)
    visual_live.add_argument("--no-comments", action="store_true")
    visual_live.add_argument("--json", action="store_true")

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

    sw009_bundle_template = rc.add_parser(
        "sw009-live-bundle-template",
        help="emit an editable owner-only live operation draft",
    )
    sw009_bundle_template.add_argument("input")
    sw009_bundle_template.add_argument("--bundle-id", default="sw009-live-bundle-edit-me")
    sw009_bundle_template.add_argument("--output", required=True)
    sw009_bundle_template.add_argument("--json", action="store_true")

    sw009_bundle_compile = rc.add_parser(
        "sw009-live-bundle-compile",
        help="validate and digest-bind one owner-only live operation draft",
    )
    sw009_bundle_compile.add_argument("draft")
    sw009_bundle_compile.add_argument("--output", required=True)
    sw009_bundle_compile.add_argument("--json", action="store_true")

    sw009_authorization_create = rc.add_parser(
        "sw009-live-authorization-create",
        help="bind one live gate and operation bundle to an expiring authorization",
    )
    sw009_authorization_create.add_argument("gate")
    sw009_authorization_create.add_argument("--bundle", required=True)
    sw009_authorization_create.add_argument("--authorization-id", required=True)
    sw009_authorization_create.add_argument("--approved-by", required=True)
    sw009_authorization_create.add_argument("--approval-reference", required=True)
    sw009_authorization_create.add_argument(
        "--confirmation",
        required=True,
        help="must be exactly APPROVE_LIVE_APPLY",
    )
    sw009_authorization_create.add_argument(
        "--valid-minutes", type=_bounded_integer(1, 1440), default=60
    )
    sw009_authorization_create.add_argument("--output", required=True)
    sw009_authorization_create.add_argument("--json", action="store_true")

    sw009_live_plan = rc.add_parser(
        "sw009-live-plan", help="compile a fully bound live apply plan without mutation"
    )
    sw009_live_plan.add_argument("gate")
    sw009_live_plan.add_argument("--bundle", required=True)
    sw009_live_plan.add_argument("--authorization", required=True)
    sw009_live_plan.add_argument("--output", required=True)
    sw009_live_plan.add_argument("--json", action="store_true")

    sw009_live_apply = rc.add_parser(
        "sw009-live-apply", help="execute one reviewed managed-region live transaction"
    )
    sw009_live_apply.add_argument("gate")
    sw009_live_apply.add_argument("--bundle", required=True)
    sw009_live_apply.add_argument("--authorization", required=True)
    sw009_live_apply.add_argument(
        "--plan", required=True, help="owner-only reviewed plan to bind execution"
    )
    sw009_live_apply.add_argument("--output", required=True)
    sw009_live_apply.add_argument("--json", action="store_true")

    sw009_live_restore = rc.add_parser(
        "sw009-live-restore", help="restore one committed managed-region transaction"
    )
    sw009_live_restore.add_argument("transaction_receipt")
    sw009_live_restore.add_argument("--output", required=True)
    sw009_live_restore.add_argument("--json", action="store_true")

    sw009_kill_switch = rc.add_parser(
        "sw009-kill-switch", help="inspect, enable or explicitly disable live apply"
    )
    sw009_kill_switch.add_argument("action", choices=("status", "enable", "disable"))
    sw009_kill_switch.add_argument("--reason")
    sw009_kill_switch.add_argument(
        "--confirmation", help="disable requires exactly ENABLE_LIVE_APPLY"
    )
    sw009_kill_switch.add_argument("--json", action="store_true")

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
