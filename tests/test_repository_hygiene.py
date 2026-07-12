from pathlib import Path


def test_generated_uv_lock_is_ignored() -> None:
    root = Path(__file__).resolve().parents[1]
    lines = {
        line.strip() for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    assert "uv.lock" in lines
