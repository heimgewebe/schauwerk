from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

BROWSER_SMOKE_TEST = (
    "tests/visual/test_standalone_editor.py::"
    "test_canvas_import_browser_xml_validation_when_chrome_available"
)
MAX_ATTEMPTS = 2


def _real_chrome() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("Chrome/Chromium is required for the CI browser smoke test")


def _write_chrome_wrapper(path: Path, real_chrome: str, profile: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        f'exec "{real_chrome}" --user-data-dir="{profile}" "$@"\n',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def main() -> int:
    real_chrome = _real_chrome()
    temp_parent = os.environ.get("RUNNER_TEMP")
    if temp_parent and not Path(temp_parent).is_dir():
        temp_parent = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        with tempfile.TemporaryDirectory(
            prefix="schauwerk-browser-smoke-",
            dir=temp_parent,
        ) as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "google-chrome"
            _write_chrome_wrapper(wrapper, real_chrome, root / "profile")

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", BROWSER_SMOKE_TEST, "-q"],
                check=False,
                env=env,
            )
            if completed.returncode == 0:
                return 0

        if attempt < MAX_ATTEMPTS:
            print(
                "browser smoke failed; retrying once with a fresh Chrome profile",
                file=sys.stderr,
            )

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
