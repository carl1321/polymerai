"""Smoke tests for detector and templates (minimal fixture: Si primitive)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pymatgen")

SI_POSCAR = """Si
1.0
  0.0000000   2.7150000   2.7150000
  2.7150000   0.0000000   2.7150000
  2.7150000   2.7150000   0.0000000
Si
2
Direct
  0.000000  0.000000  0.000000
  0.250000  0.250000  0.250000
"""


@pytest.fixture
def si_poscar(tmp_path):
    p = tmp_path / "POSCAR"
    p.write_text(SI_POSCAR, encoding="utf-8")
    return p


def test_detector_runs(si_poscar):
    from vasp_incar.system_detector import detect

    t = detect(si_poscar)
    assert t.n_atoms == 2
    assert t.lattice_type == "FCC"
    assert t.gamma_required is True


def test_template_relax_has_ibrion2(si_poscar):
    from pymatgen.core import Structure

    from vasp_incar.system_detector import detect
    from vasp_incar.templates.relax import build

    s = Structure.from_file(str(si_poscar))
    t = detect(si_poscar)
    incar = build(s, t)
    assert incar["IBRION"] == 2
    assert incar["NSW"] > 0
    assert incar["EDIFFG"] < 0


def test_template_band_has_icharg11(si_poscar):
    from pymatgen.core import Structure

    from vasp_incar.system_detector import detect
    from vasp_incar.templates.band import build

    s = Structure.from_file(str(si_poscar))
    t = detect(si_poscar)
    incar = build(s, t)
    assert incar["ICHARG"] == 11
    assert incar["LORBIT"] == 11


def test_template_hse_algo_not_fast(si_poscar):
    from pymatgen.core import Structure

    from vasp_incar.system_detector import detect
    from vasp_incar.templates.hse import build

    s = Structure.from_file(str(si_poscar))
    t = detect(si_poscar)
    incar = build(s, t)
    assert incar["LHFCALC"] is True
    assert incar["ALGO"] not in ("Fast", "VeryFast")


def test_template_scan_no_gga(si_poscar):
    from pymatgen.core import Structure

    from vasp_incar.system_detector import detect
    from vasp_incar.templates.scan import build

    s = Structure.from_file(str(si_poscar))
    t = detect(si_poscar)
    incar = build(s, t)
    assert incar["METAGGA"] == "R2SCAN"
    assert incar["LASPH"] is True
    assert "GGA" not in incar
