from schauwerk import runner


def test_runner_dispatches_stage_build(monkeypatch, capsys) -> None:
    observed = {}

    def fake_build(**kwargs):
        observed.update(kwargs)
        return {"ok": True, "schema_version": "fixture"}

    monkeypatch.setattr(runner, "handle_stage_build", fake_build)
    assert (
        runner.main(
            [
                "stage",
                "build",
                "model.json",
                "--variant",
                "technical",
                "--public-dir",
                "public",
                "--presenter-dir",
                "presenter",
                "--source-root",
                "repo",
                "--json",
            ]
        )
        == 0
    )
    assert observed == {
        "model_path": "model.json",
        "variant": "technical",
        "public_dir": "public",
        "presenter_dir": "presenter",
        "source_root": "repo",
    }
    assert '"ok": true' in capsys.readouterr().out
