from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_product_shell_is_single_workspace_and_responsive(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert "Vom Gedanken zum Schaubild." in index_html
    assert 'class="start-layout"' in index_html
    assert 'class="import-panel"' in index_html
    assert '<details class="advanced-settings">' in index_html
    assert ">Leeres Schaubild<" in index_html

    assert index_html.count('id="workspace"') == 1
    assert index_html.count('class="editor-stage"') == 1
    assert (
        '<details class="workspace-menu workspace-tools-menu" name="workspace-menu">'
        in index_html
    )
    assert (
        '<details class="workspace-menu workspace-export-menu" name="workspace-menu">'
        in index_html
    )
    assert 'class="workspace-popover workspace-tools-popover"' in index_html
    assert 'class="workspace-popover workspace-output"' in index_html
    assert 'id="backButton"' not in index_html
    assert 'id="fullscreenButton"' not in index_html
    assert 'id="workspaceCloseButton"' in index_html
    assert 'id="projectButton"' in index_html
    assert 'data-export="png"' in index_html
    assert 'data-export="svg"' in index_html

    assert "[hidden] { display: none !important; }" in styles_css
    assert "height: 100dvh;" in styles_css
    assert ".workspace-bar {" in styles_css
    assert ".workspace-popover {" in styles_css
    assert "--workspace-bar-height: 44px;" in styles_css
    assert "--workspace-dock-height" not in styles_css
    assert "body.workspace-active.engine-legacy .editor-stage {" not in styles_css
    assert "body.editor-focus" not in styles_css
    assert ".fullscreen-toggle" not in styles_css
    assert ".workspace-bar { overflow-x: auto; }" not in styles_css
    # Legacy font/layout actions must remain reachable without :has().
    assert "body.engine-legacy .workspace-tools-menu {" not in styles_css
    assert ".workspace-tools-menu[hidden] { display: none; }" in styles_css
    assert "body.engine-native .workspace-tools-menu:not(:has(" not in styles_css
    assert ".workspace-menu-label {" in styles_css
    assert "text-overflow: ellipsis;" in styles_css
    assert (
        "toolsMenu.hidden = native && "
        "!(currentRepresentation || currentLegacyXml || historyAvailable);"
    ) in app_js
    assert 'id="nativeUndoButton"' in index_html
    assert 'id="nativeRedoButton"' in index_html
    assert 'id="nativeHistoryControls"' in index_html
    assert "function moveNativeHistory(direction)" in app_js
    assert 'menu.addEventListener("toggle", syncWorkspaceMenuOpenState);' in app_js
    # Unsupported :has() must not invalidate the independent class fallback.
    assert "body.workspace-active.workspace-menu-open .topline {" in styles_css

    assert "fontControls.hidden = native;" in app_js
    assert "elements.layoutButton.hidden = native;" in app_js
    # PNG export is supported by the native editor; do not resurrect its old hide gate.
    assert "pngButton.hidden = native;" not in app_js
    assert 'elements.projectButton.textContent = "Canvas";' in app_js
    assert 'elements.projectButton.textContent = "Original";' in app_js
    assert 'elements.projectButton.textContent = "Quelle";' in app_js
    assert 'elements.projectButton.textContent = "Projekt";' in app_js
    assert "function setWorkspaceActive(active)" in app_js
    assert "setWorkspaceActive(true);" in app_js
    assert 'elements.workspaceCloseButton.addEventListener("click", showStart);' in app_js
    assert "toggleEditorFullscreen" not in app_js
    assert "syncWorkspaceDockHeight" not in app_js
    assert "ResizeObserver" not in app_js

    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "font-size: clamp(2.85rem, 13.2vw, 4rem)" in mobile_css
    assert "min-height: 160px" in mobile_css
    assert ".workspace-bar {" in mobile_css
    assert "right: max(6px, env(safe-area-inset-right));" in mobile_css
    assert mobile_css.count(
        "100vw - max(6px, env(safe-area-inset-left))"
    ) == 2
    assert mobile_css.count(
        "- max(6px, env(safe-area-inset-right))"
    ) == 2
    assert "min-height: 42px;" in mobile_css
    assert "bottom: calc(100% + var(--workspace-overlay-gap) + 48px);" in mobile_css

    dark_css = styles_css[styles_css.index("@media (prefers-color-scheme: dark)") :]
    assert ".workspace-popover { background: rgba(16, 18, 25, 0.88); }" in dark_css
    dark_status = dark_css[
        dark_css.index("body.workspace-active .status {")
        : dark_css.index(".paste-box textarea")
    ]
    assert "color: var(--ink);" in dark_status
    assert "background: var(--surface-raised);" in dark_status
    assert "border-color: var(--line-strong);" in dark_status

def test_muted_text_remains_wcag_aa_readable_over_both_background_glows(
    tmp_path: Path,
) -> None:
    """Even the combined maximum of both radial overlays must meet 4.5:1.

    This is stricter than a single viewport: the two glows have distinct
    centers, so their maximum opacities cannot normally coincide. The previous
    light muted token failed on the real 360/390 px landing page at 4.36/4.39:1.
    """
    import re

    output = tmp_path / "editor"
    build_standalone_editor(output)
    css = (output / "styles.css").read_text(encoding="utf-8")
    light_css, dark_css = css.split("@media (prefers-color-scheme: dark)", 1)
    assert ".lede {" in light_css and "color: var(--muted);" in light_css

    def css_color(scope: str, name: str) -> tuple[int, int, int]:
        match = re.search(rf"--{name}:\s*#([0-9a-f]{{6}});", scope)
        assert match, f"Missing CSS variable --{name}"
        value = match.group(1)
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))

    def luminance(rgb: tuple[int, int, int]) -> float:
        def channel(value: int) -> float:
            srgb = value / 255
            return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

        return sum(weight * channel(value) for weight, value in zip((0.2126, 0.7152, 0.0722), rgb))

    for theme, scope in (("light", light_css), ("dark", dark_css)):
        body = re.search(r"(?:^|\n)\s*body\s*\{([^{}]+)\}", scope)
        assert body, f"No {theme} body background"
        stops = re.findall(
            r"radial-gradient\([^\n]*?rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)",
            body.group(1),
        )
        assert len(stops) == 2, f"Unexpected {theme} radial gradient background"
        background = css_color(scope, "bg")
        # CSS paints the first background layer on top of the second.
        for red, green, blue, alpha in reversed(stops):
            opacity = float(alpha)
            assert 0 <= opacity <= 1
            background = tuple(
                round(opacity * foreground + (1 - opacity) * underneath)
                for foreground, underneath in zip((int(red), int(green), int(blue)), background)
            )
        foreground_luminance = luminance(css_color(scope, "muted"))
        background_luminance = luminance(background)
        ratio = (max(foreground_luminance, background_luminance) + 0.05) / (
            min(foreground_luminance, background_luminance) + 0.05
        )
        assert ratio >= 4.5, f"{theme} muted text on overlapping glows: {ratio:.2f}:1"
