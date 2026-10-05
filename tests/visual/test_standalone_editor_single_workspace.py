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
    ("width", "height"),
    [
        (1366, 900),
        (1024, 768),
        (390, 844),
    ],
)
def test_single_workspace_browser_uses_full_canvas_and_keeps_native_actions_reachable(
    tmp_path: Path,
    width: int,
    height: int,
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
      {id: "b", type: "text", x: 320, y: 0, width: 220, height: 120, text: "Beta"},
    ],
    edges: [
      {id: "ab", fromNode: "a", toNode: "b", toEnd: "arrow", label: "verbindet"},
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

  viewer.querySelector("#fitView").click();
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
  if (viewer.querySelector("#addEdge").hidden || viewer.querySelector("#editText").hidden) {
    throw new Error("selection-dependent native edit actions stayed hidden");
  }

  svgButton.click();
  await waitUntil(
    () => !document.querySelector("#downloadLink").hidden,
    "native SVG export did not prepare a download in the same workspace",
  );
  const barRect = document.querySelector(".workspace-bar").getBoundingClientRect();
  const downloadRect = document.querySelector("#downloadLink").getBoundingClientRect();
  if (barRect.height > 54 || downloadRect.height < 40) {
    throw new Error("prepared download expanded the compact workspace chrome");
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

  document.documentElement.dataset.singleWorkspaceBrowserRegression = "pass";
  document.documentElement.dataset.singleWorkspaceViewport = `${innerWidth}x${innerHeight}`;
} catch (error) {
  document.documentElement.dataset.singleWorkspaceBrowserRegression = "fail";
  document.documentElement.dataset.singleWorkspaceBrowserRegressionError = String(
    error?.message || error
  );
}
"""
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