from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import stat
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from schauwerk.runner import main
from schauwerk.surfaces.miro.errors import (
    MiroConnectionError,
    MiroCredentialError,
    MiroToolError,
)
from schauwerk.surfaces.miro.models import MiroSettings
from schauwerk.surfaces.miro.native_executor import (
    NativeBundleError,
    NativeExecutionError,
    _canvas_svg_evidence,
    compile_diagram_dsl_to_mermaid,
    execute_native_bundle,
    load_native_bundle,
    load_native_resume_receipt,
    render_canvas_diagram_svg,
    required_tools,
    validate_native_bundle,
)
from schauwerk.surfaces.miro.native_runtime import (
    native_board_lock,
    native_receipt_lock,
    prepare_native_destination,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/miro-native-bundle-v1.json"
BOARD_URL = "https://miro.com/app/board/uXjVNativeTest=/"
PREVIEW_RESOURCE = "miro-preview://create/abcdefghijklmnop"
PREVIEW_BYTES = b"provider-preview-png"


def catalogue(*names: str) -> list[dict]:
    return [
        {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": True},
            "output_schema": {"type": "object", "additionalProperties": True},
        }
        for name in names
    ]


class FakeMiro:
    def __init__(
        self,
        *,
        document_matches: bool = True,
        provider_preview: bool = False,
        provider_preview_status: str = "ready",
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.document_matches = document_matches
        self.provider_preview = provider_preview
        self.provider_preview_status = provider_preview_status
        self.inventory_reads = 0
        self.context_reads = 0
        self.comment_created = False

    async def __call__(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, copy.deepcopy(arguments)))
        if tool == "user_who_am_i":
            return {
                "org_id": "org",
                "team_id": "team",
                "user_id": "user",
                "workspace_id": "workspace",
            }
        if tool == "board_list_items":
            self.inventory_reads += 1
            items = [{"id": "before", "type": "frame"}]
            if self.inventory_reads > 1:
                items.extend(
                    [
                        {"id": "diagram", "type": "shape"},
                        {"id": "doc", "type": "doc_format"},
                        {"id": "table", "type": "data_table_format"},
                        {"id": "code", "type": "code"},
                    ]
                )
            return {
                "data": items,
                "total": len(items),
                "has_more": False,
                "nextCursor": None,
            }
        if tool == "context_explore":
            self.context_reads += 1
            items = [
                {"miro_url": f"{BOARD_URL}?moveToWidget=frame", "title": "Frame", "type": "frame"}
            ]
            if self.context_reads > 1:
                items.extend(
                    [
                        {
                            "miro_url": f"{BOARD_URL}?moveToWidget=diagram",
                            "title": "Diagram",
                            "type": "diagram",
                        },
                        {
                            "miro_url": f"{BOARD_URL}?moveToWidget=doc",
                            "title": "Doc",
                            "type": "document",
                        },
                        {
                            "miro_url": f"{BOARD_URL}?moveToWidget=table",
                            "title": "Table",
                            "type": "table",
                        },
                    ]
                )
            return {"items": items}
        if tool == "layout_get_dsl":
            return {
                "spec": "FRAME and TEXT syntax",
                "example": "root FRAME x=0 y=0 w=100 h=100 title",
            }
        if tool == "layout_create":
            return {
                "success": True,
                "message": "created",
                "created_count": 2,
                "failed_items": [],
                "miro_url": BOARD_URL,
                "result_dsl": "frame-url FRAME x=0 y=0 w=100 h=100 title",
            }
        if tool == "layout_read":
            return {
                "success": True,
                "message": "read",
                "dsl": "frame-url FRAME x=0 y=0 w=100 h=100 title",
                "item_count": 2,
                "connector_count": 0,
                "skipped_count": 0,
                "miro_url": BOARD_URL,
            }
        if tool == "diagram_get_dsl":
            return {
                "diagram_type": arguments["diagram_type"],
                "data": {"spec": "node/edge", "example": "node a"},
            }
        if tool == "diagram_create":
            payload = {"miro_url": f"{BOARD_URL}?moveToWidget=diagram"}
            if not self.provider_preview:
                return payload
            return SimpleNamespace(
                structuredContent=payload,
                content=[SimpleNamespace(type="resource_link", uri=PREVIEW_RESOURCE)],
                isError=False,
            )
        if tool == "preview_resource_poll":
            assert self.provider_preview is True
            assert arguments["preview_resource"] == PREVIEW_RESOURCE
            if self.provider_preview_status != "ready":
                return {"status": self.provider_preview_status}
            return {
                "status": "ready",
                "mime_type": "image/png",
                "data_base64": base64.b64encode(PREVIEW_BYTES).decode("ascii"),
            }
        if tool == "context_get":
            return {
                "miro_url": arguments["miro_url"],
                "content": "Diagram with Operator and Schauwerk nodes",
            }
        if tool == "doc_create":
            return {"miro_url": f"{BOARD_URL}?moveToWidget=doc"}
        if tool == "doc_get":
            content = "# Native Miro\n\nEditable provider objects with receipt-bound readback."
            if not self.document_matches:
                content = "provider changed the document"
            return {
                "miro_url": arguments["miro_url"],
                "content": content,
                "content_version": 1,
                "success": True,
                "message": "ok",
            }
        if tool == "table_create":
            return {"miro_url": f"{BOARD_URL}?moveToWidget=table"}
        if tool == "table_sync_rows":
            return {"success": True, "miro_url": arguments["miro_url"]}
        if tool == "table_list_rows":
            return {
                "miro_url": arguments["miro_url"],
                "rows": [
                    {
                        "rowId": "1",
                        "cells": [
                            {"columnTitle": "Lane", "content": "Native diagram"},
                            {
                                "columnTitle": "Status",
                                "options": [{"displayValue": "Verified"}],
                            },
                        ],
                    },
                    {
                        "rowId": "2",
                        "cells": [
                            {"columnTitle": "Lane", "content": "Living document"},
                            {
                                "columnTitle": "Status",
                                "options": [{"displayValue": "Verified"}],
                            },
                        ],
                    },
                ],
                "total": 2,
                "cursor": None,
            }
        if tool == "table_update_view":
            return {"miro_url": arguments["miro_url"], "layout": arguments["layout"]}
        if tool == "code_widget_create":
            return {"miro_url": f"{BOARD_URL}?moveToWidget=code"}
        if tool == "code_widget_get":
            return {
                "miro_url": arguments["miro_url"],
                "code": "flowchart LR\n  Operator --> Schauwerk\n  Schauwerk --> Miro",
                "language": "Mermaid",
                "title": "Editable Mermaid source",
                "line_numbers_visible": True,
                "width": 900,
                "height": 500,
                "x": 500,
                "y": 500,
                "success": True,
                "message": "ok",
            }
        if tool == "comment_create":
            self.comment_created = True
            return {"id": "comment-1"}
        if tool == "comment_list_comments":
            data = []
            if self.comment_created:
                data = [
                    {
                        "id": "comment-1",
                        "messages": [
                            {
                                "id": "message-1",
                                "content": ("Schauwerk native executor verification marker"),
                            }
                        ],
                    }
                ]
            return {
                "data": data,
                "total": len(data),
                "offset": 0,
                "limit": 50,
                "board_id": "board",
                "board_url": BOARD_URL,
            }
        raise AssertionError(f"unexpected tool: {tool}")


def live_tools(bundle: dict) -> list[dict]:
    return catalogue(*required_tools(bundle))


def current_diagram_bundle(*, diagram_dsl: str | None = None) -> dict:
    return validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "current-canvas-diagram",
            "operations": [
                {
                    "operation_id": "current-diagram",
                    "kind": "diagram",
                    "title": "Aktueller & editierbarer Ablauf",
                    "diagram_type": "flowchart",
                    "diagram_dsl": diagram_dsl
                    or (
                        "graphdir LR\n"
                        "palette #E8F0FE #E6F4EA #FCE8E6\n"
                        "start Start & Auftrag flowchart-process 0\n"
                        "choice Freigabe <jetzt>? flowchart-decision 1\n"
                        "end Fertig flowchart-terminator 2\n"
                        "c start prüft | sicher choice\n"
                        "c choice bestätigt end\n"
                        'cluster lane "Prüfung & Übergabe" start choice end\n'
                    ),
                    "x": 125,
                    "y": -75,
                }
            ],
        }
    )


def canvas_tools(*, include_svg_readback: bool = True) -> list[dict]:
    names = [
        "user_who_am_i",
        "board_list_items",
        "context_explore",
        "context_get",
        "canvas_get_canvas_composer_skill",
        "canvas_load_format_skill",
        "canvas_create_from_svg",
    ]
    if include_svg_readback:
        names.append("canvas_read_as_svg")
    return catalogue(*names)


def canvas_resume_bundle() -> dict:
    diagram = copy.deepcopy(current_diagram_bundle()["operations"][0])
    diagram["operation_id"] = "beziehungsarbeit-wissenskarte"
    diagram["title"] = "Wissenskarte"
    return validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "canvas-resume-reconciliation",
            "operations": [
                diagram,
                {
                    "operation_id": "resume-followup",
                    "kind": "document",
                    "content": "# Fortsetzung\n\nNach verifizierter Wissenskarte.",
                    "x": 1900,
                    "y": -75,
                },
            ],
        }
    )


def canvas_inventory_item(bundle: dict, *, item_id: str = "42") -> dict:
    operation = bundle["operations"][0]
    return {
        "data": {
            "code": compile_diagram_dsl_to_mermaid(operation["diagram_dsl"]),
            "title": operation["title"],
        },
        "geometry": {"width": 1600, "height": 900},
        "id": item_id,
        "miro_url": f"{BOARD_URL}?moveToWidget={item_id}",
        "parent": None,
        "position": {"x": operation["x"], "y": operation["y"]},
        "style": {},
        "type": "diagram",
    }


def pending_canvas_receipt(bundle: dict, *, baseline_count: int = 0) -> dict:
    receipt = {
        "schema_version": "schauwerk-miro-native-execution-receipt.v1",
        "success": False,
        "execution_state": "in_progress",
        "bundle_digest": bundle["bundle_digest"],
        "board_alias": "native-test",
        "board_reference_digest": hashlib.sha256(BOARD_URL.encode("utf-8")).hexdigest()[:24],
        "completed_operations": [],
        "completed_operation_count": 0,
        "preflight": {
            "inventory": {"item_count": baseline_count},
            "context": {"item_count": baseline_count},
        },
        "calls": [],
        "pending_operation_id": "beziehungsarbeit-wissenskarte",
        "pending_tool": "canvas_create_from_svg",
        "mutation_attempted": True,
    }
    receipt["execution_digest"] = _receipt_digest(receipt)
    return receipt


class CurrentCanvasMiro(FakeMiro):
    def __init__(
        self,
        *,
        context_title: str | None = None,
        context_metadata: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        self.context_title = context_title
        self.context_metadata = copy.deepcopy(context_metadata or {})
        self.canvas_svg: str | None = None
        self.canvas_svgs: dict[str, str] = {}

    async def __call__(self, tool: str, arguments: dict) -> dict:
        if tool == "canvas_get_canvas_composer_skill":
            self.calls.append((tool, copy.deepcopy(arguments)))
            return {"skill": "Compose supported Canvas SVG elements."}
        if tool == "canvas_load_format_skill":
            self.calls.append((tool, copy.deepcopy(arguments)))
            assert arguments["format_name"] == "diagramming"
            assert arguments["notation"] == "flowchart"
            return {"skill": "Use Mermaid 10.3 flowchart notation."}
        if tool == "canvas_create_from_svg":
            self.calls.append((tool, copy.deepcopy(arguments)))
            item_id = str(42 + len(self.canvas_svgs))
            self.canvas_svg = arguments["svg"].replace(
                ' data-type="diagram"',
                f' data-miro-id="{item_id}" data-type="diagram"',
                1,
            )
            self.canvas_svgs[item_id] = self.canvas_svg
            return {
                "success": True,
                "created_count": 1,
                "failed_items": [],
                "miro_url": BOARD_URL,
                "result_svg": self.canvas_svg,
            }
        if tool == "context_get":
            for item_id, svg in self.canvas_svgs.items():
                if f"moveToWidget={item_id}" in arguments["miro_url"]:
                    self.calls.append((tool, copy.deepcopy(arguments)))
                    diagram = next(
                        element
                        for element in ET.fromstring(svg).iter()
                        if element.tag.rsplit("}", 1)[-1] == "foreignObject"
                    )
                    result = {
                        "content": "".join(diagram.itertext()),
                        "miro_url": arguments["miro_url"],
                        "parent_miro_url": BOARD_URL,
                        "x": 125,
                        "y": -75,
                    }
                    if self.context_title is not None:
                        result["title"] = self.context_title
                    result.update(copy.deepcopy(self.context_metadata))
                    return result
        if tool == "canvas_read_as_svg":
            self.calls.append((tool, copy.deepcopy(arguments)))
            for item_id, svg in self.canvas_svgs.items():
                if f"moveToWidget={item_id}" in arguments["miro_url"]:
                    return {"success": True, "svg": svg}
            raise AssertionError("unknown Canvas item reference")
        return await super().__call__(tool, arguments)


class CanvasResumeMiro(CurrentCanvasMiro):
    def __init__(
        self,
        bundle: dict,
        *,
        candidates: list[dict] | None = None,
        interrupt_context_once: bool = False,
        interrupt_tool_once: str | None = None,
        paginate_inventory: bool = False,
    ) -> None:
        super().__init__()
        self.bundle = bundle
        self.candidates = copy.deepcopy(candidates or [])
        self.interrupt_context_once = interrupt_context_once
        self.interrupt_tool_once = interrupt_tool_once
        self.paginate_inventory = paginate_inventory
        self.document_created = False

    async def __call__(self, tool: str, arguments: dict) -> dict:
        if tool == self.interrupt_tool_once:
            self.calls.append((tool, copy.deepcopy(arguments)))
            self.interrupt_tool_once = None
            raise MiroToolError(f"interrupted {tool}")
        if tool == "board_list_items":
            self.calls.append((tool, copy.deepcopy(arguments)))
            items = copy.deepcopy(self.candidates)
            if self.document_created:
                items.append(
                    {
                        "id": "doc",
                        "miro_url": f"{BOARD_URL}?moveToWidget=doc",
                        "type": "doc_format",
                    }
                )
            cursor = arguments.get("cursor")
            if self.paginate_inventory and items and cursor is None:
                return {
                    "data": [],
                    "total": len(items),
                    "has_more": True,
                    "nextCursor": "canvas-next",
                }
            if cursor is not None:
                assert cursor == "canvas-next"
            return {
                "data": items,
                "total": len(items),
                "has_more": False,
                "nextCursor": None,
            }
        if tool == "context_explore":
            self.calls.append((tool, copy.deepcopy(arguments)))
            return {"items": []}
        if tool == "canvas_create_from_svg":
            created = await super().__call__(tool, arguments)
            self.candidates = [canvas_inventory_item(self.bundle)]
            return created
        if (
            tool == "context_get"
            and "moveToWidget=42" in arguments["miro_url"]
            and self.interrupt_context_once
        ):
            self.calls.append((tool, copy.deepcopy(arguments)))
            self.interrupt_context_once = False
            raise MiroToolError("interrupted Canvas context readback")
        if tool == "doc_create":
            self.calls.append((tool, copy.deepcopy(arguments)))
            self.document_created = True
            return {"miro_url": f"{BOARD_URL}?moveToWidget=doc"}
        if tool == "doc_get":
            self.calls.append((tool, copy.deepcopy(arguments)))
            return {
                "miro_url": arguments["miro_url"],
                "content": self.bundle["operations"][1]["content"],
                "content_version": 1,
                "success": True,
                "message": "ok",
            }
        return await super().__call__(tool, arguments)


def test_current_dsl_conversion_is_deterministic_and_preserves_semantics() -> None:
    operation = current_diagram_bundle()["operations"][0]

    first = compile_diagram_dsl_to_mermaid(operation["diagram_dsl"])
    second = compile_diagram_dsl_to_mermaid(operation["diagram_dsl"])
    svg = render_canvas_diagram_svg(operation, first)

    assert first == second
    assert first.startswith("flowchart LR\n")
    assert '(["Fertig"])' in first
    assert '{"Freigabe &lt;jetzt&gt;?"}' in first
    assert '["Start &amp; Auftrag"]' in first
    assert '-->|"prüft &#124; sicher"|' in first
    assert '["Prüfung &amp; Übergabe"]' in first
    assert "classDef swPalette0 fill:#E8F0FE;" in first
    assert "classDef swPalette1 fill:#E6F4EA;" in first
    assert "classDef swPalette2 fill:#FCE8E6;" in first
    assert "class " in first
    assert 'width="1600" height="900"' in svg
    assert 'x="125" y="-75"' in svg
    assert 'data-type="diagram"' in svg
    assert 'data-title="Aktueller &amp; editierbarer Ablauf"' in svg
    assert "&amp;amp; Auftrag" in svg
    assert "Start & Auftrag" not in svg


@pytest.mark.parametrize(
    "diagram_dsl,message",
    [
        (
            "graphdir LR\npalette #E8F0FE\na A flowchart-process 0\nwat nope\n",
            "unknown or invalid directive",
        ),
        (
            "graphdir LR\npalette #E8F0FE\na A flowchart-process 0\na B flowchart-process 0\n",
            "duplicate id",
        ),
        (
            "graphdir LR\npalette #E8F0FE\na A flowchart-process 0\nc a goes missing\n",
            "unknown node",
        ),
        (
            "graphdir LR\npalette #E8F0FE\na A flowchart-process 1\n",
            "out-of-range palette index",
        ),
        (
            "graphdir LR\npalette #E8F0FE\na A flowchart-cloud 0\n",
            "unknown or invalid directive",
        ),
        (
            "graphdir LR\npalette blue\na A flowchart-process 0\n",
            "invalid palette",
        ),
    ],
)
def test_current_dsl_conversion_rejects_invalid_input(diagram_dsl: str, message: str) -> None:
    with pytest.raises(NativeBundleError, match=message):
        compile_diagram_dsl_to_mermaid(diagram_dsl)


def test_canvas_native_execution_preloads_skills_and_verifies_both_readbacks() -> None:
    bundle = current_diagram_bundle()
    fake = CurrentCanvasMiro()

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=canvas_tools(),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    called = [name for name, _arguments in fake.calls]
    create_index = called.index("canvas_create_from_svg")
    assert called.index("canvas_get_canvas_composer_skill") < create_index
    assert called.index("canvas_load_format_skill") < create_index
    assert called.index("context_get") > create_index
    assert called.index("canvas_read_as_svg") > called.index("context_get")
    assert called.count("canvas_get_canvas_composer_skill") == 1
    assert called.count("canvas_load_format_skill") == 1
    assert "diagram_create" not in called
    assert "diagram_create_mermaid" not in called
    assert receipt["provider_fallback_count"] == 0
    resolution = receipt["provider_resolution"][0]
    assert resolution["mode"] == "native"
    assert resolution["native_transport"] == "canvas_diagram"
    readback = receipt["completed_operations"][0]["readback"]
    assert readback["provider_mode"] == "native"
    assert readback["native_transport"] == "canvas_diagram"
    assert readback["skills_loaded"] is True
    assert readback["skills_schema_validated"] is True
    assert readback["created_svg"]["title_matches"] is True
    assert readback["context"]["diagram_semantics"] is True
    assert readback["context"]["source_matches"] is True
    assert readback["context"]["title_exposed"] is False
    assert readback["context"]["title_matches"] is True
    assert readback["canvas_svg_schema_available"] is True
    assert readback["canvas_svg_verified"] is True
    assert readback["item_reference_derived"] is True
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    assert BOARD_URL not in encoded
    assert "Aktueller & editierbarer Ablauf" not in encoded
    assert "flowchart LR" not in encoded


def test_canvas_svg_readback_selects_unique_expected_diagram_from_board_svg() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<foreignObject data-type="diagram" data-title="Anderes Diagramm" '
        'width="1600" height="900">'
        'flowchart LR\nX --> Y'
        '</foreignObject>'
        '<foreignObject data-type="diagram" data-title="Erwartetes Diagramm" '
        'width="1600" height="900">'
        '\nflowchart LR\nA --> B'
        '</foreignObject>'
        '</svg>'
    )

    evidence = _canvas_svg_evidence(
        svg,
        expected_title="Erwartetes Diagramm",
        expected_source="flowchart LR\nA --> B",
        local_id=None,
        require_item_id=False,
    )

    assert evidence["title_matches"] is True
    assert evidence["source_matches"] is True
    assert evidence["geometry_matches"] is True


def test_canvas_svg_readback_rejects_duplicate_expected_titles_in_board_svg() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<foreignObject data-type="diagram" data-title="Erwartetes Diagramm" '
        'width="1600" height="900">'
        'flowchart LR\nA --> B'
        '</foreignObject>'
        '<foreignObject data-type="diagram" data-title="Erwartetes Diagramm" '
        'width="1600" height="900">'
        'flowchart LR\nC --> D'
        '</foreignObject>'
        '</svg>'
    )

    with pytest.raises(MiroToolError, match="expected structured diagram exactly once"):
        _canvas_svg_evidence(
            svg,
            expected_title="Erwartetes Diagramm",
            expected_source="flowchart LR\nA --> B",
            local_id=None,
            require_item_id=False,
        )


def test_canvas_svg_readback_keeps_source_check_after_board_svg_selection() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<foreignObject data-type="diagram" data-title="Anderes Diagramm" '
        'width="1600" height="900">'
        'flowchart LR\nX --> Y'
        '</foreignObject>'
        '<foreignObject data-type="diagram" data-title="Erwartetes Diagramm" '
        'width="1600" height="900">'
        'flowchart LR\nC --> D'
        '</foreignObject>'
        '</svg>'
    )

    with pytest.raises(MiroToolError, match="diagram source does not match"):
        _canvas_svg_evidence(
            svg,
            expected_title="Erwartetes Diagramm",
            expected_source="flowchart LR\nA --> B",
            local_id=None,
            require_item_id=False,
        )


def test_canvas_context_explicit_conflicting_title_fails() -> None:
    fake = CurrentCanvasMiro(context_title="Falscher Titel")

    with pytest.raises(NativeExecutionError, match="title conflicts"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=canvas_tools(),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=current_diagram_bundle(),
            )
        )

    called = [name for name, _arguments in fake.calls]
    assert called.count("canvas_create_from_svg") == 1
    assert "canvas_read_as_svg" not in called


def test_canvas_context_ignores_foreign_nested_metadata_names() -> None:
    bundle = current_diagram_bundle()
    fake = CurrentCanvasMiro(
        context_title=bundle["operations"][0]["title"],
        context_metadata={
            "creator": {"name": "Provider User"},
            "container": {"name": "Provider Space"},
        },
    )

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=canvas_tools(),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    context = receipt["completed_operations"][0]["readback"]["context"]
    assert context["title_exposed"] is True
    assert context["title_matches"] is True
    assert context["source_matches"] is True


def test_pending_canvas_resume_adopts_exact_candidate_and_continues() -> None:
    bundle = canvas_resume_bundle()
    tools = [*canvas_tools(), *catalogue("doc_create", "doc_get")]
    fake = CanvasResumeMiro(
        bundle,
        interrupt_context_once=True,
        paginate_inventory=True,
    )
    checkpoints: list[dict] = []

    with pytest.raises(NativeExecutionError, match="interrupted Canvas context"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=tools,
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                checkpoint=checkpoints.append,
            )
        )

    resume = checkpoints[-1]
    assert resume["pending_operation_id"] == "beziehungsarbeit-wissenskarte"
    assert resume["pending_tool"] == "canvas_create_from_svg"
    assert resume["completed_operations"] == []
    resume_call_count = len(fake.calls)

    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=tools,
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
            resume_receipt=resume,
            checkpoint=checkpoints.append,
        )
    )

    resumed_tools = [tool for tool, _arguments in fake.calls[resume_call_count:]]
    assert resumed_tools.count("board_list_items") == 4
    assert "canvas_create_from_svg" not in resumed_tools
    assert "doc_create" in resumed_tools
    assert result["success"] is True
    assert result["completed_operation_count"] == 2
    assert result["pending_operation_id"] is None
    assert result["pending_tool"] is None
    diagram_readback = result["completed_operations"][0]["readback"]
    assert diagram_readback["reconciled_existing"] is True
    assert diagram_readback["inventory_reconciliation"] == {
        "item_type_matches": True,
        "title_matches": True,
        "source_matches": True,
        "geometry_matches": True,
        "position_matches": True,
        "item_reference_verified": True,
    }
    assert diagram_readback["context"]["title_exposed"] is False
    assert diagram_readback["canvas_svg_verified"] is True
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert BOARD_URL not in encoded
    assert "Wissenskarte" not in encoded
    assert "flowchart LR" not in encoded


@pytest.mark.parametrize(
    "interrupt_tool",
    [
        "user_who_am_i",
        "canvas_get_canvas_composer_skill",
        "context_get",
        "canvas_read_as_svg",
    ],
)
def test_pending_canvas_resume_preserves_markers_across_transient_reconciliation_failures(
    interrupt_tool: str,
) -> None:
    bundle = canvas_resume_bundle()
    tools = [*canvas_tools(), *catalogue("doc_create", "doc_get")]
    fake = CanvasResumeMiro(
        bundle,
        interrupt_context_once=True,
    )
    checkpoints: list[dict] = []

    with pytest.raises(NativeExecutionError, match="interrupted Canvas context"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=tools,
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                checkpoint=checkpoints.append,
            )
        )

    initial_resume = checkpoints[-1]
    fake.interrupt_tool_once = interrupt_tool
    with pytest.raises(NativeExecutionError, match=f"interrupted {interrupt_tool}"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=tools,
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=initial_resume,
                checkpoint=checkpoints.append,
            )
        )

    failed_resume = checkpoints[-1]
    assert failed_resume["pending_operation_id"] == "beziehungsarbeit-wissenskarte"
    assert failed_resume["pending_tool"] == "canvas_create_from_svg"
    assert failed_resume["completed_operations"] == []

    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=tools,
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
            resume_receipt=failed_resume,
            checkpoint=checkpoints.append,
        )
    )

    called = [tool for tool, _arguments in fake.calls]
    assert called.count("canvas_create_from_svg") == 1
    assert result["success"] is True
    assert result["completed_operation_count"] == 2
    assert result["pending_operation_id"] is None
    assert result["pending_tool"] is None
    assert result["completed_operations"][0]["readback"]["reconciled_existing"] is True


def test_pending_canvas_resume_accepts_provider_stripped_terminal_newline() -> None:
    bundle = canvas_resume_bundle()
    candidate = canvas_inventory_item(bundle)
    source = candidate["data"]["code"]
    assert source.endswith("\n")
    candidate["data"]["code"] = source[:-1]
    fake = CanvasResumeMiro(bundle, candidates=[candidate])
    operation = bundle["operations"][0]
    svg = render_canvas_diagram_svg(operation, source).replace(
        ' data-type="diagram"',
        ' data-miro-id="42" data-type="diagram"',
        1,
    )
    fake.canvas_svg = svg
    fake.canvas_svgs["42"] = svg

    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=[*canvas_tools(), *catalogue("doc_create", "doc_get")],
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
            resume_receipt=pending_canvas_receipt(bundle),
        )
    )

    called = [tool for tool, _arguments in fake.calls]
    assert "canvas_create_from_svg" not in called
    assert result["success"] is True
    assert result["completed_operations"][0]["readback"]["reconciled_existing"] is True
    assert result["completed_operations"][0]["readback"]["inventory_reconciliation"][
        "source_matches"
    ] is True


@pytest.mark.parametrize(
    ("case", "baseline_count", "message"),
    [
        ("zero", 0, "unexpected inventory delta"),
        ("multiple", 1, "multiple exact candidates"),
        ("wrong_type", 0, "no exact candidate"),
        ("wrong_title", 0, "no exact candidate"),
        ("wrong_code", 0, "no exact candidate"),
        ("wrong_geometry", 0, "no exact candidate"),
        ("wrong_position", 0, "no exact candidate"),
        ("wrong_url", 0, "no exact candidate"),
        ("unexpected_delta", 0, "unexpected inventory delta"),
    ],
)
def test_pending_canvas_resume_rejects_ambiguous_or_mismatched_inventory_before_mutation(
    case: str, baseline_count: int, message: str
) -> None:
    bundle = canvas_resume_bundle()
    exact = canvas_inventory_item(bundle)
    candidates: list[dict]
    if case == "zero":
        candidates = []
    elif case == "multiple":
        candidates = [exact, canvas_inventory_item(bundle, item_id="43")]
    elif case == "unexpected_delta":
        candidates = [exact, {"id": "other", "type": "shape"}]
    else:
        candidate = copy.deepcopy(exact)
        if case == "wrong_type":
            candidate["type"] = "shape"
        elif case == "wrong_title":
            candidate["data"]["title"] = "Andere Wissenskarte"
        elif case == "wrong_code":
            candidate["data"]["code"] += "\nflowchart TD"
        elif case == "wrong_geometry":
            candidate["geometry"]["width"] = 1599
        elif case == "wrong_position":
            candidate["position"]["x"] += 1
        elif case == "wrong_url":
            candidate["miro_url"] = "https://miro.com/app/board/other/?moveToWidget=42"
        candidates = [candidate]
    fake = CanvasResumeMiro(bundle, candidates=candidates)

    with pytest.raises(NativeExecutionError, match=message):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=[*canvas_tools(), *catalogue("doc_create", "doc_get")],
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=pending_canvas_receipt(
                    bundle,
                    baseline_count=baseline_count,
                ),
            )
        )

    called = [tool for tool, _arguments in fake.calls]
    assert "canvas_create_from_svg" not in called
    assert "doc_create" not in called


def test_invalid_canvas_dsl_fails_before_any_provider_call() -> None:
    bundle = current_diagram_bundle(
        diagram_dsl="graphdir LR\npalette #E8F0FE\na Bad flowchart-cloud 0\n"
    )
    fake = CurrentCanvasMiro()

    with pytest.raises(NativeBundleError, match="unknown or invalid directive"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=canvas_tools(),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )

    assert fake.calls == []


def test_canvas_skills_are_cached_once_for_multiple_diagrams() -> None:
    bundle = current_diagram_bundle()
    second = copy.deepcopy(bundle["operations"][0])
    second["operation_id"] = "current-diagram-2"
    bundle = validate_native_bundle(
        {
            key: value
            for key, value in {**bundle, "operations": [*bundle["operations"], second]}.items()
            if key != "bundle_digest"
        }
    )
    fake = CurrentCanvasMiro()

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=canvas_tools(),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    called = [name for name, _arguments in fake.calls]
    assert receipt["completed_operation_count"] == 2
    assert called.count("canvas_create_from_svg") == 2
    assert called.count("canvas_get_canvas_composer_skill") == 1
    assert called.count("canvas_load_format_skill") == 1


class LeadingLfCanvasReadbackMiro(CurrentCanvasMiro):
    def __init__(self, leading_lf_count: int) -> None:
        super().__init__()
        self.leading_lf_count = leading_lf_count

    async def __call__(self, tool: str, arguments: dict) -> dict:
        result = await super().__call__(tool, arguments)
        if tool != "canvas_read_as_svg":
            return result
        svg = result["svg"]
        marker = 'data-type="diagram"'
        marker_index = svg.index(marker)
        tag_end = svg.index(">", marker_index) + 1
        return {
            **result,
            "svg": svg[:tag_end] + "\n" * self.leading_lf_count + svg[tag_end:],
        }


def test_canvas_svg_readback_accepts_one_provider_inserted_leading_lf() -> None:
    fake = LeadingLfCanvasReadbackMiro(1)

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=canvas_tools(),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=current_diagram_bundle(),
        )
    )

    readback = receipt["completed_operations"][0]["readback"]
    assert receipt["success"] is True
    assert readback["canvas_svg_verified"] is True


def test_canvas_svg_readback_rejects_two_provider_inserted_leading_lfs() -> None:
    fake = LeadingLfCanvasReadbackMiro(2)

    with pytest.raises(NativeExecutionError, match="SVG diagram source does not match"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=canvas_tools(),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=current_diagram_bundle(),
            )
        )


def test_canvas_svg_readback_requires_an_available_output_schema() -> None:
    tools = canvas_tools()
    next(item for item in tools if item["name"] == "canvas_read_as_svg")["output_schema"] = None
    fake = CurrentCanvasMiro()

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=tools,
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=current_diagram_bundle(),
        )
    )

    readback = receipt["completed_operations"][0]["readback"]
    assert readback["canvas_svg_schema_available"] is False
    assert readback["canvas_svg_verified"] is False
    assert "canvas_read_as_svg" not in [name for name, _arguments in fake.calls]


def test_canvas_skill_output_schema_is_required_before_provider_calls() -> None:
    tools = canvas_tools()
    next(item for item in tools if item["name"] == "canvas_get_canvas_composer_skill")[
        "output_schema"
    ] = None
    fake = CurrentCanvasMiro()

    with pytest.raises(NativeBundleError, match="lacks an output schema"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=tools,
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=current_diagram_bundle(),
            )
        )

    assert fake.calls == []


def test_provider_preview_is_supplemental_digest_bound_evidence() -> None:
    bundle = load_native_bundle(FIXTURE)
    fake = FakeMiro(provider_preview=True)
    tools = catalogue(*required_tools(bundle), "preview_resource_poll")

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=tools,
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    diagram = next(
        operation for operation in receipt["completed_operations"] if operation["kind"] == "diagram"
    )
    preview = diagram["readback"]["provider_preview"]
    encoded = json.dumps(receipt, sort_keys=True)

    assert preview["status"] == "ready"
    assert preview["mime_type"] == "image/png"
    assert preview["byte_count"] == len(PREVIEW_BYTES)
    assert preview["content_sha256"] == hashlib.sha256(PREVIEW_BYTES).hexdigest()
    assert preview["supplemental_only"] is True
    assert preview["authenticated_provider_capture_required"] is True
    assert preview["poll_attempt_count"] == 1
    assert preview["poll_call_recorded"] is True
    assert receipt["provider_preview_evidence"]["ready_operation_count"] == 1
    assert receipt["provider_preview_evidence"]["automatic_aesthetic_verdict"] is False
    assert receipt["visual_acceptance"]["status"] == "pending_authenticated_provider_capture"
    assert [name for name, _arguments in fake.calls].count("preview_resource_poll") == 1
    assert PREVIEW_RESOURCE not in encoded
    assert base64.b64encode(PREVIEW_BYTES).decode("ascii") not in encoded


def test_pending_provider_preview_does_not_fail_verified_create() -> None:
    bundle = load_native_bundle(FIXTURE)
    fake = FakeMiro(provider_preview=True, provider_preview_status="pending")
    tools = catalogue(*required_tools(bundle), "preview_resource_poll")

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=tools,
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    diagram = next(
        operation for operation in receipt["completed_operations"] if operation["kind"] == "diagram"
    )
    preview = diagram["readback"]["provider_preview"]

    assert receipt["success"] is True
    assert preview["status"] == "pending"
    assert preview["poll_attempt_count"] == 1
    assert preview["poll_call_recorded"] is True
    assert receipt["provider_preview_evidence"]["status_counts"]["pending"] == 1
    assert receipt["visual_acceptance"]["status"] == "pending_authenticated_provider_capture"


def test_bundle_is_validated_and_required_tools_are_complete() -> None:
    bundle = load_native_bundle(FIXTURE)

    assert bundle["schema_version"] == "schauwerk-miro-native-bundle.v1"
    assert len(bundle["bundle_digest"]) == 64
    assert required_tools(bundle) == (
        "board_list_items",
        "code_widget_create",
        "code_widget_get",
        "comment_create",
        "comment_list_comments",
        "context_explore",
        "context_get",
        "diagram_create",
        "diagram_get_dsl",
        "doc_create",
        "doc_get",
        "table_create",
        "table_list_rows",
        "table_sync_rows",
        "table_update_view",
        "user_who_am_i",
    )


def test_bundle_rejects_duplicate_ids_unknown_columns_and_foreign_targets() -> None:
    raw = json.loads(FIXTURE.read_text())
    raw["operations"][1]["operation_id"] = raw["operations"][0]["operation_id"]
    with pytest.raises(NativeBundleError, match="unique"):
        validate_native_bundle(raw)

    raw = json.loads(FIXTURE.read_text())
    raw["operations"][2]["rows"][0]["cells"][0]["columnTitle"] = "Missing"
    with pytest.raises(NativeBundleError, match="unknown column"):
        validate_native_bundle(raw)

    raw = json.loads(FIXTURE.read_text())
    raw["operations"][0]["target_miro_url"] = "https://miro.com/app/board/other=/"
    bundle = validate_native_bundle(raw)
    fake = FakeMiro()
    with pytest.raises(NativeExecutionError, match="outside the allowlisted board"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )


def test_executor_runs_all_native_lanes_and_returns_sanitized_readbacks() -> None:
    bundle = load_native_bundle(FIXTURE)
    fake = FakeMiro()
    checkpoints: list[dict] = []

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
            checkpoint=lambda value: checkpoints.append(copy.deepcopy(value)),
        )
    )

    assert receipt["success"] is True
    assert receipt["completed_operation_count"] == 5
    assert receipt["partial_mutation"] is False
    assert receipt["atomic"] is False
    assert receipt["visual_acceptance"] == {
        "authenticated_provider_capture_required": True,
        "status": "pending_authenticated_provider_capture",
        "automatic_aesthetic_verdict": False,
    }
    assert receipt["preflight"]["inventory"]["item_count"] == 1
    assert receipt["postflight"]["inventory"]["item_count"] == 5
    assert receipt["completed_operations"][0]["readback"]["content_present"] is True
    assert receipt["completed_operations"][1]["readback"]["content_matches"] is True
    assert receipt["completed_operations"][2]["readback"]["layout"] == "kanban"
    assert receipt["completed_operations"][2]["readback"]["submitted_rows_match"] is True
    code_readback = receipt["completed_operations"][3]["readback"]
    assert code_readback["code_matches"] is True
    assert code_readback["line_numbers_visible"] is True
    assert code_readback["width"] == 900.0
    assert code_readback["position_matches"] == {"x": True, "y": True}
    assert receipt["completed_operations"][4]["readback"]["comment_present"] is True
    assert receipt["expected_created_item_count"] == 4
    assert receipt["observed_item_count_delta"] == 4
    assert BOARD_URL not in json.dumps(receipt)
    assert checkpoints[-1] == receipt
    assert any(checkpoint["error_code"] == "in_progress" for checkpoint in checkpoints[:-1])


def test_failure_checkpoint_preserves_partial_mutation_truth() -> None:
    bundle = load_native_bundle(FIXTURE)
    fake = FakeMiro(document_matches=False)
    checkpoints: list[dict] = []

    with pytest.raises(NativeExecutionError, match="does not match"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                checkpoint=lambda value: checkpoints.append(copy.deepcopy(value)),
            )
        )

    failure = checkpoints[-1]
    assert failure["success"] is False
    assert failure["completed_operation_count"] == 1
    assert failure["failed_operation_id"] == "explanation-document"
    assert failure["partial_mutation"] is True
    assert failure["mutation_attempted"] is True


def test_cli_check_is_mutation_free(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["miro", "native", "check", str(FIXTURE), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["ok"] is True
    assert result["operation_count"] == 5
    assert result["mutation_attempted"] is False
    assert "diagram_create" in result["required_tools"]


def _receipt_digest(value: dict) -> str:
    content = {key: item for key, item in value.items() if key != "execution_digest"}
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def test_resume_skips_verified_prefix_and_reconciles_uncertain_comment() -> None:
    bundle = load_native_bundle(FIXTURE)
    first_fake = FakeMiro()
    complete = asyncio.run(
        execute_native_bundle(
            call_tool=first_fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )
    resume = copy.deepcopy(complete)
    resume["success"] = False
    resume["execution_state"] = "in_progress"
    resume["error_code"] = "in_progress"
    resume["completed_operations"] = resume["completed_operations"][:4]
    resume["completed_operation_count"] = 4
    resume["calls"] = resume["calls"][:14]
    resume["call_count"] = 14
    resume["postflight"] = {"inventory": None, "context": None}
    resume["pending_operation_id"] = "review-marker"
    resume["pending_tool"] = "comment_create"
    resume["execution_digest"] = _receipt_digest(resume)

    resumed_fake = FakeMiro()
    resumed_fake.inventory_reads = 1
    resumed_fake.context_reads = 1
    resumed_fake.comment_created = True
    result = asyncio.run(
        execute_native_bundle(
            call_tool=resumed_fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
            resume_receipt=resume,
        )
    )

    tools = [tool for tool, _arguments in resumed_fake.calls]
    assert "diagram_create" not in tools
    assert "doc_create" not in tools
    assert "table_create" not in tools
    assert "code_widget_create" not in tools
    assert "comment_create" not in tools
    assert result["success"] is True
    assert result["resume_completed_operation_count"] == 4
    assert result["completed_operations"][-1]["readback"]["reconciled_existing"] is True


def test_resume_rejects_tampered_receipt_even_with_recomputed_digest() -> None:
    bundle = load_native_bundle(FIXTURE)
    fake = FakeMiro()
    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )
    receipt["success"] = False
    receipt["execution_state"] = "in_progress"
    receipt["completed_operations"][0]["operation_id"] = "forged-operation"
    receipt["execution_digest"] = _receipt_digest(receipt)

    with pytest.raises(NativeBundleError, match="verified bundle prefix"):
        asyncio.run(
            execute_native_bundle(
                call_tool=FakeMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=receipt,
            )
        )


def test_layout_lane_reads_contract_and_verifies_created_dsl() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "layout-stage-test",
            "operations": [
                {
                    "operation_id": "stage",
                    "kind": "layout",
                    "dsl": (
                        'root FRAME x=0 y=0 w=100 h=100 "Stage"\n'
                        'title TEXT parent=root x=50 y=20 w=80 "Title"'
                    ),
                }
            ],
        }
    )
    fake = FakeMiro()
    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    assert result["success"] is True
    assert required_tools(bundle) == (
        "board_list_items",
        "context_explore",
        "layout_create",
        "layout_get_dsl",
        "layout_read",
        "user_who_am_i",
    )
    readback = result["completed_operations"][0]["readback"]
    assert readback["created_count"] == 2
    assert readback["failed_item_count"] == 0
    assert readback["board_item_count"] == 2


def test_packaged_schema_matches_public_schema() -> None:
    public = (ROOT / "schemas/miro-native-bundle.v1.schema.json").read_bytes()
    packaged = files("schauwerk.schemas").joinpath("miro-native-bundle.v1.schema.json").read_bytes()

    assert packaged == public


def test_resume_rejects_uncertain_non_comment_mutation() -> None:
    bundle = load_native_bundle(FIXTURE)
    fake = FakeMiro()
    complete = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )
    receipt = copy.deepcopy(complete)
    receipt["success"] = False
    receipt["execution_state"] = "in_progress"
    receipt["completed_operations"] = []
    receipt["completed_operation_count"] = 0
    receipt["pending_operation_id"] = "architecture-diagram"
    receipt["pending_tool"] = "diagram_create"
    receipt["postflight"] = {"inventory": None, "context": None}
    receipt["execution_digest"] = _receipt_digest(receipt)

    with pytest.raises(NativeBundleError, match="manual reconciliation"):
        asyncio.run(
            execute_native_bundle(
                call_tool=FakeMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=receipt,
            )
        )


class PagedCommentMiro(FakeMiro):
    def __init__(self) -> None:
        super().__init__()
        self.marker = "Schauwerk native executor verification marker"

    async def __call__(self, tool: str, arguments: dict) -> dict:
        if tool != "comment_list_comments":
            return await super().__call__(tool, arguments)
        self.calls.append((tool, copy.deepcopy(arguments)))
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit", 50)
        comments = [
            {
                "id": f"comment-{index}",
                "messages": [{"id": f"message-{index}", "content": f"other-{index}"}],
            }
            for index in range(54)
        ]
        comments.append(
            {
                "id": "comment-marker",
                "messages": [{"id": "message-marker", "content": self.marker}],
            }
        )
        page = comments[offset : offset + limit]
        return {
            "data": page,
            "total": len(comments),
            "offset": offset,
            "limit": limit,
            "board_id": "board",
            "board_url": BOARD_URL,
        }


def pending_comment_receipt(bundle: dict, operation_id: str) -> dict:
    receipt = {
        "schema_version": "schauwerk-miro-native-execution-receipt.v1",
        "success": False,
        "execution_state": "in_progress",
        "bundle_digest": bundle["bundle_digest"],
        "board_alias": "native-test",
        "board_reference_digest": hashlib.sha256(BOARD_URL.encode("utf-8")).hexdigest()[:24],
        "completed_operations": [],
        "completed_operation_count": 0,
        "preflight": {
            "inventory": {"item_count": 1},
            "context": {"item_count": 1},
        },
        "calls": [],
        "pending_operation_id": operation_id,
        "pending_tool": "comment_create",
    }
    receipt["execution_digest"] = _receipt_digest(receipt)
    return receipt


def test_comment_reconciliation_paginates_before_deciding_to_create() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "paged-comment-test",
            "operations": [
                {
                    "operation_id": "marker",
                    "kind": "comment",
                    "content": "Schauwerk native executor verification marker",
                    "x": 0,
                    "y": 0,
                }
            ],
        }
    )
    fake = PagedCommentMiro()
    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
            resume_receipt=pending_comment_receipt(bundle, "marker"),
        )
    )

    tools = [tool for tool, _arguments in fake.calls]
    assert tools.count("comment_list_comments") == 4
    assert "comment_create" not in tools
    assert result["completed_operations"][0]["readback"]["reconciled_existing"] is True


def test_native_inputs_reject_symlink_chains(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    bundle_path = target / "bundle.json"
    bundle_path.write_bytes(FIXTURE.read_bytes())
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(NativeBundleError, match="must not contain symlinks"):
        load_native_bundle(linked / "bundle.json")


def test_native_output_cannot_overwrite_inputs_or_miro_state(tmp_path: Path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(FIXTURE.read_bytes())
    resume = tmp_path / "resume.json"
    resume.write_text("{}")

    with pytest.raises(MiroCredentialError, match="protected input"):
        prepare_native_destination(
            settings,
            input_path=bundle,
            output_path=bundle,
        )
    assert (
        prepare_native_destination(
            settings,
            input_path=bundle,
            output_path=resume,
        )
        == resume.absolute()
    )
    with pytest.raises(MiroCredentialError, match="protected input"):
        prepare_native_destination(
            settings,
            input_path=bundle,
            output_path=settings.credentials_path,
        )


def test_native_output_rejects_symlink_chain(tmp_path: Path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(FIXTURE.read_bytes())
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(MiroCredentialError, match="unsafe"):
        prepare_native_destination(
            settings,
            input_path=bundle,
            output_path=linked / "receipt.json",
        )


class PagedTableMiro(FakeMiro):
    async def __call__(self, tool: str, arguments: dict) -> dict:
        if tool != "table_list_rows":
            return await super().__call__(tool, arguments)
        self.calls.append((tool, copy.deepcopy(arguments)))
        cursor = arguments.get("next_cursor")
        if cursor is None:
            return {
                "miro_url": arguments["miro_url"],
                "rows": [
                    {
                        "rowId": "1",
                        "cells": [{"columnTitle": "Lane", "content": "One"}],
                    },
                    {
                        "rowId": "2",
                        "cells": [{"columnTitle": "Lane", "content": "Two"}],
                    },
                ],
                "total": 3,
                "cursor": "next-page",
            }
        assert cursor == "next-page"
        return {
            "miro_url": arguments["miro_url"],
            "rows": [
                {
                    "rowId": "3",
                    "cells": [{"columnTitle": "Lane", "content": "Three"}],
                }
            ],
            "total": 3,
            "cursor": None,
        }


def test_table_readback_paginates_and_matches_submitted_cells() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "paged-table-test",
            "operations": [
                {
                    "operation_id": "table",
                    "kind": "table",
                    "table_title": "Rows",
                    "columns": [
                        {
                            "column_type": "text",
                            "column_title": "Lane",
                            "isTitle": True,
                        }
                    ],
                    "rows": [
                        {"cells": [{"columnTitle": "Lane", "value": "Three"}]},
                        {"cells": [{"columnTitle": "Lane", "value": "One"}]},
                        {"cells": [{"columnTitle": "Lane", "value": "Two"}]},
                    ],
                }
            ],
        }
    )
    fake = PagedTableMiro()
    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    assert [tool for tool, _arguments in fake.calls].count("table_list_rows") == 2
    readback = result["completed_operations"][0]["readback"]
    assert readback["row_count"] == 3
    assert readback["submitted_rows_match"] is True


class MismatchedTableMiro(FakeMiro):
    async def __call__(self, tool: str, arguments: dict) -> dict:
        value = await super().__call__(tool, arguments)
        if tool == "table_list_rows":
            value["rows"][0]["cells"][0]["content"] = "wrong"
        return value


def test_table_readback_rejects_missing_submitted_content() -> None:
    bundle = load_native_bundle(FIXTURE)
    with pytest.raises(NativeExecutionError, match="does not contain a submitted row"):
        asyncio.run(
            execute_native_bundle(
                call_tool=MismatchedTableMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )


def typed_table_bundle() -> dict:
    return {
        "schema_version": "schauwerk-miro-native-bundle.v1",
        "bundle_id": "typed-table-values",
        "operations": [
            {
                "operation_id": "typed-table",
                "kind": "table",
                "table_title": "Typed values",
                "columns": [
                    {"column_type": "text", "column_title": "Title", "isTitle": True},
                    {
                        "column_type": "select",
                        "column_title": "Status",
                        "options": [
                            {"displayValue": "Open", "color": "#E7E7E7"},
                            {"displayValue": "Done", "color": "#C6DCFF"},
                        ],
                    },
                    {"column_type": "date", "column_title": "Due"},
                    {"column_type": "link", "column_title": "Source"},
                    {"column_type": "person", "column_title": "Owner"},
                ],
                "rows": [
                    {
                        "cells": [
                            {"columnTitle": "Title", "value": "Audit"},
                            {"columnTitle": "Status", "value": ["Open"]},
                            {"columnTitle": "Due", "value": "2026-07-14T18:00:00Z"},
                            {
                                "columnTitle": "Source",
                                "value": [{"url": "https://example.com/audit", "text": "Audit"}],
                            },
                            {"columnTitle": "Owner", "value": ["miro-user-1"]},
                        ]
                    }
                ],
            }
        ],
    }


def test_table_cell_values_are_bound_to_column_types() -> None:
    result = validate_native_bundle(typed_table_bundle())
    assert result["operations"][0]["rows"][0]["cells"][2]["value"].endswith("Z")


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Title", ["not-text"], "text table column"),
        ("Status", "Missing", "unknown values"),
        ("Status", ["Open", "Open"], "duplicate display values"),
        ("Due", "14/07/2026", "ISO 8601"),
        ("Source", [{"text": "missing URL"}], "objects with url"),
        ("Source", "javascript:alert(1)", "absolute HTTP"),
        ("Owner", [{"id": "not-a-string-value"}], "Miro user IDs"),
        ("Owner", ["miro-user-1", "miro-user-1"], "duplicate Miro user IDs"),
    ],
)
def test_table_cell_semantics_reject_invalid_values(
    column: str, value: object, message: str
) -> None:
    raw = typed_table_bundle()
    cell = next(
        item for item in raw["operations"][0]["rows"][0]["cells"] if item["columnTitle"] == column
    )
    cell["value"] = value

    with pytest.raises(NativeBundleError, match=message):
        validate_native_bundle(raw)


def test_table_rejects_duplicate_cells_and_select_option_labels() -> None:
    raw = typed_table_bundle()
    raw["operations"][0]["rows"][0]["cells"].append({"columnTitle": "Title", "value": "Duplicate"})
    with pytest.raises(NativeBundleError, match="duplicate column cells"):
        validate_native_bundle(raw)

    raw = typed_table_bundle()
    options = raw["operations"][0]["columns"][1]["options"]
    options[1]["displayValue"] = options[0]["displayValue"]
    with pytest.raises(NativeBundleError, match="option display values must be unique"):
        validate_native_bundle(raw)


def test_native_board_lock_serializes_same_board_and_allows_other_boards(
    tmp_path: Path,
) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    other_board = "https://miro.com/app/board/uXjVOtherBoard=/"

    with native_board_lock(settings, BOARD_URL) as lock_path:
        lock_mode = lock_path.stat().st_mode
        directory_mode = lock_path.parent.stat().st_mode
        assert stat.S_IMODE(lock_mode) == 0o600
        assert stat.S_IMODE(directory_mode) == 0o700
        with pytest.raises(MiroConnectionError, match="already active"):
            with native_board_lock(settings, BOARD_URL):
                pass
        with native_board_lock(settings, other_board):
            pass

    with native_board_lock(settings, BOARD_URL):
        pass


def test_native_board_lock_rejects_unsafe_existing_permissions(tmp_path: Path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    directory = settings.state_root / "native-execution-locks"
    directory.mkdir(parents=True, mode=0o755)
    directory.chmod(0o755)

    with pytest.raises(MiroCredentialError, match="not owner-only"):
        with native_board_lock(settings, BOARD_URL):
            pass


def test_native_receipt_lock_serializes_same_output_across_boards(
    tmp_path: Path,
) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    receipt = tmp_path / "receipt.json"
    other_receipt = tmp_path / "other-receipt.json"

    with native_receipt_lock(settings, receipt):
        with pytest.raises(MiroConnectionError, match="receipt"):
            with native_receipt_lock(settings, receipt):
                pass
        with native_receipt_lock(settings, other_receipt):
            pass


def test_resume_receipt_must_be_owner_only(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    receipt.chmod(0o644)

    with pytest.raises(NativeBundleError, match="owner-only"):
        load_native_resume_receipt(receipt)

    receipt.chmod(0o600)
    assert load_native_resume_receipt(receipt) == {}


class MismatchedCodeWidgetMiro(FakeMiro):
    async def __call__(self, tool: str, arguments: dict) -> dict:
        value = await super().__call__(tool, arguments)
        if tool == "code_widget_get":
            value["line_numbers_visible"] = False
        return value


def test_code_widget_readback_rejects_style_mismatch() -> None:
    bundle = load_native_bundle(FIXTURE)
    with pytest.raises(NativeExecutionError, match="line-number"):
        asyncio.run(
            execute_native_bundle(
                call_tool=MismatchedCodeWidgetMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )


def test_fresh_comment_does_not_adopt_equal_existing_content() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "fresh-comment-test",
            "operations": [
                {
                    "operation_id": "marker",
                    "kind": "comment",
                    "content": "Schauwerk native executor verification marker",
                    "x": 0,
                    "y": 0,
                }
            ],
        }
    )
    fake = PagedCommentMiro()
    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    tools = [tool for tool, _arguments in fake.calls]
    assert "comment_create" in tools
    assert result["completed_operations"][0]["readback"]["reconciled_existing"] is False


def test_pending_comment_without_exact_marker_fails_closed() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "missing-comment-marker",
            "operations": [
                {
                    "operation_id": "marker",
                    "kind": "comment",
                    "content": "missing marker",
                    "x": 0,
                    "y": 0,
                }
            ],
        }
    )
    fake = FakeMiro()
    with pytest.raises(NativeExecutionError, match="could not be reconciled"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=pending_comment_receipt(bundle, "marker"),
            )
        )
    assert "comment_create" not in [tool for tool, _arguments in fake.calls]


def connector_layout_bundle() -> dict:
    return validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "connector-observability",
            "operations": [
                {
                    "operation_id": "layout",
                    "kind": "layout",
                    "dsl": (
                        "a SHAPE x=0 y=0 w=100 h=100 A\n"
                        "b SHAPE x=200 y=0 w=100 h=100 B\n"
                        "c SHAPE x=400 y=0 w=100 h=100 C\n"
                        "ab CONNECTOR from=a to=b\n"
                        "bc CONNECTOR from=b to=c"
                    ),
                }
            ],
        }
    )


class ConnectorLayoutMiro(FakeMiro):
    def __init__(
        self,
        *,
        layout_connector_count: object = 2,
        board_connector_lines: int = 2,
        include_connector_count: bool = True,
        initial_connector_count: int = 0,
    ) -> None:
        super().__init__()
        self.layout_connector_count = layout_connector_count
        self.board_connector_lines = board_connector_lines
        self.include_connector_count = include_connector_count
        self.initial_connector_count = initial_connector_count
        self.layout_creates = 0

    @staticmethod
    def _dsl(connector_lines: int) -> str:
        node_count = max(1, connector_lines + 1)
        lines = [
            f"n{index} SHAPE x={index * 200} y=0 w=100 h=100 N{index}"
            for index in range(node_count)
        ]
        lines.extend(
            f"e{index} CONNECTOR from=n{index} to=n{index + 1}" for index in range(connector_lines)
        )
        return "\n".join(lines)

    async def __call__(self, tool: str, arguments: dict) -> dict:
        value = await super().__call__(tool, arguments)
        if tool == "board_list_items" and self.inventory_reads > 1:
            value["data"] = [
                {"id": "before", "type": "frame"},
                {"id": "a", "type": "shape"},
                {"id": "b", "type": "shape"},
                {"id": "c", "type": "shape"},
            ]
            value["total"] = len(value["data"])
        elif tool == "layout_create":
            self.layout_creates += 1
            value.update(
                {
                    "created_count": 5,
                    "result_dsl": self._dsl(self.board_connector_lines),
                }
            )
        elif tool == "layout_read":
            before_create = self.layout_creates == 0
            connector_lines = (
                self.initial_connector_count if before_create else self.board_connector_lines
            )
            value.update(
                {
                    "dsl": self._dsl(connector_lines),
                    "item_count": max(1, connector_lines * 2 + 1),
                }
            )
            if self.include_connector_count:
                value["connector_count"] = (
                    self.initial_connector_count if before_create else self.layout_connector_count
                )
            else:
                value.pop("connector_count", None)
        return value


def test_layout_inventory_omission_of_verified_connectors_completes_truthfully() -> None:
    result = asyncio.run(
        execute_native_bundle(
            call_tool=ConnectorLayoutMiro(),
            tool_catalogue=live_tools(connector_layout_bundle()),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=connector_layout_bundle(),
        )
    )

    assert result["success"] is True
    assert result["partial_mutation"] is False
    assert result["provider_created_item_count"] == 5
    assert result["board_inventory_visible_created_item_count"] == 3
    assert result["expected_net_item_count_delta"] == 5
    assert result["expected_board_inventory_item_count_delta"] == 3
    assert result["observed_board_inventory_item_count_delta"] == 3
    assert result["connector_evidence"] == {
        "layout_operation_count": 1,
        "layout_read_verified_operation_count": 1,
        "layout_operations_with_connectors": 1,
        "declared_connector_count": 2,
        "provider_created_connector_count": 2,
        "board_inventory_connector_visibility": "not_assumed",
    }
    readback = result["completed_operations"][0]["readback"]
    assert readback["board_inventory_visible_created_count"] == 3
    assert readback["connector_evidence"] == {
        "schema_version": 2,
        "declared_count": 2,
        "result_dsl_count": 2,
        "layout_read_count": 2,
        "board_dsl_count": 2,
        "layout_read_before_count": 0,
        "layout_read_after_count": 2,
        "board_dsl_before_count": 0,
        "board_dsl_after_count": 2,
        "created_count": 2,
        "verified": True,
    }


def test_layout_connector_evidence_uses_delta_with_preexisting_connectors() -> None:
    result = asyncio.run(
        execute_native_bundle(
            call_tool=ConnectorLayoutMiro(
                initial_connector_count=2,
                layout_connector_count=4,
                board_connector_lines=4,
            ),
            tool_catalogue=live_tools(connector_layout_bundle()),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=connector_layout_bundle(),
        )
    )

    evidence = result["completed_operations"][0]["readback"]["connector_evidence"]
    assert evidence["schema_version"] == 2
    assert evidence["layout_read_count"] == 4
    assert evidence["board_dsl_count"] == 4
    assert evidence["layout_read_before_count"] == 2
    assert evidence["layout_read_after_count"] == 4
    assert evidence["created_count"] == 2
    assert result["provider_created_item_count"] == 5
    assert result["board_inventory_visible_created_item_count"] == 3


def multi_connector_layout_bundle() -> dict:
    return validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "multi-connector-observability",
            "operations": [
                {
                    "operation_id": "layout-a",
                    "kind": "layout",
                    "dsl": (
                        "a1 SHAPE x=0 y=0 w=100 h=100 A1\n"
                        "b1 SHAPE x=200 y=0 w=100 h=100 B1\n"
                        "e1 CONNECTOR from=a1 to=b1"
                    ),
                },
                {
                    "operation_id": "layout-b",
                    "kind": "layout",
                    "dsl": (
                        "a2 SHAPE x=0 y=300 w=100 h=100 A2\n"
                        "b2 SHAPE x=200 y=300 w=100 h=100 B2\n"
                        "e2 CONNECTOR from=a2 to=b2"
                    ),
                },
            ],
        }
    )


class MultiConnectorLayoutMiro(FakeMiro):
    def __init__(self, *, omit_second_connector: bool = False) -> None:
        super().__init__()
        self.layout_creates = 0
        self.omit_second_connector = omit_second_connector
        self.board_dsl_lines = ["before FRAME x=0 y=0 w=100 h=100 Before"]

    async def __call__(self, tool: str, arguments: dict) -> dict:
        value = await super().__call__(tool, arguments)
        if tool == "board_list_items" and self.inventory_reads > 1:
            value["data"] = [
                {"id": "before", "type": "frame"},
                {"id": "a1", "type": "shape"},
                {"id": "b1", "type": "shape"},
                {"id": "a2", "type": "shape"},
                {"id": "b2", "type": "shape"},
            ]
            value["total"] = len(value["data"])
        elif tool == "layout_create":
            self.layout_creates += 1
            operation_dsl = arguments["dsl"]
            lines = operation_dsl.splitlines()
            if self.omit_second_connector and self.layout_creates == 2:
                self.board_dsl_lines.extend(
                    line for line in lines if " CONNECTOR " not in f" {line} "
                )
                created_count = 2
            else:
                self.board_dsl_lines.extend(lines)
                created_count = 3
            value.update(
                {
                    "created_count": created_count,
                    "result_dsl": "\n".join(self.board_dsl_lines),
                }
            )
        elif tool == "layout_read":
            connector_count = sum(" CONNECTOR " in f" {line} " for line in self.board_dsl_lines)
            value.update(
                {
                    "dsl": "\n".join(self.board_dsl_lines),
                    "item_count": len(self.board_dsl_lines),
                    "connector_count": connector_count,
                }
            )
        return value


def test_multiple_layout_operations_use_operation_local_connector_deltas() -> None:
    bundle = multi_connector_layout_bundle()
    result = asyncio.run(
        execute_native_bundle(
            call_tool=MultiConnectorLayoutMiro(),
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )

    assert result["provider_created_item_count"] == 6
    assert result["board_inventory_visible_created_item_count"] == 4
    assert result["observed_board_inventory_item_count_delta"] == 4
    assert result["connector_evidence"] == {
        "layout_operation_count": 2,
        "layout_read_verified_operation_count": 2,
        "layout_operations_with_connectors": 2,
        "declared_connector_count": 2,
        "provider_created_connector_count": 2,
        "board_inventory_connector_visibility": "not_assumed",
    }
    evidence = [
        operation["readback"]["connector_evidence"] for operation in result["completed_operations"]
    ]
    assert [
        (item["layout_read_before_count"], item["layout_read_after_count"]) for item in evidence
    ] == [
        (0, 1),
        (1, 2),
    ]
    assert [item["schema_version"] for item in evidence] == [2, 2]
    assert [item["layout_read_count"] for item in evidence] == [1, 2]
    assert [item["created_count"] for item in evidence] == [1, 1]


def test_idempotently_omitted_connector_is_not_double_counted() -> None:
    bundle = multi_connector_layout_bundle()
    with pytest.raises(NativeExecutionError, match="fewer newly created connectors"):
        asyncio.run(
            execute_native_bundle(
                call_tool=MultiConnectorLayoutMiro(omit_second_connector=True),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        (ConnectorLayoutMiro(include_connector_count=False), "invalid connector_count"),
        (ConnectorLayoutMiro(layout_connector_count="2"), "invalid connector_count"),
        (
            ConnectorLayoutMiro(layout_connector_count=1, board_connector_lines=1),
            "result DSL contains fewer connectors than declared",
        ),
    ],
)
def test_layout_connector_evidence_failures_remain_fail_closed(
    fake: ConnectorLayoutMiro, message: str
) -> None:
    bundle = connector_layout_bundle()
    with pytest.raises(NativeExecutionError, match=message):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )


def test_missing_layout_connector_count_fails_before_mutation() -> None:
    fake = ConnectorLayoutMiro(include_connector_count=False)
    bundle = connector_layout_bundle()

    with pytest.raises(NativeExecutionError, match="invalid connector_count"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )

    assert "layout_create" not in [tool for tool, _arguments in fake.calls]


class MissingCreatedItemMiro(FakeMiro):
    async def __call__(self, tool: str, arguments: dict) -> dict:
        value = await super().__call__(tool, arguments)
        if tool == "board_list_items" and self.inventory_reads > 1:
            value["data"] = value["data"][:-1]
            value["total"] = len(value["data"])
        return value


def test_postflight_rejects_missing_created_board_item() -> None:
    bundle = load_native_bundle(FIXTURE)
    with pytest.raises(NativeExecutionError, match="did not expose all created"):
        asyncio.run(
            execute_native_bundle(
                call_tool=MissingCreatedItemMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )


def test_resume_rejects_missing_verified_prefix_items() -> None:
    bundle = load_native_bundle(FIXTURE)
    complete = asyncio.run(
        execute_native_bundle(
            call_tool=FakeMiro(),
            tool_catalogue=live_tools(bundle),
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )
    resume = copy.deepcopy(complete)
    resume["success"] = False
    resume["execution_state"] = "in_progress"
    resume["completed_operations"] = resume["completed_operations"][:4]
    resume["completed_operation_count"] = 4
    resume["pending_operation_id"] = "review-marker"
    resume["pending_tool"] = "comment_create"
    resume["postflight"] = {"inventory": None, "context": None}
    resume["execution_digest"] = _receipt_digest(resume)

    with pytest.raises(NativeExecutionError, match="does not expose the verified resume prefix"):
        asyncio.run(
            execute_native_bundle(
                call_tool=FakeMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=resume,
            )
        )


def test_resume_rejects_missing_baseline_inventory() -> None:
    bundle = load_native_bundle(FIXTURE)
    receipt = pending_comment_receipt(bundle, "review-marker")
    receipt.pop("preflight")
    receipt["execution_digest"] = _receipt_digest(receipt)

    with pytest.raises(NativeBundleError, match="baseline inventory"):
        asyncio.run(
            execute_native_bundle(
                call_tool=FakeMiro(),
                tool_catalogue=live_tools(bundle),
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
                resume_receipt=receipt,
            )
        )


def test_live_executor_uses_creation_fallback_before_first_mutation() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "document-fallback",
            "operations": [
                {
                    "operation_id": "doc",
                    "kind": "document",
                    "content": "Ein editierbarer Fallback",
                }
            ],
        }
    )
    fake = FakeMiro()
    tools = catalogue(
        "user_who_am_i",
        "board_list_items",
        "context_explore",
        "layout_get_dsl",
        "layout_create",
        "layout_read",
    )
    result = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=tools,
            board_alias="native-test",
            board_url=BOARD_URL,
            bundle=bundle,
        )
    )
    assert result["success"] is True
    assert result["provider_fallback_count"] == 1
    assert result["completed_operations"][0]["kind"] == "document"
    readback = result["completed_operations"][0]["readback"]
    assert readback["provider_mode"] == "fallback"
    assert readback["fallback"] == "layout_document"
    called = [name for name, _arguments in fake.calls]
    assert "layout_create" in called
    assert "doc_create" not in called


def test_missing_maintenance_tool_does_not_fallback() -> None:
    bundle = validate_native_bundle(
        {
            "schema_version": "schauwerk-miro-native-bundle.v1",
            "bundle_id": "update-no-fallback",
            "operations": [
                {
                    "operation_id": "update",
                    "kind": "document_update",
                    "target_miro_url": f"{BOARD_URL}?moveToWidget=doc",
                    "expected_content_sha256": "a" * 64,
                    "old_content": "old",
                    "new_content": "new",
                }
            ],
        }
    )
    tools = catalogue(
        "user_who_am_i",
        "board_list_items",
        "context_explore",
        "layout_get_dsl",
        "layout_create",
        "layout_read",
    )
    with pytest.raises(NativeBundleError, match="lacks required tools"):
        asyncio.run(
            execute_native_bundle(
                call_tool=FakeMiro(),
                tool_catalogue=tools,
                board_alias="native-test",
                board_url=BOARD_URL,
                bundle=bundle,
            )
        )
