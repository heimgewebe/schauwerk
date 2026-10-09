# ruff: noqa: E501
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

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
      () => document.querySelector("#downloadLink .download-caption")?.textContent.trim()
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


@pytest.mark.parametrize(
    ("width", "height", "inset_left", "inset_right"),
    [
        (320, 700, 0, 0),
        (320, 700, 44, 0),
        (320, 700, 0, 44),
        (390, 844, 44, 0),
        (390, 844, 0, 44),
    ],
)
def test_single_workspace_mobile_320_prepared_download_is_readable_and_clickable(
    tmp_path: Path,
    width: int,
    height: int,
    inset_left: int,
    inset_right: int,
) -> None:
    """Use actual CDP CSS viewports, including simulated left/right screen safe areas."""
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("mobile browser smoke runs only in the Python 3.12 CI lane")

    from websockets.sync.client import connect

    chrome = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("Chrome/Chromium is required for the mobile 320px browser smoke")
        pytest.skip("Chrome/Chromium is unavailable")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    # Chrome desktop does not expose hardware-notch env() values; substitute
    # the exact CSS safe-area values in the isolated build, never the repo.
    styles_path = output / "styles.css"
    styles = styles_path.read_text(encoding="utf-8")
    assert "env(safe-area-inset-left)" in styles
    assert "env(safe-area-inset-right)" in styles
    styles = styles.replace("env(safe-area-inset-left)", f"{inset_left}px")
    styles = styles.replace("env(safe-area-inset-right)", f"{inset_right}px")
    # Simulate a browser without :has() in this isolated Chrome build.
    styles = styles.replace(":has(", ":unsupported-pseudo(")
    styles_path.write_text(styles, encoding="utf-8")
    probe_js = r"""
const wait = async (predicate, label) => {
  for (let attempt = 0; attempt < 350; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(label);
};
(async () => {
  const xml = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
    + '<mxCell id="a" value="Ali" vertex="1" parent="1">'
    + '<mxGeometry x="20" y="20" width="140" height="60" as="geometry"/>'
    + '</mxCell></root></mxGraphModel>';
  document.querySelector("#sourceInput").value = xml;
  document.querySelector("#openPasteButton").click();
  await wait(
    () => !document.querySelector("#workspace").hidden
      && document.querySelector("#projectButton").textContent.trim() === "Original"
      && document.querySelector("#editorFrame").src.includes("/native/"),
    "native draw.io import did not become ready",
  );
  const exportMenu = document.querySelector(".workspace-export-menu");
  exportMenu.open = true;
  document.querySelector("#projectButton").click();
  const download = document.querySelector("#downloadLink");
  await wait(
    () => !download.hidden && download.querySelector(".download-caption")?.textContent.trim()
      === "Originalprojekt speichern",
    "prepared original download did not appear",
  );
  const fullDownloadCaption = download.querySelector(".download-caption");
  const shortCaption = download.querySelector(".download-short-caption");
  if (!fullDownloadCaption
      || fullDownloadCaption.textContent.trim() !== "Originalprojekt speichern"
      || getComputedStyle(fullDownloadCaption).display !== "none"
      || !shortCaption || shortCaption.textContent.trim() !== "Speichern"
      || getComputedStyle(shortCaption).display !== "block") {
    throw new Error("mobile original download captions have incorrect visibility");
  }
  const shortStyle = getComputedStyle(shortCaption);
  if (shortStyle.textOverflow !== "ellipsis" || shortStyle.overflowX !== "hidden") {
    throw new Error("mobile short caption does not own controlled text truncation");
  }
  if (shortCaption.scrollWidth > shortCaption.clientWidth + 1) {
    throw new Error("P2: visible Speichern caption is shortened: "
      + shortCaption.clientWidth + "/" + shortCaption.scrollWidth);
  }
  if (!(download.getAttribute("aria-label") || "").startsWith(shortCaption.textContent.trim())) {
    throw new Error("P2: accessible save name lacks visible Speichern prefix");
  }
  const safeLeft = __LEFT__;
  const safeRight = __RIGHT__;
  if (innerWidth !== __WIDTH__ || innerHeight !== __HEIGHT__) {
    throw new Error("Chrome did not use the requested CSS viewport");
  }
  const toolsMenu = document.querySelector(".workspace-tools-menu");
  if (toolsMenu.hidden) {
    throw new Error("native draw.io tools menu was hidden despite compatibility action");
  }
  for (const label of [
    toolsMenu.querySelector(".workspace-menu-label"),
    exportMenu.querySelector(".workspace-menu-label"),
  ]) {
    if (!label || !label.textContent.trim()) {
      throw new Error("mobile action has no accessible text label");
    }
    const style = getComputedStyle(label);
    if (style.display !== "block" || style.textOverflow !== "ellipsis"
        || style.overflowX !== "hidden") {
      throw new Error("mobile summary uses ineffective flex-box text truncation");
    }
    if (label.scrollWidth > label.clientWidth + 1) {
      throw new Error("P2: mobile menu label is visibly shortened: "
        + label.textContent.trim() + ", available=" + label.clientWidth
        + ", needed=" + label.scrollWidth);
    }
    const summary = label.closest("summary");
    const visibleName = label.textContent.trim();
    const accessibleName = (summary?.getAttribute("aria-label") || visibleName).trim();
    if (!accessibleName.startsWith(visibleName)) {
      throw new Error("P2: mobile menu accessible name lacks visible label: "
        + accessibleName + " / " + visibleName);
    }
    if (!summary || parseFloat(getComputedStyle(summary).fontSize) < 12) {
      throw new Error("P2: mobile menu font is too small at " + innerWidth + "px");
    }
  }
  const close = document.querySelector("#workspaceCloseButton");
  if (!close?.getAttribute("aria-label")?.startsWith(close.textContent.trim())) {
    throw new Error("P2: Back button accessible name lacks visible label");
  }
  const bar = document.querySelector(".workspace-bar");
  const controls = [
    toolsMenu.querySelector("summary"),
    exportMenu.querySelector("summary"),
    download,
    document.querySelector("#workspaceCloseButton"),
  ];
  const rects = controls.map((control) => control.getBoundingClientRect());
  const barRect = bar.getBoundingClientRect();
  if (
    barRect.height > 54
    || barRect.left < safeLeft - 0.5
    || barRect.right > innerWidth - safeRight + 0.5
  ) {
    throw new Error("mobile workspace action bar enters the left/right safe area");
  }
  for (let i = 0; i < controls.length; i += 1) {
    const rect = rects[i];
    const control = controls[i];
    if (rect.width < 38 || rect.height < 40
        || rect.left < safeLeft - 0.5
        || rect.right > innerWidth - safeRight + 0.5) {
      throw new Error("mobile action is clipped or too small: " + i);
    }
    // A flex container must not pass merely because it declares ellipsis:
    // the inner block span now owns the actual text clipping.
    if (control.scrollWidth > control.clientWidth + 1) {
      throw new Error("mobile action text escapes its hit target: " + i);
    }
    const hit = document.elementFromPoint(
      rect.left + rect.width / 2, rect.top + rect.height / 2,
    );
    if (!hit || !control.contains(hit)) {
      throw new Error("mobile action is not the top pointer hit: " + i);
    }
    for (let j = 0; j < i; j += 1) {
      const other = rects[j];
      const overlapWidth = Math.max(
        0, Math.min(rect.right, other.right) - Math.max(rect.left, other.left),
      );
      const overlapHeight = Math.max(
        0, Math.min(rect.bottom, other.bottom) - Math.max(rect.top, other.top),
      );
      if (overlapWidth > 0.5 && overlapHeight > 0.5) {
        throw new Error("mobile action touch targets overlap: " + i + "/" + j);
      }
    }
  }
  if (download.getAttribute("aria-label") !== "Speichern: Originalprojekt") {
    throw new Error("compact download lacks its full accessible name");
  }
  if (innerWidth <= 420 && getComputedStyle(download, "::after").content !== "none") {
    throw new Error("anonymous flex pseudo-caption can escape narrow hit target");
  }
  const visibleShort = shortCaption.getBoundingClientRect();
  const downloadRect = download.getBoundingClientRect();
  if (visibleShort.width < 20 || visibleShort.left < downloadRect.left - 0.5
      || visibleShort.right > downloadRect.right + 0.5) {
    throw new Error("real short caption is clipped outside download action");
  }
  const stage = document.querySelector(".editor-stage").getBoundingClientRect();
  if (Math.abs(stage.width - innerWidth) > 1 || Math.abs(stage.height - innerHeight) > 1) {
    throw new Error("mobile action bar reduced the actual canvas viewport");
  }
  toolsMenu.open = true;
  await wait(
    () => document.body.classList.contains("workspace-menu-open"),
    "menu-open fallback did not update without :has()",
  );
  // The isolated page deliberately omits details[name], emulating engines
  // without native mutual exclusion. JS must close the first menu itself.
  exportMenu.open = true;
  await wait(
    () => !toolsMenu.open && exportMenu.open,
    "unsupported details[name] left both workspace menus open",
  );
  exportMenu.open = false;
  await wait(
    () => !document.body.classList.contains("workspace-menu-open"),
    "closing sibling popover did not restore status",
  );
  toolsMenu.open = true;
  await wait(
    () => document.body.classList.contains("workspace-menu-open"),
    "tools popover did not reopen after sibling closure",
  );
  const popover = toolsMenu.querySelector(".workspace-popover").getBoundingClientRect();
  const gap = barRect.top - popover.bottom;
  if (
    gap < 6 || gap > 14
    || popover.left < safeLeft - 0.5
    || popover.right > innerWidth - safeRight + 0.5
  ) {
    throw new Error("mobile tools popover enters the safe area or detaches from the bar");
  }
  const status = document.querySelector("body.workspace-active .status");
  if (getComputedStyle(status).visibility !== "hidden") {
    throw new Error("mobile status overlaps the open tools menu");
  }
  toolsMenu.open = false;
  await wait(
    () => !document.body.classList.contains("workspace-menu-open"),
    "menu-closed fallback did not restore status",
  );
  if (getComputedStyle(status).visibility !== "visible") {
    throw new Error("mobile status did not return after menu close");
  }
  exportMenu.open = true;
  const exportPopover = exportMenu.querySelector(".workspace-popover").getBoundingClientRect();
  if (
    exportPopover.left < safeLeft - 0.5
    || exportPopover.right > innerWidth - safeRight + 0.5
  ) {
    throw new Error("mobile export popover enters the safe area");
  }
  exportMenu.open = false;
  await wait(
    () => !document.body.classList.contains("workspace-menu-open"),
    "export menu did not close",
  );

  // An active native retry and the host status require distinct overlay rows.
  const retry = document.querySelector("#nativeRetryButton");
  const priorStatus = status.textContent;
  retry.hidden = false;
  status.textContent = "Native Änderung nicht neu gerendert · Neu rendern zum Wiederholen";
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const statusRect = status.getBoundingClientRect();
  const retryRect = retry.getBoundingClientRect();
  const collisionWidth = Math.max(0,
    Math.min(statusRect.right, retryRect.right) - Math.max(statusRect.left, retryRect.left));
  const collisionHeight = Math.max(0,
    Math.min(statusRect.bottom, retryRect.bottom) - Math.max(statusRect.top, retryRect.top));
  if (collisionWidth > 0.5 && collisionHeight > 0.5) {
    throw new Error("native retry button covers workspace error status");
  }
  retry.hidden = true;
  status.textContent = priorStatus;

  // The active native-editing prompt must remain visible and clear of controls.
  document.querySelector("#workspaceCloseButton").click();
  await wait(
    () => document.querySelector("#workspace").hidden
      && !document.querySelector("#startView").hidden,
    "could not return to start for hosted native-editor status check",
  );
  document.querySelector("#sourceInput").value = JSON.stringify({
    nodes: [
      {id: "a", type: "text", x: 0, y: 0, width: 220, height: 120, text: "Alpha"},
      {id: "b", type: "text", x: 20, y: 5000, width: 220, height: 120, text: "Beta"},
    ],
    edges: [],
  });
  document.querySelector("#openPasteButton").click();
  await wait(() => {
    const frame = document.querySelector("#editorFrame");
    return !document.querySelector("#workspace").hidden
      && frame?.contentDocument?.body?.classList.contains("document-editor-hosted")
      && frame.contentDocument.querySelector('[data-source-id="a"]');
  }, "editable native diagram did not load");
  const nativeFrame = document.querySelector("#editorFrame");
  const nativeDoc = nativeFrame.contentDocument;
  const nativeStatus = nativeDoc.querySelector("#status");
  // Real hosted geometry: the iframe's env(safe-area-*) can differ from host.
  const nativeFrameRect = nativeFrame.getBoundingClientRect();
  const nativeInteractiveControls = [
    nativeDoc.querySelector("#zoomOut"),
    nativeDoc.querySelector("#zoomIn"),
    nativeDoc.querySelector("#fitView"),
    nativeDoc.querySelector("#resetLayout"),
    nativeDoc.querySelector(".edit-controls > summary"),
  ];
  const hostedSafeLeft = __LEFT__;
  const hostedSafeRight = __RIGHT__;
  for (const nativeControl of nativeInteractiveControls) {
    if (!nativeControl || !nativeControl.getClientRects().length) continue;
    const nativeRect = nativeControl.getBoundingClientRect();
    if (nativeFrameRect.left + nativeRect.left < hostedSafeLeft - 0.5
        || nativeFrameRect.left + nativeRect.right > innerWidth - hostedSafeRight + 0.5) {
      throw new Error("P2: embedded Native control enters host horizontal safe area: "
        + (nativeControl.id || nativeControl.tagName) + " "
        + (nativeFrameRect.left + nativeRect.left).toFixed(1) + "/"
        + (nativeFrameRect.left + nativeRect.right).toFixed(1)
        + " host-right=" + document.querySelector(".workspace-bar").getBoundingClientRect().right.toFixed(1)
        + " child-right-var=" + nativeDoc.documentElement.style.getPropertyValue("--host-safe-right")
        + " child-left-var=" + nativeDoc.documentElement.style.getPropertyValue("--host-safe-left")
        + " frame=" + nativeFrameRect.left.toFixed(1) + "/" + nativeFrameRect.right.toFixed(1));
    }
  }
  const nativeSelectionFooter = nativeDoc.querySelector(".viewer-foot");
  const nativeFooterRect = nativeSelectionFooter.getBoundingClientRect();
  if (nativeFrameRect.left + nativeFooterRect.left < hostedSafeLeft - 0.5
      || nativeFrameRect.left + nativeFooterRect.right > innerWidth - hostedSafeRight + 0.5) {
    throw new Error("P2: embedded Native selection footer enters host safe area");
  }
  const hostToolbarRect = document.querySelector(".workspace-bar").getBoundingClientRect();
  const footerOverlapWidth = Math.max(0,
    Math.min(nativeFrameRect.left + nativeFooterRect.right, hostToolbarRect.right)
    - Math.max(nativeFrameRect.left + nativeFooterRect.left, hostToolbarRect.left));
  const footerOverlapHeight = Math.max(0,
    Math.min(nativeFrameRect.top + nativeFooterRect.bottom, hostToolbarRect.bottom)
    - Math.max(nativeFrameRect.top + nativeFooterRect.top, hostToolbarRect.top));
  if (footerOverlapWidth > 0.5 && footerOverlapHeight > 0.5) {
    throw new Error("P2: host workspace toolbar obscures Native selection footer");
  }
  const emptyNativeTools = document.querySelector(".workspace-tools-menu");
  if (!emptyNativeTools.hidden || getComputedStyle(emptyNativeTools).display !== "none") {
    throw new Error("native canvas shows an empty tools menu without :has()");
  }
  await new Promise((resolve) => setTimeout(resolve, 200));
  // Live CSS viewport, real editable JSON canvas and actual production limit message.
  nativeDoc.querySelector("#fitView").click();
  const barBeforeGrowth = nativeDoc.querySelector(".viewer-bar").getBoundingClientRect().bottom;
  const firstNode = nativeDoc.querySelector('[data-source-id="a"]');
  const limits = JSON.parse(nativeDoc.querySelector("#nativeLimits").textContent);
  nativeStatus.textContent = "Produktgrenze erreicht · maximal " + limits.max_edges
    + " Kanten und " + limits.max_routing_pairs + " Routing-Paare";
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const barAfterGrowth = nativeDoc.querySelector(".viewer-bar").getBoundingClientRect().bottom;
  const topNodeAfterGrowth = firstNode.getBoundingClientRect().top;
  if (barAfterGrowth <= barBeforeGrowth + 1) {
    throw new Error("long real status did not expand native overlay: "
      + barBeforeGrowth.toFixed(2) + "/" + barAfterGrowth.toFixed(2));
  }
  if (topNodeAfterGrowth < barAfterGrowth + 8) {
    throw new Error("auto-fit top node obscured by grown status overlay: "
      + topNodeAfterGrowth.toFixed(2) + "/" + barAfterGrowth.toFixed(2));
  }
  nativeDoc.querySelector("#fitView").click();
  nativeStatus.textContent = "Ziel f\u00fcr die neue Verbindung ausw\u00e4hlen";
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const promptRect = nativeStatus.getBoundingClientRect();
  const nativeControlsRect = nativeDoc.querySelector(".controls").getBoundingClientRect();
  const promptIntersectionX = Math.max(0,
    Math.min(promptRect.right, nativeControlsRect.right)
    - Math.max(promptRect.left, nativeControlsRect.left));
  const promptIntersectionY = Math.max(0,
    Math.min(promptRect.bottom, nativeControlsRect.bottom)
    - Math.max(promptRect.top, nativeControlsRect.top));
  if (promptIntersectionX > 0.5 && promptIntersectionY > 0.5) {
    throw new Error("native editing process instruction is hidden under zoom/edit controls");
  }
  if (
    nativeStatus.scrollWidth > nativeStatus.clientWidth + 1
    || nativeStatus.scrollHeight > nativeStatus.clientHeight + 1
    || (innerWidth <= 360 && promptRect.width < 160)
  ) {
    throw new Error("native editing process instruction is too narrow or clipped");
  }
  const nativeStage = nativeDoc.querySelector(".viewer-stage").getBoundingClientRect();
  if (
    Math.abs(nativeStage.width - innerWidth) > 1
    || Math.abs(nativeStage.height - innerHeight) > 1
  ) {
    throw new Error("native editing process status reduced the full canvas viewport");
  }
  // A status change between pointer moves may grow the native toolbar.
  // A manual node drag must preserve its view transform across that resize.
  if (innerWidth === 390) {
    const nativeWin = nativeFrame.contentWindow;
    const dragViewport = nativeDoc.querySelector("#nativeViewport");
    const dragCanvas = nativeDoc.querySelector("#nativeCanvas");
    const dragNode = nativeDoc.querySelector('[data-source-id="a"]');
    nativeWin.Element.prototype.setPointerCapture = function () {};
    nativeWin.Element.prototype.releasePointerCapture = function () {};
    nativeDoc.querySelector("#fitView").click();
    const waitFrame = () => new Promise((resolve) => nativeWin.requestAnimationFrame(
      () => nativeWin.requestAnimationFrame(resolve)
    ));
    await waitFrame();
    const barBeforeDrag = nativeDoc.querySelector(".viewer-bar").getBoundingClientRect().bottom;
    const viewBeforeDrag = dragCanvas.style.transform;
    const nodeRect = dragNode.getBoundingClientRect();
    const startX = nodeRect.left + Math.max(1, nodeRect.width / 2);
    const startY = nodeRect.top + Math.max(1, nodeRect.height / 2);
    const fireDrag = (target, type, x, y) => target.dispatchEvent(
      new nativeWin.PointerEvent(type, {
        bubbles: true, cancelable: true, pointerId: 73, pointerType: "mouse",
        isPrimary: true, button: 0, buttons: type === "pointerup" ? 0 : 1,
        clientX: x, clientY: y,
      })
    );
    // Interruptions must not commit canceled edits or allow background re-fit
    // while the user's pointer gesture has already taken ownership.
    const limitsNow = JSON.parse(nativeDoc.querySelector("#nativeLimits").textContent);
    const longStatus = "Produktgrenze erreicht · maximal " + limitsNow.max_edges
      + " Kanten und " + limitsNow.max_routing_pairs + " Routing-Paare";
    const resetFit = async () => {
      nativeDoc.querySelector("#fitView").click();
      await waitFrame();
    };
    await resetFit();
    const holdView = dragCanvas.style.transform;
    fireDrag(dragNode, "pointerdown", startX, startY);
    nativeStatus.textContent = longStatus;
    await waitFrame();
    if (dragCanvas.style.transform !== holdView) {
      throw new Error("pre-threshold node hold allowed status re-fit: "
        + holdView + " => " + dragCanvas.style.transform);
    }
    fireDrag(dragViewport, "pointercancel", startX, startY);
    await resetFit();

    const startNodeOffset = dragNode.getAttribute("transform");
    const startNodeLeft = dragNode.getBoundingClientRect().left;
    fireDrag(dragNode, "pointerdown", startX, startY);
    fireDrag(dragViewport, "pointermove", startX + 24, startY + 3);
    await waitFrame();
    if (dragNode.getBoundingClientRect().left < startNodeLeft + 8) {
      throw new Error("cancel test did not perform a real node drag");
    }
    fireDrag(dragViewport, "pointercancel", startX + 24, startY + 3);
    await waitFrame();
    if (dragNode.getAttribute("transform") !== startNodeOffset) {
      throw new Error("pointercancel committed a moved node instead of rollback");
    }
    await resetFit();

    const touch = (type, id, cx, cy) => dragViewport.dispatchEvent(
      new nativeWin.PointerEvent(type, {
        bubbles: true, cancelable: true, pointerId: id, pointerType: "touch",
        isPrimary: id === 82, button: 0, buttons: type === "pointerup" ? 0 : 1,
        clientX: cx, clientY: cy,
      })
    );
    const pinchBefore = dragCanvas.style.transform;
    touch("pointerdown", 82, 120, 420);
    touch("pointerdown", 83, 255, 420);
    nativeStatus.textContent = longStatus;
    await waitFrame();
    if (dragCanvas.style.transform !== pinchBefore) {
      throw new Error("pinch initiation allowed status re-fit before pointer movement");
    }
    touch("pointerup", 83, 255, 420);
    touch("pointerup", 82, 120, 420);
    await resetFit();

    // Background pan owns its view before a first move, even during status growth.
    const heldPanView = dragCanvas.style.transform;
    fireDrag(dragViewport, "pointerdown", 280, 400);
    nativeStatus.textContent = longStatus;
    await waitFrame();
    if (dragCanvas.style.transform !== heldPanView) {
      throw new Error("held background pan allowed auto-fit before first move: "
        + heldPanView + " => " + dragCanvas.style.transform);
    }
    fireDrag(dragViewport, "pointercancel", 280, 400);
    await resetFit();

    // Taking a dragged node over into pinch rolls the offset and status back.
    const takeoverInitialTransform = dragNode.getAttribute("transform");
    fireDrag(dragNode, "pointerdown", startX, startY);
    fireDrag(dragViewport, "pointermove", startX + 24, startY + 3);
    await waitFrame();
    if (nativeStatus.textContent.trim() !== "Position geändert · Verbindungen angepasst") {
      throw new Error("takeover test did not start from an active node drag");
    }
    touch("pointerdown", 82, 255, 420);
    await waitFrame();
    if (dragNode.getAttribute("transform") !== takeoverInitialTransform) {
      throw new Error("pinch takeover did not rollback dragged node");
    }
    if (nativeStatus.textContent.trim() !== "Verschieben abgebrochen") {
      throw new Error("pinch takeover retained stale drag mutation status");
    }
    touch("pointerup", 82, 255, 420);
    fireDrag(dragViewport, "pointerup", startX + 24, startY + 3);
    await resetFit();

    fireDrag(dragNode, "pointerdown", startX, startY);
    fireDrag(dragViewport, "pointermove", startX + 24, startY + 3);
    await waitFrame();
    const dragStatus = nativeStatus.textContent.trim();
    const barDuringDrag = nativeDoc.querySelector(".viewer-bar").getBoundingClientRect().bottom;
    if (dragStatus !== "Position geändert · Verbindungen angepasst") {
      throw new Error("node drag did not set expected live status: " + dragStatus);
    }
    if (barDuringDrag <= barBeforeDrag + 1) {
      throw new Error("drag status did not expand overlay in 390px regression: "
        + barBeforeDrag.toFixed(2) + "/" + barDuringDrag.toFixed(2));
    }
    if (dragCanvas.style.transform !== viewBeforeDrag) {
      throw new Error("dragging node triggered auto-fit after status growth: "
        + viewBeforeDrag + " => " + dragCanvas.style.transform);
    }
    fireDrag(dragViewport, "pointermove", startX + 37, startY + 3);
    await waitFrame();
    if (dragCanvas.style.transform !== viewBeforeDrag) {
      throw new Error("native drag view changed between pointer moves");
    }
    fireDrag(dragViewport, "pointerup", startX + 37, startY + 3);
  }
  document.documentElement.dataset.mobileBar320Smoke = "pass";
})().catch((error) => {
  document.documentElement.dataset.mobileBar320Smoke = "fail";
  document.documentElement.dataset.mobileBar320Error = String(error?.message || error);
});
"""
    probe_js = (
        probe_js.replace("__WIDTH__", str(width))
        .replace("__HEIGHT__", str(height))
        .replace("__LEFT__", str(inset_left))
        .replace("__RIGHT__", str(inset_right))
    )
    (output / "mobile-bar-320.js").write_text(probe_js, encoding="utf-8")
    index = output / "index.html"
    original_markup = index.read_text(encoding="utf-8")
    assert original_markup.count(' name="workspace-menu"') == 2
    without_native_exclusivity = original_markup.replace(' name="workspace-menu"', "")
    index.write_text(
        without_native_exclusivity.replace(
            "</body>", '<script type="module" src="mobile-bar-320.js"></script></body>',
        ),
        encoding="utf-8",
    )

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_EditorRequestHandler, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    chrome_profile = tmp_path / "chrome-profile"
    debug_port_file = chrome_profile / "DevToolsActivePort"
    proc = subprocess.Popen(
        [
            chrome, "--headless=new", "--no-first-run", "--disable-gpu",
            "--disable-dev-shm-usage", "--no-sandbox",
            "--remote-allow-origins=http://localhost",
            "--remote-debugging-port=0",
            f"--user-data-dir={chrome_profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(100):
            try:
                # Chrome owns port selection; no temporary free-port race.
                port_text = debug_port_file.read_text(encoding="utf-8").splitlines()[0]
                debug_port = int(port_text)
                if not 1 <= debug_port <= 65535:
                    raise ValueError("invalid Chrome debugging port")
                with urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=1) as response:
                    tabs = json.load(response)
                tab = next((item for item in tabs if item.get("type") == "page"), None)
                if tab:
                    break
            except (OSError, TimeoutError, ValueError, IndexError):
                pass
            time.sleep(0.12)
        assert tab, "Chrome DevTools page was not ready"

        with connect(tab["webSocketDebuggerUrl"], origin="http://localhost") as ws:
            message_id = 0

            def cdp(method: str, parameters: dict | None = None) -> dict:
                nonlocal message_id
                message_id += 1
                expected_id = message_id
                ws.send(json.dumps({
                    "id": expected_id, "method": method, "params": parameters or {},
                }))
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    timeout = min(10, max(0.1, deadline - time.monotonic()))
                    message = json.loads(ws.recv(timeout=timeout))
                    if message.get("id") == expected_id:
                        assert "error" not in message, message.get("error")
                        return message.get("result", {})
                raise AssertionError("Chrome DevTools response timed out: " + method)

            cdp("Page.enable")
            cdp("Runtime.enable")
            cdp("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height,
                "deviceScaleFactor": 1, "mobile": False,
            })
            cdp("Page.navigate", {"url": f"http://127.0.0.1:{server.server_address[1]}/"})
            for _ in range(120):
                evaluated = cdp("Runtime.evaluate", {
                    "expression": (
                        "({state:document.documentElement.dataset.mobileBar320Smoke||'',"
                        "error:document.documentElement.dataset.mobileBar320Error||''})"
                    ),
                    "returnByValue": True,
                })
                result = evaluated.get("result", {}).get("value", {})
                if result.get("state") == "fail":
                    pytest.fail(str(result.get("error")))
                if result.get("state") == "pass":
                    break
                time.sleep(0.1)
            else:
                pytest.fail("real 320px mobile bar probe did not finish")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
