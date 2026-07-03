"""Input set generation. Thin wrappers over pymatgen / atomate2 sets."""

from .sets import (  # noqa: F401
    build_relax_inputs,
    build_scf_inputs,
    build_band_inputs,
    build_dos_inputs,
)
