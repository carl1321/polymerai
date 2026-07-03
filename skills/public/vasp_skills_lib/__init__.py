"""vasp_skills_lib - shared library for vasp-skills atomic skills."""

from .config import Config, load_config  # noqa: F401
from .inputs.sets import (  # noqa: F401
    build_band_inputs,
    build_dielectric_inputs,
    build_dos_inputs,
    build_lobster_inputs,
    build_magnetic_inputs,
    build_optics_inputs,
    build_relax_inputs,
    build_scf_inputs,
    resolve_input_files,
)
from .runner import build_submit_script, resolve_vasp_command, run_with_handlers  # noqa: F401

__version__ = "0.1.0"
