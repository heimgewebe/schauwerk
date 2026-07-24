"""Fail-closed inspection and output-only repair for Python ELF stack metadata."""

from __future__ import annotations

import hashlib
import os
import stat
import struct
import sys
from pathlib import Path
from typing import Any

_ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
_PROGRAM_HEADER = struct.Struct("<IIQQQQQQ")
_PT_NOTE = 4
_PT_GNU_STACK = 0x6474E551
_PF_R = 4
_PF_W = 2
_PF_X = 1
_NT_GNU_ABI_TAG = 1
_ELF_NOTE_HEADER = struct.Struct("<III")
_MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024


class PythonRuntimeStackError(ValueError):
    """The executable cannot be safely inspected or repaired."""


def _safe_candidate(path: Path, *, label: str) -> tuple[Path, os.stat_result]:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise PythonRuntimeStackError(f"{label} path is unsafe")
    try:
        metadata = candidate.lstat()
    except FileNotFoundError as exc:
        raise PythonRuntimeStackError(f"{label} is missing") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or metadata.st_size < _ELF_HEADER.size
        or metadata.st_size > _MAX_EXECUTABLE_BYTES
        or metadata.st_mode & stat.S_IXUSR == 0
    ):
        raise PythonRuntimeStackError(f"{label} must be one bounded owner-owned executable")
    return candidate, metadata


def _read_executable(path: Path) -> tuple[Path, os.stat_result, bytes]:
    candidate, metadata = _safe_candidate(path, label="Python executable")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise PythonRuntimeStackError("Python executable is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        expected = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        observed = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if expected != observed or opened.st_nlink != 1:
            raise PythonRuntimeStackError("Python executable changed during read")
        payload = bytearray()
        while len(payload) <= _MAX_EXECUTABLE_BYTES:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _MAX_EXECUTABLE_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > _MAX_EXECUTABLE_BYTES:
            raise PythonRuntimeStackError("Python executable exceeds the byte bound")
        return candidate, metadata, bytes(payload)
    finally:
        os.close(descriptor)


def _elf_layout(payload: bytes) -> dict[str, Any]:
    if len(payload) < _ELF_HEADER.size:
        raise PythonRuntimeStackError("Python executable has a truncated ELF header")
    header = _ELF_HEADER.unpack_from(payload)
    (
        ident,
        elf_type,
        machine,
        version,
        _entry,
        phoff,
        _shoff,
        _flags,
        ehsize,
        phentsize,
        phnum,
        *_,
    ) = header
    if ident[:4] != b"\x7fELF" or ident[4:7] != bytes((2, 1, 1)):
        raise PythonRuntimeStackError("Python executable is not ELF64 little-endian")
    if elf_type not in {2, 3} or machine != 62 or version != 1:
        raise PythonRuntimeStackError("Python executable has an unsupported ELF identity")
    if ehsize != _ELF_HEADER.size or phentsize != _PROGRAM_HEADER.size or not 1 <= phnum <= 128:
        raise PythonRuntimeStackError("Python executable has an unsupported program-header table")
    table_end = phoff + phentsize * phnum
    if phoff < ehsize or table_end > len(payload):
        raise PythonRuntimeStackError("Python executable has an out-of-bounds program-header table")

    stacks: list[tuple[int, int, tuple[int, ...]]] = []
    notes: list[tuple[int, int, tuple[int, ...]]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        values = _PROGRAM_HEADER.unpack_from(payload, offset)
        if values[0] == _PT_GNU_STACK:
            stacks.append((index, offset, values))
        elif values[0] == _PT_NOTE:
            notes.append((index, offset, values))
    if len(stacks) > 1:
        raise PythonRuntimeStackError("Python executable has multiple GNU_STACK headers")

    stack_flags = stacks[0][2][1] if stacks else None
    stack_state = (
        "missing"
        if stack_flags is None
        else "executable"
        if stack_flags & _PF_X
        else "non_executable"
    )
    repair_note = None
    if not stacks and len(notes) == 1:
        note = notes[0]
        _ptype, pflags, poff, _vaddr, _paddr, filesz, memsz, align = note[2]
        note_end = poff + filesz
        if (
            pflags == _PF_R
            and filesz == 32
            and memsz == 32
            and align == 4
            and poff >= table_end
            and note_end <= len(payload)
        ):
            namesz, descsz, note_type = _ELF_NOTE_HEADER.unpack_from(payload, poff)
            name = payload[poff + _ELF_NOTE_HEADER.size : poff + 16]
            descriptor = payload[poff + 16 : note_end]
            if (
                namesz == 4
                and descsz == 16
                and note_type == _NT_GNU_ABI_TAG
                and name == b"GNU\x00"
                and len(descriptor) == 16
                and struct.unpack_from("<I", descriptor)[0] == 0
            ):
                repair_note = note

    return {
        "elf_type": "ET_EXEC" if elf_type == 2 else "ET_DYN",
        "machine": "x86_64",
        "program_header_count": phnum,
        "gnu_stack_state": stack_state,
        "gnu_stack_flags": stack_flags,
        "pt_note_count": len(notes),
        "repairable_missing_stack": repair_note is not None,
        "repair_note": repair_note,
    }


def inspect_python_thread_stack(executable: Path | None = None) -> dict[str, Any]:
    """Inspect GNU_STACK metadata without starting a worker thread or mutating files."""

    selected = executable or Path(sys._base_executable or sys.executable)
    candidate, metadata, payload = _read_executable(Path(selected))
    layout = _elf_layout(payload)
    return {
        "schema_version": "schauwerk-python-thread-stack-inspection.v1",
        "executable": str(candidate),
        "executable_sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "mode": oct(stat.S_IMODE(metadata.st_mode)),
        "elf_type": layout["elf_type"],
        "machine": layout["machine"],
        "program_header_count": layout["program_header_count"],
        "gnu_stack_state": layout["gnu_stack_state"],
        "gnu_stack_flags": layout["gnu_stack_flags"],
        "pt_note_count": layout["pt_note_count"],
        "repairable_missing_stack": layout["repairable_missing_stack"],
        "mutation_attempted": False,
        "does_not_establish": [
            "that a worker thread was started",
            "that every extension module requests a non-executable stack",
            "permission to replace the inspected executable",
        ],
    }


def repair_python_thread_stack(source: Path, output: Path) -> dict[str, Any]:
    """Write a new executable with PT_GNU_STACK RW; never replace the source."""

    source_path, source_metadata, source_payload = _read_executable(source)
    layout = _elf_layout(source_payload)
    repair_note = layout["repair_note"]
    if layout["gnu_stack_state"] != "missing" or repair_note is None:
        raise PythonRuntimeStackError(
            "Python executable is not the supported missing-GNU_STACK shape"
        )

    destination = output.expanduser().absolute()
    if destination == source_path:
        raise PythonRuntimeStackError("repair output must differ from the source")
    if destination.exists() or destination.is_symlink():
        raise PythonRuntimeStackError("repair output already exists")
    if any(parent.is_symlink() for parent in destination.parents):
        raise PythonRuntimeStackError("repair output path is unsafe")
    try:
        parent_metadata = destination.parent.lstat()
    except FileNotFoundError as exc:
        raise PythonRuntimeStackError("repair output parent must be an existing directory") from exc
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or parent_metadata.st_mode & 0o022
    ):
        raise PythonRuntimeStackError("repair output parent must be an owner-controlled directory")

    index, offset, _values = repair_note
    repaired = bytearray(source_payload)
    _PROGRAM_HEADER.pack_into(
        repaired,
        offset,
        _PT_GNU_STACK,
        _PF_R | _PF_W,
        0,
        0,
        0,
        0,
        0,
        16,
    )
    repaired_layout = _elf_layout(repaired)
    if repaired_layout["gnu_stack_state"] != "non_executable":
        raise PythonRuntimeStackError("repaired executable failed GNU_STACK verification")

    mode = stat.S_IMODE(source_metadata.st_mode) & 0o755
    mode |= stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    output_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(destination, flags, mode)
        os.fchmod(descriptor, mode)
        opened_metadata = os.fstat(descriptor)
        output_identity = (opened_metadata.st_dev, opened_metadata.st_ino)
        view = memoryview(repaired)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        written_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(written_metadata.st_mode)
            or written_metadata.st_uid != os.getuid()
            or written_metadata.st_nlink != 1
            or written_metadata.st_size != len(repaired)
            or stat.S_IMODE(written_metadata.st_mode) != mode
        ):
            raise PythonRuntimeStackError("repair output failed filesystem verification")
        path_metadata = destination.lstat()
        if (path_metadata.st_dev, path_metadata.st_ino) != output_identity:
            raise PythonRuntimeStackError("repair output path changed during write")
        os.lseek(descriptor, 0, os.SEEK_SET)
        written_payload = bytearray()
        while len(written_payload) < len(repaired):
            chunk = os.read(descriptor, min(1024 * 1024, len(repaired) - len(written_payload)))
            if not chunk:
                break
            written_payload.extend(chunk)
        if bytes(written_payload) != repaired:
            raise PythonRuntimeStackError("repair output failed descriptor-bound byte readback")
        os.close(descriptor)
        descriptor = None
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if output_identity is not None:
            try:
                current = destination.lstat()
            except FileNotFoundError:
                current = None
            if current is not None and (current.st_dev, current.st_ino) == output_identity:
                destination.unlink()
        raise

    return {
        "schema_version": "schauwerk-python-thread-stack-repair.v1",
        "success": True,
        "source": str(source_path),
        "output": str(destination),
        "source_sha256": hashlib.sha256(source_payload).hexdigest(),
        "output_sha256": hashlib.sha256(repaired).hexdigest(),
        "bytes": len(repaired),
        "program_header_index": index,
        "before_gnu_stack_state": "missing",
        "after_gnu_stack_state": "non_executable",
        "after_gnu_stack_flags": _PF_R | _PF_W,
        "source_replaced": False,
        "output_create_only": True,
        "host_wx_relaxed": False,
        "does_not_establish": [
            "that the output has replaced the source executable",
            "that the output can start a worker thread",
            "that future runtime reinstallations preserve the repaired header",
        ],
    }
