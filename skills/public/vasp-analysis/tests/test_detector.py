"""Detector unit tests for vasp-analysis."""
from __future__ import annotations

from pathlib import Path

from vasp_analysis.detector import detect


def test_unknown_empty_dir(tmp_path):
    r = detect(tmp_path)
    assert r.calc_type == "unknown"


def test_band_line_mode(tmp_path):
    (tmp_path / "KPOINTS").write_text(
        "Line-mode k-points\n20\nLine-mode\nreciprocal\n"
        "0.0 0.0 0.0 GAMMA\n0.5 0.0 0.0 X\n"
    )
    (tmp_path / "INCAR").write_text("IBRION = -1\n")
    r = detect(tmp_path)
    assert r.calc_type == "band"


def test_phonon_from_forcesets(tmp_path):
    (tmp_path / "FORCE_SETS").write_text("dummy")
    r = detect(tmp_path)
    assert r.calc_type == "phonon"


def test_elastic_outcar(tmp_path):
    (tmp_path / "OUTCAR").write_text("something\n TOTAL ELASTIC MODULI (kBar)\n")
    r = detect(tmp_path)
    assert r.calc_type == "elastic"
