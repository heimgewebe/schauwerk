from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import schauwerk.fundus.package_contract as package_contract
from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.errors import FundusError
from schauwerk.fundus.model import canonical_json, digest_bytes, digest_json
from schauwerk.fundus.package_contract import (
    canonical_consumer_lock_bytes,
    consumer_lock_manifest,
    load_consumer_lock,
    verify_consumer_lock,
    verify_package_directory,
)
from schauwerk.runner import main as runner_main

SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<path fill="#000" d="M0 0L10 0L10 10Z"/></svg>'
)


def _package(tmp_path: Path, *, version: int) -> tuple[Path, dict]:
    root = tmp_path / f"package-v{version}"
    assets = root / "assets"
    assets.mkdir(parents=True)
    asset_path = assets / "fixture-mask.svg"
    asset_path.write_bytes(SVG)
    file_record = {
        "path": "assets/fixture-mask.svg",
        "role": "mask",
        **({"source_role": "trace_source"} if version == 2 else {}),
        "media_type": "image/svg+xml",
        "sha256": digest_bytes(SVG),
        "bytes": len(SVG),
    }
    body = {
        "schema_version": f"schauwerk-fundus-package.v{version}",
        "asset_id": "fixture.mask",
        "build_digest": "a" * 64,
        "acceptance_digest": "b" * 64,
        "files": [file_record],
        **(
            {
                "source_image_briefs": [
                    {"role": "trace_source", "sha256": "c" * 64}
                ]
            }
            if version == 2
            else {}
        ),
        "consumer_runtime_dependency": False,
    }
    manifest = {**body, "package_digest": digest_json(body)}
    manifest_bytes = canonical_json(manifest) + b"\n"
    (root / "fundus-package.json").write_bytes(manifest_bytes)
    (root / "SHA256SUMS").write_text(
        f"{file_record['sha256']}  {file_record['path']}\n"
        f"{digest_bytes(manifest_bytes)}  fundus-package.json\n",
        encoding="utf-8",
    )
    return root, manifest


@pytest.mark.parametrize("version", [1, 2])
def test_verify_package_directory_accepts_v1_and_v2(tmp_path: Path, version: int) -> None:
    root, manifest = _package(tmp_path, version=version)
    result = verify_package_directory(root)
    assert result["ok"] is True
    assert result["package_digest"] == manifest["package_digest"]
    assert result["consumer_runtime_dependency"] is False
    assert result["verified_files"] == manifest["files"]
    assert len(result["package_manifest_sha256"]) == 64


def test_consumer_lock_is_immutable_fundus_metadata_and_portable(tmp_path: Path) -> None:
    package_root, manifest = _package(tmp_path, version=2)
    before = sorted(path.relative_to(package_root).as_posix() for path in package_root.rglob("*"))
    fundus = Fundus(
        FundusPaths(
            data_root=tmp_path / "fundus-state",
            registry_root=tmp_path / "unused-registry",
        )
    )
    first = fundus.consumer_lock(package_root)
    second = fundus.consumer_lock(package_root)
    after = sorted(path.relative_to(package_root).as_posix() for path in package_root.rglob("*"))

    assert before == after
    assert first["lock_digest"] == second["lock_digest"]
    assert first["lock_path"] == second["lock_path"]
    assert first["package_digest"] == manifest["package_digest"]
    assert first["consumer_runtime_dependency"] is False
    lock_path = Path(first["lock_path"])
    assert (tmp_path / "fundus-state" / "consumer-locks") in lock_path.parents
    assert lock_path.read_bytes() == canonical_consumer_lock_bytes(
        {key: value for key, value in first.items() if key != "lock_path"}
    )

    checked = verify_consumer_lock(lock_path, package_root)
    assert checked["ok"] is True
    assert checked["package_digest"] == manifest["package_digest"]
    assert checked["lock_digest"] == first["lock_digest"]


def test_consumer_lock_manifest_requires_a_verified_package(tmp_path: Path) -> None:
    root, _ = _package(tmp_path, version=1)
    result = verify_package_directory(root)
    result["ok"] = False
    with pytest.raises(FundusError, match="requires a verified Fundus package"):
        consumer_lock_manifest(result)


def test_package_tampering_and_extra_files_fail_closed(tmp_path: Path) -> None:
    root, _ = _package(tmp_path, version=2)
    (root / "assets" / "fixture-mask.svg").write_bytes(SVG + b"\n")
    with pytest.raises(FundusError, match="file drifted"):
        verify_package_directory(root)


def test_package_extra_file_added_during_verification_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _package(tmp_path, version=2)
    original = package_contract._inventory
    calls = 0

    def add_after_inventory(root_fd: int):
        nonlocal calls
        result = original(root_fd)
        calls += 1
        if calls == 1:
            (root / "raced-extra.txt").write_text("extra\n", encoding="utf-8")
        return result

    monkeypatch.setattr(package_contract, "_inventory", add_after_inventory)
    with pytest.raises(FundusError, match="file set mismatch|changed during"):
        verify_package_directory(root)


@pytest.mark.parametrize(
    "active_svg",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        b'<script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        b'<image href="https://example.invalid/a.png"/></svg>',
    ],
)
def test_package_verify_rejects_active_or_external_svg(
    tmp_path: Path, active_svg: bytes
) -> None:
    root, manifest = _package(tmp_path, version=1)
    asset_path = root / manifest["files"][0]["path"]
    asset_path.write_bytes(active_svg)
    body = dict(manifest)
    body.pop("package_digest")
    body["files"][0]["sha256"] = digest_bytes(active_svg)
    body["files"][0]["bytes"] = len(active_svg)
    manifest = {**body, "package_digest": digest_json(body)}
    manifest_bytes = canonical_json(manifest) + b"\n"
    (root / "fundus-package.json").write_bytes(manifest_bytes)
    (root / "SHA256SUMS").write_text(
        f"{body['files'][0]['sha256']}  {body['files'][0]['path']}\n"
        f"{digest_bytes(manifest_bytes)}  fundus-package.json\n",
        encoding="utf-8",
    )

    with pytest.raises(FundusError, match="passive profile"):
        verify_package_directory(root)

    root, _ = _package(tmp_path / "extra", version=2)
    (root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(FundusError, match="file set mismatch"):
        verify_package_directory(root)


def test_package_sha256s_symlink_and_hardlink_fail_closed(tmp_path: Path) -> None:
    root, _ = _package(tmp_path, version=1)
    (root / "SHA256SUMS").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FundusError, match="SHA256SUMS mismatch"):
        verify_package_directory(root)

    root, _ = _package(tmp_path / "symlink", version=1)
    target = root / "assets" / "fixture-mask.svg"
    target.unlink()
    target.symlink_to(root / "fundus-package.json")
    with pytest.raises(FundusError, match="package path is a symlink"):
        verify_package_directory(root)

    root, _ = _package(tmp_path / "hardlink", version=1)
    target = root / "assets" / "fixture-mask.svg"
    os.link(target, root / "hardlink-copy.svg")
    with pytest.raises(FundusError, match="package file is unsafe|file set mismatch"):
        verify_package_directory(root)


def test_consumer_lock_tamper_and_noncanonical_paths_fail_closed(tmp_path: Path) -> None:
    root, _ = _package(tmp_path, version=2)
    package = verify_package_directory(root)
    lock = consumer_lock_manifest(package)
    lock_path = tmp_path / "fundus-consumer-lock.json"
    lock_path.write_bytes(canonical_consumer_lock_bytes(lock))

    tampered = json.loads(lock_path.read_text(encoding="utf-8"))
    tampered["package_digest"] = "d" * 64
    lock_path.write_bytes(canonical_json(tampered) + b"\n")
    with pytest.raises(FundusError, match="lock digest mismatch"):
        load_consumer_lock(lock_path)

    invalid = consumer_lock_manifest(package)
    invalid["files"][0]["path"] = "../escape.svg"
    body = dict(invalid)
    body.pop("lock_digest")
    invalid["lock_digest"] = digest_json(body)
    lock_path.write_bytes(canonical_json(invalid) + b"\n")
    with pytest.raises(FundusError, match="canonical relative path"):
        load_consumer_lock(lock_path)


def test_consumer_check_rejects_lock_from_another_package(tmp_path: Path) -> None:
    left, _ = _package(tmp_path / "left", version=1)
    right, _ = _package(tmp_path / "right", version=1)
    right_manifest_path = right / "fundus-package.json"
    right_manifest = json.loads(right_manifest_path.read_text(encoding="utf-8"))
    body = dict(right_manifest)
    body.pop("package_digest")
    body["asset_id"] = "fixture.other"
    right_manifest = {**body, "package_digest": digest_json(body)}
    right_manifest_bytes = canonical_json(right_manifest) + b"\n"
    right_manifest_path.write_bytes(right_manifest_bytes)
    record = right_manifest["files"][0]
    (right / "SHA256SUMS").write_text(
        f"{record['sha256']}  {record['path']}\n"
        f"{digest_bytes(right_manifest_bytes)}  fundus-package.json\n",
        encoding="utf-8",
    )

    lock = consumer_lock_manifest(verify_package_directory(left))
    lock_path = tmp_path / "left.lock.json"
    lock_path.write_bytes(canonical_consumer_lock_bytes(lock))
    with pytest.raises(FundusError, match="binding mismatch: asset_id"):
        verify_consumer_lock(lock_path, right)


def test_fundus_cli_package_verify_lock_and_consumer_check(tmp_path: Path, capsys) -> None:
    root, manifest = _package(tmp_path, version=2)
    assert runner_main(["fundus", "package-verify", str(root), "--json"]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["package_digest"] == manifest["package_digest"]

    data_root = tmp_path / "fundus-cli-state"
    assert (
        runner_main(
            [
                "fundus",
                "consumer-lock",
                str(root),
                "--data-root",
                str(data_root),
                "--json",
            ]
        )
        == 0
    )
    locked = json.loads(capsys.readouterr().out)
    lock_path = locked["lock_path"]
    assert Path(lock_path).is_file()

    assert (
        runner_main(
            [
                "fundus",
                "consumer-check",
                lock_path,
                str(root),
                "--json",
            ]
        )
        == 0
    )
    checked = json.loads(capsys.readouterr().out)
    assert checked["ok"] is True
    assert checked["lock_digest"] == locked["lock_digest"]


def test_package_inventory_depth_is_bounded(tmp_path: Path) -> None:
    root, _ = _package(tmp_path, version=1)
    current = root
    for index in range(18):
        current = current / f"nested-{index:02d}"
        current.mkdir()
    with pytest.raises(FundusError, match="directory depth exceeds"):
        verify_package_directory(root)


def test_package_manifest_requires_canonical_unique_json(tmp_path: Path) -> None:
    root, manifest = _package(tmp_path, version=1)
    manifest_path = root / "fundus-package.json"

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(FundusError, match="serialization is not canonical"):
        verify_package_directory(root)

    duplicate = canonical_json(manifest).decode("utf-8").replace(
        '"asset_id":"fixture.mask",',
        '"asset_id":"fixture.mask","asset_id":"fixture.mask",',
        1,
    )
    manifest_path.write_text(duplicate + "\n", encoding="utf-8")
    with pytest.raises(FundusError, match="manifest is invalid JSON"):
        verify_package_directory(root)


def test_consumer_lock_requires_canonical_unique_json(tmp_path: Path) -> None:
    root, _ = _package(tmp_path, version=2)
    package = verify_package_directory(root)
    lock = consumer_lock_manifest(package)
    lock_path = tmp_path / "fundus-consumer-lock.json"

    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    with pytest.raises(FundusError, match="serialization is not canonical"):
        load_consumer_lock(lock_path)

    duplicate = canonical_json(lock).decode("utf-8").replace(
        '"asset_id":"fixture.mask",',
        '"asset_id":"fixture.mask","asset_id":"fixture.mask",',
        1,
    )
    lock_path.write_text(duplicate + "\n", encoding="utf-8")
    with pytest.raises(FundusError, match="lock is invalid JSON"):
        load_consumer_lock(lock_path)


def test_consumer_lock_refuses_data_root_inside_package(tmp_path: Path) -> None:
    package_root, _ = _package(tmp_path, version=2)
    before = sorted(
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
    )
    fundus = Fundus(
        FundusPaths(
            data_root=package_root,
            registry_root=tmp_path / "unused-registry",
        )
    )

    with pytest.raises(
        FundusError, match="must not be materialized inside the package"
    ):
        fundus.consumer_lock(package_root)

    after = sorted(
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
    )
    assert after == before
