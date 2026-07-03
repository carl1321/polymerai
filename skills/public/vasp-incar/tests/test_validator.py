"""Validator unit tests — one test per conflict rule family."""
from __future__ import annotations

import pytest

from vasp_incar.validator import validate


def _fire(incar, context=None):
    return {v.rule_id for v in validate(incar, context=context or {})}


def test_ismear_m5_insufficient_kpoints_fires():
    assert "ISMEAR_M5_INSUFFICIENT_KPTS" in _fire(
        {"ISMEAR": -5}, context={"n_kpoints": 2})


def test_ismear_m5_relax_fires():
    assert "ISMEAR_M5_RELAX" in _fire({"ISMEAR": -5, "NSW": 50})


def test_hse_algo_fast_fires():
    assert "HSE_ALGO_FAST" in _fire({"LHFCALC": True, "ALGO": "Fast"})


def test_metagga_needs_lasph_fires():
    assert "METAGGA_NEEDS_LASPH" in _fire({"METAGGA": "R2SCAN", "LASPH": False})


def test_metagga_gga_both_fires():
    assert "METAGGA_GGA_BOTH" in _fire(
        {"METAGGA": "R2SCAN", "GGA": "PE", "LASPH": True})


def test_ldau_without_lmaxmix_fires():
    assert "LDAU_WITHOUT_LMAXMIX" in _fire({"LDAU": True, "LMAXMIX": 2})


def test_ediffg_positive_warning():
    assert "EDIFFG_POSITIVE_FORCES" in _fire({"EDIFFG": 0.01})


def test_ediff_loose_for_phonon_fires():
    assert "EDIFF_LOOSE_FOR_PHONON" in _fire({"IBRION": 8, "EDIFF": 1e-5})


def test_nsw_without_ibrion_fires():
    assert "NSW_WITHOUT_IBRION" in _fire({"NSW": 30, "IBRION": -1})


def test_prec_low_fires():
    assert "PREC_LOW_PRODUCTION" in _fire({"PREC": "Low"})


def test_encut_too_low_fires():
    assert "ENCUT_TOO_LOW" in _fire({"ENCUT": 250})


def test_lsorbit_requires_lmaxmix_fires():
    assert "LSORBIT_REQUIRES_LMAXMIX" in _fire({"LSORBIT": True, "LMAXMIX": 2})


def test_nupdown_without_ispin_fires():
    assert "NUPDOWN_WITHOUT_ISPIN" in _fire({"NUPDOWN": 2, "ISPIN": 1})


def test_clean_incar_no_errors():
    incar = {
        "ENCUT": 520, "ISMEAR": 0, "SIGMA": 0.05, "IBRION": 2,
        "NSW": 100, "EDIFF": 1e-6, "EDIFFG": -0.01, "PREC": "Accurate",
        "ALGO": "Normal", "LREAL": False,
    }
    errors = [v for v in validate(incar, context={"n_atoms": 20, "n_kpoints": 8})
              if v.severity == "error"]
    assert errors == []
