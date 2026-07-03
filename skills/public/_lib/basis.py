"""Basis-set helpers backed by `basis_set_exchange`.

Use this when a method needs a basis not built into Gaussian (e.g. custom ECPs).
Outputs a Gaussian-format `@basis.gbs` tail block that can be appended to an
input file via `make_input(..., tail=...)`.
"""

from __future__ import annotations


def gen_gaussian_basis_block(basis_name: str, elements: list[str]) -> str:
    """Fetch `basis_name` for the given elements and format for Gaussian input.

    elements: list of element symbols, e.g. ["H", "C", "O"].
    """
    import basis_set_exchange as bse

    text = bse.get_basis(
        basis_name,
        elements=elements,
        fmt="gaussian94",
        header=False,
    )
    return text
