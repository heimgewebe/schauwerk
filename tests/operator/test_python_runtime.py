from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import pytest

from schauwerk import runner
from schauwerk.operator.python_runtime import (
    PythonRuntimeStackError,
    inspect_python_thread_stack,
    repair_python_thread_stack,
)

_ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
_PROGRAM_HEADER = struct.Struct("<IIQQQQQQ")
_PT_NOTE = 4
_PT_GNU_STACK = 0x6474E551


def executable_fixture(tmp_path: Path, *, kind: str = "missing") -> Path:
    path = tmp_path / f"python-{kind}"
    ident = b"\x7fELF" + bytes((2, 1, 1, 0)) + b"\x00" * 8
    header = _ELF_HEADER.pack(
        ident,
        2,
        62,
        1,
        0,
        _ELF_HEADER.size,
        0,
        0,
        _ELF_HEADER.size,
        _PROGRAM_HEADER.size,
        1,
        0,
        0,
        0,
    )
    if kind == "missing":
        program = _PROGRAM_HEADER.pack(
            _PT_NOTE,
            4,
            _ELF_HEADER.size + _PROGRAM_HEADER.size,
            0,
            0,
            32,
            32,
            4,
        )
        abi_note = struct.pack("<III4sIIII", 4, 16, 1, b"GNU\x00", 0, 3, 2, 0)
        payload = header + program + abi_note
    elif kind == "nonexec":
        program = _PROGRAM_HEADER.pack(_PT_GNU_STACK, 6, 0, 0, 0, 0, 0, 16)
        payload = header + program
    elif kind == "exec":
        program = _PROGRAM_HEADER.pack(_PT_GNU_STACK, 7, 0, 0, 0, 0, 0, 16)
        payload = header + program
    else:
        raise AssertionError(kind)
    path.write_bytes(payload)
    path.chmod(0o700)
    return path


def test_inspect_reports_repairable_missing_stack_without_mutation(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    before = source.read_bytes()

    result = inspect_python_thread_stack(source)

    assert result["gnu_stack_state"] == "missing"
    assert result["repairable_missing_stack"] is True
    assert result["pt_note_count"] == 1
    assert result["mutation_attempted"] is False
    assert source.read_bytes() == before


def test_repair_writes_create_only_non_executable_stack(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    output = tmp_path / "python-repaired"
    before = source.read_bytes()

    receipt = repair_python_thread_stack(source, output)
    inspected = inspect_python_thread_stack(output)

    assert receipt["success"] is True
    assert receipt["before_gnu_stack_state"] == "missing"
    assert receipt["after_gnu_stack_state"] == "non_executable"
    assert receipt["after_gnu_stack_flags"] == 6
    assert receipt["source_replaced"] is False
    assert receipt["output_create_only"] is True
    assert receipt["host_wx_relaxed"] is False
    assert inspected["gnu_stack_state"] == "non_executable"
    assert inspected["gnu_stack_flags"] == 6
    assert inspected["pt_note_count"] == 0
    assert source.read_bytes() == before
    assert output.stat().st_mode & 0o777 == 0o700


def test_repair_rejects_non_abi_note_shape(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    payload = bytearray(source.read_bytes())
    payload[-20] = ord("X")
    source.write_bytes(payload)
    source.chmod(0o700)

    inspected = inspect_python_thread_stack(source)
    assert inspected["gnu_stack_state"] == "missing"
    assert inspected["repairable_missing_stack"] is False
    with pytest.raises(PythonRuntimeStackError, match="supported missing-GNU_STACK"):
        repair_python_thread_stack(source, tmp_path / "unused")


def test_repair_rejects_existing_output_and_already_declared_stack(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    existing = tmp_path / "existing"
    existing.write_bytes(b"do-not-replace")

    with pytest.raises(PythonRuntimeStackError, match="already exists"):
        repair_python_thread_stack(source, existing)
    assert existing.read_bytes() == b"do-not-replace"

    nonexec = executable_fixture(tmp_path, kind="nonexec")
    with pytest.raises(PythonRuntimeStackError, match="supported missing-GNU_STACK"):
        repair_python_thread_stack(nonexec, tmp_path / "unused")


def test_repair_rejects_group_writable_output_parent(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    unsafe_parent = tmp_path / "unsafe"
    unsafe_parent.mkdir(mode=0o700)
    unsafe_parent.chmod(0o720)

    with pytest.raises(PythonRuntimeStackError, match="owner-controlled directory"):
        repair_python_thread_stack(source, unsafe_parent / "python-repaired")


def test_repair_output_mode_is_not_reduced_by_umask(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    output = tmp_path / "python-repaired"
    previous = os.umask(0o777)
    try:
        repair_python_thread_stack(source, output)
    finally:
        os.umask(previous)

    assert output.stat().st_mode & 0o777 == 0o700


def test_inspect_rejects_symlink_and_hardlink_sources(tmp_path: Path) -> None:
    source = executable_fixture(tmp_path)
    symlink = tmp_path / "python-symlink"
    symlink.symlink_to(source)
    with pytest.raises(PythonRuntimeStackError, match="unsafe"):
        inspect_python_thread_stack(symlink)

    hardlink = tmp_path / "python-hardlink"
    os.link(source, hardlink)
    with pytest.raises(PythonRuntimeStackError, match="bounded owner-owned executable"):
        inspect_python_thread_stack(source)


def test_runner_dispatches_python_stack_inspect_and_repair(tmp_path: Path, capsys) -> None:
    source = executable_fixture(tmp_path)
    output = tmp_path / "python-repaired"

    assert (
        runner.main(
            [
                "runtime",
                "python-thread-stack",
                "inspect",
                str(source),
                "--json",
            ]
        )
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["gnu_stack_state"] == "missing"

    assert (
        runner.main(
            [
                "runtime",
                "python-thread-stack",
                "repair",
                str(source),
                "--output",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    repaired = json.loads(capsys.readouterr().out)
    assert repaired["after_gnu_stack_state"] == "non_executable"
