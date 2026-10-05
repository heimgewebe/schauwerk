from __future__ import annotations

import os
import subprocess
from pathlib import Path

from scripts import run_browser_smoke


def test_browser_smoke_retries_once_with_fresh_profiles(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(run_browser_smoke, "_real_chrome", lambda: "/bin/true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    calls: list[dict[str, str]] = []
    results = iter(
        [
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0),
        ]
    )

    def fake_run(*_args, **kwargs):
        env = kwargs["env"]
        wrapper = Path(env["PATH"].split(":", 1)[0]) / "google-chrome"
        calls.append(
            {
                "wrapper": wrapper.read_text(encoding="utf-8"),
                "path": str(wrapper),
            }
        )
        return next(results)

    monkeypatch.setattr(run_browser_smoke.subprocess, "run", fake_run)

    assert run_browser_smoke.main() == 0
    assert len(calls) == 2
    assert calls[0]["path"] != calls[1]["path"]
    assert "--user-data-dir=" in calls[0]["wrapper"]
    assert "--user-data-dir=" in calls[1]["wrapper"]



def test_browser_smoke_runner_covers_makefile_filter_exactly() -> None:
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    prefix = "BROWSER_SMOKE_FILTER := "
    filter_line = next(line for line in makefile.splitlines() if line.startswith(prefix))
    filtered_names = set(filter_line.removeprefix(prefix).split(" or "))
    runner_names = {
        nodeid.rsplit("::", 1)[1]
        for nodeid in run_browser_smoke.BROWSER_SMOKE_TESTS
    }

    assert runner_names == filtered_names


def test_ci_python_failure_stops_before_browser_smoke(tmp_path: Path) -> None:
    marker = tmp_path / "browser-smoke-started"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\" -m pytest -k \"*) exit 23 ;;\n"
        f"  *\" scripts/run_browser_smoke.py \"*) touch \"{marker}\"; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["CI"] = "true"

    completed = subprocess.run(
        ["make", "test", f"PYTHON={fake_python}"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
    )

    assert completed.returncode != 0
    assert "Fehler 23" in completed.stderr or "Error 23" in completed.stderr
    assert not marker.exists()
