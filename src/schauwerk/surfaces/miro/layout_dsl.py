"""Small structural parser for the conservative Miro layout DSL subset."""

from __future__ import annotations

from dataclasses import dataclass


class LayoutDslParseError(ValueError):
    """The layout DSL cannot be summarized without guessing its structure."""


@dataclass(frozen=True)
class LayoutDslSummary:
    """Structural counts derived from non-comment DSL declarations."""

    line_count: int
    kind_counts: tuple[tuple[str, int], ...]

    def count(self, kind: str) -> int:
        return dict(self.kind_counts).get(kind, 0)


def summarize_layout_dsl(value: str) -> LayoutDslSummary:
    """Summarize declaration kinds while enforcing the reference-before-kind grammar."""

    if not isinstance(value, str):
        raise LayoutDslParseError("layout DSL must be text")
    line_count = 0
    counts: dict[str, int] = {}
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        line_count += 1
        tokens = stripped.split(maxsplit=2)
        if tokens[0] == "CONNECTOR":
            raise LayoutDslParseError("connector declaration requires a reference before CONNECTOR")
        if len(tokens) < 2:
            continue
        kind = tokens[1]
        counts[kind] = counts.get(kind, 0) + 1
    return LayoutDslSummary(
        line_count=line_count,
        kind_counts=tuple(sorted(counts.items())),
    )
