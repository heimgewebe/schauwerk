# ruff: noqa: E501
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from schauwerk.visual.standalone_editor import _EditorRequestHandler, build_standalone_editor


@pytest.mark.parametrize(
    ("width", "height", "bottom_y"),
    [
        (1366, 900, 1280),
        (1024, 768, 1280),
        (844, 390, 1280),
        (768, 1024, 1280),
        (431, 844, 1280),
        (390, 844, 1280),
        (390, 844, 4000),
        (390, 844, 5000),
    ],
)
def test_single_workspace_browser_uses_full_canvas_and_keeps_native_actions_reachable(
    tmp_path: Path,
    width: int,
    height: int,
    bottom_y: int,
) -> None:
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("single-workspace browser geometry is covered on the Python 3.12 CI lane")

    chrome = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("Chrome/Chromium is required in CI for single-workspace geometry")
        pytest.skip("Chrome/Chromium is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)

    probe_js = r"""
const waitUntil = async (predicate, label, attempts = 600) => {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(label);
};
const almost = (actual, expected, tolerance = 2) =>
  Math.abs(Number(actual) - Number(expected)) <= tolerance;

try {
  const source = {
    nodes: [
      {id: "a", type: "text", x: 0, y: 0, width: 220, height: 120, text: "Alpha"},
      {id: "b", type: "text", x: 0, y: 640, width: 220, height: 120, text: "Beta"},
      {id: "c", type: "text", x: 0, y: __BOTTOM_Y__, width: 220, height: 120, text: "Gamma"},
    ],
    edges: [
      {id: "ab", fromNode: "a", toNode: "b", toEnd: "arrow", label: "verbindet"},
      {id: "bc", fromNode: "b", toNode: "c", toEnd: "arrow", label: "führt zu"},
    ],
  };
  document.querySelector("#sourceInput").value = JSON.stringify(source);
  document.querySelector("#openPasteButton").click();

  await waitUntil(() => {
    const frame = document.querySelector("#editorFrame");
    return (
      !document.querySelector("#workspace").hidden &&
      document.querySelector("#startView").hidden &&
      frame?.src?.includes("/native/") &&
      frame.contentDocument?.readyState === "complete" &&
      frame.contentDocument?.querySelector("#nativeViewport") &&
      frame.contentDocument?.querySelector('[data-source-id="a"]')
    );
  }, "native single workspace did not become ready");

  const workspace = document.querySelector("#workspace");
  const stage = document.querySelector(".editor-stage");
  const frame = document.querySelector("#editorFrame");
  const workspaceRect = workspace.getBoundingClientRect();
  const stageRect = stage.getBoundingClientRect();
  const frameRect = frame.getBoundingClientRect();

  if (document.querySelector("#fullscreenButton")) {
    throw new Error("fullscreen toggle survived in the product workspace");
  }
  if (!almost(workspaceRect.width, innerWidth) || !almost(workspaceRect.height, innerHeight)) {
    throw new Error(`workspace does not fill viewport: ${workspaceRect.width}x${workspaceRect.height} vs ${innerWidth}x${innerHeight}`);
  }
  if (!almost(stageRect.width, innerWidth) || !almost(stageRect.height, innerHeight)) {
    throw new Error(`editor stage does not fill viewport: ${stageRect.width}x${stageRect.height}`);
  }
  if (!almost(frameRect.width, stageRect.width) || !almost(frameRect.height, stageRect.height)) {
    throw new Error("editor iframe does not fill the single workspace stage");
  }

  const exportMenu = document.querySelector(".workspace-export-menu");
  exportMenu.open = true;
  const projectButton = document.querySelector("#projectButton");
  const pngButton = document.querySelector('[data-export="png"]');
  const svgButton = document.querySelector('[data-export="svg"]');
  if (projectButton.textContent.trim() !== "Canvas") {
    throw new Error(`native Canvas export mislabeled as ${projectButton.textContent}`);
  }
  if (!pngButton.hidden || svgButton.hidden) {
    throw new Error("native export capability visibility drifted");
  }
  const exportSummaryRect = exportMenu.querySelector("summary").getBoundingClientRect();
  if (exportSummaryRect.height < 40) {
    throw new Error("export touch target is too small");
  }

  const viewer = frame.contentDocument;
  const nativeStage = viewer.querySelector(".viewer-stage");
  const nativeRect = nativeStage.getBoundingClientRect();
  if (
    !almost(nativeRect.width, frame.contentWindow.innerWidth) ||
    !almost(nativeRect.height, frame.contentWindow.innerHeight)
  ) {
    throw new Error("native canvas stage is still reduced by permanent header/footer chrome");
  }

  exportMenu.open = false;
  // Emulate a runner/font-dependent status reflow during the first fit.
  const statusGrowthProbe = source.nodes.some((node) => node.y >= 4000);
  const growingStatus = viewer.querySelector("#status");
  if (statusGrowthProbe) {
    growingStatus.textContent = "OK";
    growingStatus.style.maxWidth = "110px";
    growingStatus.style.fontSize = "17px";
    growingStatus.style.lineHeight = "42px";
  }
  if (source.nodes.some((node) => node.y >= 5000)) {
    document.body.style.setProperty("--workspace-bar-bottom", "44px");
    const hostBarBottom = document.querySelector(".workspace-bar").getBoundingClientRect().bottom;
    if (Math.abs(innerHeight - hostBarBottom - 44) > 1) {
      throw new Error("safe-area test did not move host bar 44 CSS px");
    }
  }
  viewer.querySelector("#fitView").click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  const fittedItems = Array.from(
    viewer.querySelectorAll('[data-source-kind="node"], [data-source-kind="edge"]')
  ).map((element) => element.getBoundingClientRect());
  if (!fittedItems.length) {
    throw new Error("native fit produced no measurable graph content");
  }
  const fittedTop = frameRect.top + Math.min(...fittedItems.map((rect) => rect.top));
  const fittedBottom = frameRect.top + Math.max(...fittedItems.map((rect) => rect.bottom));
  const fitBarRect = document.querySelector(".workspace-bar").getBoundingClientRect();
  const fitStatusRect = document.querySelector("#status").getBoundingClientRect();
  const hostChromeTop = Math.min(fitBarRect.top, fitStatusRect.top);
  const hostChromeClearance = hostChromeTop - fittedBottom;
  if (hostChromeClearance < 8) {
    throw new Error(
      `fitted native content overlaps host chrome: clearance=${hostChromeClearance.toFixed(2)}px`
    );
  }
  const nativeBarBottom = frameRect.top + viewer.querySelector(".viewer-bar").getBoundingClientRect().bottom;
  const nativeBarClearance = fittedTop - nativeBarBottom;
  if (nativeBarClearance < 6) {
    throw new Error(
      `fitted native content overlaps native toolbar: clearance=${nativeBarClearance.toFixed(2)}px`
    );
  }
  if (statusGrowthProbe) {
    if (growingStatus.textContent.trim() !== "Ansicht angepasst") {
      throw new Error("status growth probe did not trigger final fit instruction");
    }
    growingStatus.removeAttribute("style");
    viewer.querySelector("#fitView").click();
  }
  if (source.nodes.some((node) => node.y >= 4000)) {
    const canvas = viewer.querySelector("#nativeCanvas");
    const scaleNow = () => Number(
      canvas.style.transform.match(/scale\(([^)]+)\)/)?.[1],
    );
    const fitScale = scaleNow();
    if (!(fitScale > 0 && fitScale < 0.25)) {
      throw new Error("tall diagram was not fitted below interactive zoom minimum");
    }
    viewer.querySelector("#zoomOut").click();
    if (scaleNow() > fitScale + 1e-9) {
      throw new Error("zoom-out increased scale after sub-minimum auto-fit");
    }
    viewer.querySelector("#fitView").click();
    viewer.querySelector("#zoomIn").click();
    if (Math.abs(scaleNow() - fitScale * 1.2) > 1e-6) {
      throw new Error(
        "zoom-in snapped to interactive minimum instead of advancing smoothly"
        + " fit=" + fitScale.toFixed(9)
        + " actual=" + scaleNow().toFixed(9)
        + " expected=" + (fitScale * 1.2).toFixed(9)
      );
    }
    viewer.querySelector("#zoomOut").click();
    if (Math.abs(scaleNow() - fitScale) > 1e-6) {
      throw new Error("zoom-in then zoom-out cannot restore sub-minimum fit scale");
    }
    viewer.querySelector("#fitView").click();
    const pinchViewport = viewer.querySelector("#nativeViewport");
    // Chrome synthetic pointer IDs need the existing viewer-test capture shim.
    frame.contentWindow.Element.prototype.setPointerCapture = function () {};
    frame.contentWindow.Element.prototype.releasePointerCapture = function () {};
    const fireTouch = (type, id, x, y) => pinchViewport.dispatchEvent(
      new frame.contentWindow.PointerEvent(type, {
        bubbles: true,
        cancelable: true,
        pointerId: id,
        pointerType: "touch",
        clientX: x,
        clientY: y,
        button: 0,
        buttons: type === "pointerup" ? 0 : 1,
        isPrimary: id === 31,
      }),
    );
    fireTouch("pointerdown", 31, 130, 420);
    fireTouch("pointerdown", 32, 270, 420);
    fireTouch("pointermove", 32, 250, 420);
    if (scaleNow() > fitScale + 1e-9) {
      throw new Error("inward pinch increased sub-minimum fitted zoom");
    }
    fireTouch("pointermove", 32, 310, 420);
    if (Math.abs(scaleNow() - fitScale * (180 / 140)) > 1e-6) {
      throw new Error(
        "outward pinch jumped to the manual zoom floor instead of scaling smoothly"
        + " fit=" + fitScale.toFixed(9)
        + " actual=" + scaleNow().toFixed(9)
        + " expected=" + (fitScale * (180 / 140)).toFixed(9)
      );
    }
    fireTouch("pointerup", 32, 310, 420);
    fireTouch("pointerup", 31, 130, 420);
    // Starting a second gesture must not ratchet the zoom floor upward.
    fireTouch("pointerdown", 31, 130, 420);
    fireTouch("pointerdown", 32, 310, 420);
    fireTouch("pointermove", 32, 270, 420);
    if (Math.abs(scaleNow() - fitScale) > 1e-6) {
      throw new Error("separate inward pinch cannot undo earlier outward pinch");
    }
    fireTouch("pointerup", 32, 270, 420);
    fireTouch("pointerup", 31, 130, 420);
    viewer.querySelector("#fitView").click();
    document.body.style.removeProperty("--workspace-bar-bottom");
  }
  viewer.querySelector("#resetLayout").click();
  const editMenu = viewer.querySelector(".edit-controls");
  if (editMenu.hidden) {
    throw new Error("native editing trigger is not reachable");
  }
  editMenu.open = true;
  const editSummaryRect = editMenu.querySelector("summary").getBoundingClientRect();
  if (editSummaryRect.height < 40) {
    throw new Error("native edit touch target is too small");
  }
  const addNode = viewer.querySelector("#addNode");
  if (addNode.hidden || addNode.disabled) {
    throw new Error("add-element action is not reachable");
  }

  const nodeA = viewer.querySelector('[data-source-id="a"]');
  nodeA.dispatchEvent(new MouseEvent("dblclick", {
    bubbles: true,
    cancelable: true,
    view: frame.contentWindow,
  }));
  await waitUntil(
    () => nodeA.classList.contains("is-selected"),
    "native node selection did not activate contextual edit actions",
  );
  const textDialog = viewer.querySelector("#textDialog");
  if (textDialog?.open) textDialog.close();
  const addEdgeButton = viewer.querySelector("#addEdge");
  if (addEdgeButton.hidden || viewer.querySelector("#editText").hidden) {
    throw new Error("selection-dependent native edit actions stayed hidden");
  }

  addEdgeButton.click();
  if (editMenu.open) {
    throw new Error("native edit popover still overlays canvas during target selection");
  }
  await waitUntil(
    () => viewer.querySelector("#status").textContent.trim() === "Ziel für die neue Verbindung auswählen",
    "native process status did not report the pending edge action",
  );
  const nativeStatusRect = viewer.querySelector("#status").getBoundingClientRect();
  if (nativeStatusRect.width < 1 || nativeStatusRect.height < 1) {
    throw new Error("native process status is not visible in the hosted workspace");
  }
  if (innerWidth <= 980) {
    const statusStyle = frame.contentWindow.getComputedStyle(viewer.querySelector("#status"));
    const nativeStatus = viewer.querySelector("#status");
    if (
      statusStyle.whiteSpace !== "normal" ||
      statusStyle.textOverflow === "ellipsis" ||
      nativeStatus.scrollWidth > nativeStatus.clientWidth + 1 ||
      nativeStatus.scrollHeight > nativeStatus.clientHeight + 1
    ) {
      throw new Error("native process instruction is clipped or ellipsized on mobile");
    }
  }
  frame.contentWindow.dispatchEvent(new frame.contentWindow.KeyboardEvent("keydown", {
    key: "Escape",
    bubbles: true,
  }));
  await waitUntil(
    () => viewer.querySelector("#status").textContent.trim() === "Verbindungsaktion abgebrochen",
    "native edge action did not cancel cleanly",
  );

  exportMenu.open = true;
  if (!exportMenu.open) {
    throw new Error("export popover could not be opened before export");
  }
  svgButton.click();
  await waitUntil(
    () => !document.querySelector("#downloadLink").hidden,
    "native SVG export did not prepare a download in the same workspace",
  );
  if (exportMenu.open) {
    throw new Error("export popover stayed open after choosing an export action");
  }
  const barRect = document.querySelector(".workspace-bar").getBoundingClientRect();
  const downloadRect = document.querySelector("#downloadLink").getBoundingClientRect();
  if (barRect.height > 54 || downloadRect.height < 40) {
    throw new Error("prepared download expanded the compact workspace chrome");
  }
  const toolsMenu = document.querySelector(".workspace-tools-menu");
  if (!toolsMenu.hidden && getComputedStyle(toolsMenu).display !== "none") {
    toolsMenu.open = true;
    const toolsPopoverRect = toolsMenu.querySelector(".workspace-popover").getBoundingClientRect();
    if (toolsPopoverRect.left < -0.5 || toolsPopoverRect.right > innerWidth + 0.5) {
      throw new Error(
        "workspace tools popover leaves viewport: left=" +
        toolsPopoverRect.left.toFixed(2) +
        " right=" +
        toolsPopoverRect.right.toFixed(2) +
        " viewport=" +
        innerWidth
      );
    }
    const toolsPopoverGap = barRect.top - toolsPopoverRect.bottom;
    if (toolsPopoverGap < 6 || (innerWidth <= 760 && toolsPopoverGap > 14)) {
      throw new Error(
        "workspace tools popover is detached from workspace bar: gap=" +
        toolsPopoverGap.toFixed(2)
      );
    }
    toolsMenu.open = false;
  }
  const stageAfterExport = stage.getBoundingClientRect();
  if (!almost(stageAfterExport.width, innerWidth) || !almost(stageAfterExport.height, innerHeight)) {
    throw new Error("prepared export reduced canvas geometry");
  }

  document.querySelector("#workspaceCloseButton").click();
  await waitUntil(
    () => document.querySelector("#workspace").hidden && !document.querySelector("#startView").hidden,
    "back action did not return to start view",
  );

  if (innerWidth <= 420) {
    const drawioSource = '<mxGraphModel><root><mxCell id="0"/>'
      + '<mxCell id="1" parent="0"/>'
      + '<mxCell id="a" value="Ali" vertex="1" parent="1">'
      + '<mxGeometry x="20" y="20" width="140" height="60" as="geometry"/>'
      + '</mxCell></root></mxGraphModel>';
    document.querySelector("#sourceInput").value = drawioSource;
    document.querySelector("#openPasteButton").click();
    await waitUntil(
      () => !document.querySelector("#workspace").hidden
        && document.querySelector("#projectButton").textContent.trim() === "Original"
        && document.querySelector("#editorFrame").src.includes("/native/"),
      "draw.io original import did not enter native workspace",
    );
    const originalMenu = document.querySelector(".workspace-export-menu");
    originalMenu.open = true;
    document.querySelector("#projectButton").click();
    await waitUntil(
      () => document.querySelector("#downloadLink").textContent.trim()
        === "Originalprojekt speichern"
        && !document.querySelector("#downloadLink").hidden,
      "draw.io original download did not become available",
    );
    const legacyToolsMenu = document.querySelector(".workspace-tools-menu");
    if (legacyToolsMenu.hidden || getComputedStyle(legacyToolsMenu).display === "none") {
      throw new Error("draw.io compatibility tools menu not visible");
    }
    legacyToolsMenu.open = true;
    const bar = document.querySelector(".workspace-bar").getBoundingClientRect();
    const popover = legacyToolsMenu.querySelector(".workspace-popover").getBoundingClientRect();
    const compatibility = document.querySelector("#legacyEditButton").getBoundingClientRect();
    if (
      popover.left < -0.5 || popover.right > innerWidth + 0.5 ||
      compatibility.left < -0.5 || compatibility.right > innerWidth + 0.5 ||
      bar.top - popover.bottom < 6
    ) {
      throw new Error(
        "draw.io tools popover clipped after original export: left="
        + popover.left.toFixed(2) + " gap=" + (bar.top - popover.bottom).toFixed(2)
      );
    }
    legacyToolsMenu.open = false;
  }

  document.querySelector("#blankButton").click();
  // The external legacy iframe navigation runs in requestAnimationFrame; Chrome
  // virtual time can delay it. Host/footer geometry does not depend on that navigation.
  await waitUntil(
    () => !document.querySelector("#workspace").hidden
      && document.body.classList.contains("engine-legacy")
      && document.querySelector("#editorFrame") instanceof HTMLIFrameElement,
    "legacy compatibility workspace did not open",
  );
  const legacyStage = document.querySelector(".editor-stage").getBoundingClientRect();
  const legacyFrame = document.querySelector("#editorFrame").getBoundingClientRect();
  const legacyBar = document.querySelector(".workspace-bar").getBoundingClientRect();
  if (
    !almost(legacyStage.width, innerWidth) || !almost(legacyStage.height, innerHeight)
    || !almost(legacyFrame.width, innerWidth) || !almost(legacyFrame.height, innerHeight)
  ) {
    throw new Error("legacy canvas lost full viewport geometry");
  }
  if (innerHeight - legacyBar.bottom < 40) {
    throw new Error("legacy host action bar overlaps the draw.io footer strip");
  }
  if (innerWidth <= 760) {
    const legacyExportMenu = document.querySelector(".workspace-export-menu");
    legacyExportMenu.open = true;
    const legacyPopover = legacyExportMenu.querySelector(".workspace-popover").getBoundingClientRect();
    const legacyPopoverGap = legacyBar.top - legacyPopover.bottom;
    if (
      legacyPopoverGap < 6 || legacyPopoverGap > 14 ||
      legacyPopover.left < -0.5 || legacyPopover.right > innerWidth + 0.5
    ) {
      throw new Error(
        "legacy export popover is detached or outside viewport: gap="
        + legacyPopoverGap.toFixed(2)
      );
    }
    const hostStatus = document.querySelector("body.workspace-active .status");
    const statusRect = hostStatus.getBoundingClientRect();
    const statusVisible = getComputedStyle(hostStatus).visibility === "visible";
    const intersectionWidth = Math.min(statusRect.right, legacyPopover.right)
      - Math.max(statusRect.left, legacyPopover.left);
    const intersectionHeight = Math.min(statusRect.bottom, legacyPopover.bottom)
      - Math.max(statusRect.top, legacyPopover.top);
    if (statusVisible && intersectionWidth > 0.5 && intersectionHeight > 0.5) {
      throw new Error("mobile export menu overlaps visible host status pill");
    }
    legacyExportMenu.open = false;
    if (getComputedStyle(hostStatus).visibility !== "visible") {
      throw new Error("host status did not reappear after closing export menu");
    }
  }
  if (
    document.querySelector("#projectButton").textContent.trim() !== "Projekt"
    || document.querySelector('[data-export="png"]').hidden
  ) {
    throw new Error("legacy export capabilities changed");
  }

  document.documentElement.dataset.singleWorkspaceBrowserRegression = "pass";
  document.documentElement.dataset.singleWorkspaceViewport = `${innerWidth}x${innerHeight}`;
  document.documentElement.dataset.singleWorkspaceFitClearance = hostChromeClearance.toFixed(2);
  document.documentElement.dataset.singleWorkspaceNativeBarClearance = nativeBarClearance.toFixed(2);
} catch (error) {
  document.documentElement.dataset.singleWorkspaceBrowserRegression = "fail";
  document.documentElement.dataset.singleWorkspaceBrowserRegressionError = String(
    error?.message || error
  );
}
"""
    assert probe_js.count("__BOTTOM_Y__") == 1
    probe_js = probe_js.replace("__BOTTOM_Y__", str(bottom_y))
    (output / "single-workspace-browser.js").write_text(probe_js, encoding="utf-8")
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    index_path.write_text(
        index.replace(
            "</body>",
            '<script type="module" src="single-workspace-browser.js"></script></body>',
        ),
        encoding="utf-8",
    )

    handler = partial(_EditorRequestHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    chrome_env = dict(os.environ)
    local_profile_args: list[str] = []
    if not os.environ.get("CI"):
        chrome_env.update(
            {
                "HOME": str(tmp_path / "home"),
                "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
                "XDG_CACHE_HOME": str(tmp_path / "xdg-cache"),
            }
        )
        local_profile_args = [f"--user-data-dir={tmp_path / 'chrome-profile'}"]

    try:
        completed = subprocess.run(
            [
                chrome,
                "--headless=new",
                *local_profile_args,
                "--no-first-run",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--run-all-compositor-stages-before-draw",
                f"--window-size={width},{height}",
                "--virtual-time-budget=18000",
                "--dump-dom",
                f"http://127.0.0.1:{port}/",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=chrome_env,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert 'data-single-workspace-browser-regression="pass"' in completed.stdout, completed.stdout
    assert 'data-single-workspace-browser-regression="fail"' not in completed.stdout, completed.stdout
