from __future__ import annotations

import pytest

from schauwerk.cli_parser import build_parser


def test_inspect_parser_accepts_bounded_read_options() -> None:
    args = build_parser().parse_args(
        [
            "miro",
            "inspect",
            "--query",
            "Schauwerk",
            "--owned-by-me",
            "--limit",
            "7",
            "--max-pages",
            "3",
            "--json",
        ]
    )

    assert args.command == "inspect"
    assert args.query == "Schauwerk"
    assert args.owned_by_me is True
    assert args.limit == 7
    assert args.max_pages == 3
    assert args.json is True


@pytest.mark.parametrize(
    ("option", "value"),
    [("--limit", "0"), ("--limit", "51"), ("--max-pages", "0")],
)
def test_inspect_parser_rejects_out_of_bounds_values(
    option: str,
    value: str,
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["miro", "inspect", option, value])
