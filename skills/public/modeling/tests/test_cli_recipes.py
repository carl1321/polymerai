"""
End-to-end regression for B0-P1 builders/transforms.

Drives modeling_cli.py via the in-process API to keep tests fast and CI-friendly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modeling.recipe import Recipe
from modeling.io import write_structure


def _run(tmp_path: Path, recipe_dict: dict, fname: str) -> Path:
    recipe = Recipe.from_dict(recipe_dict)
    structure = recipe.to_pipeline().run()
    out = tmp_path / fname
    write_structure(structure, str(out), format="poscar")
    assert out.exists() and out.stat().st_size > 0
    return out


def test_bulk_pt(tmp_path: Path):
    recipe = {
        "name": "Pt_bulk",
        "steps": [
            {"type": "builder", "name": "bulk",
             "params": {"element": "Pt", "crystalstructure": "fcc",
                        "a": 3.92, "cubic": True}},
        ],
    }
    out = _run(tmp_path, recipe, "Pt.vasp")
    text = out.read_text()
    assert "Pt" in text


def test_supercell_repeat(tmp_path: Path):
    recipe = {
        "name": "Pt_sc",
        "steps": [
            {"type": "builder", "name": "bulk",
             "params": {"element": "Pt", "crystalstructure": "fcc",
                        "a": 3.92, "cubic": True}},
            {"type": "transform", "name": "supercell",
             "params": {"matrix": [2, 2, 2]}},
        ],
    }
    structure = Recipe.from_dict(recipe).to_pipeline().run()
    # 4-atom conventional cell × 8 = 32
    assert structure.n_atoms == 32


def test_supercell_matrix_3x3(tmp_path: Path):
    recipe = {
        "name": "Pt_sc_mat",
        "steps": [
            {"type": "builder", "name": "bulk",
             "params": {"element": "Pt", "crystalstructure": "fcc",
                        "a": 3.92, "cubic": True}},
            {"type": "transform", "name": "supercell",
             "params": {"matrix": [[2, 0, 0], [0, 2, 0], [0, 0, 1]]}},
        ],
    }
    structure = Recipe.from_dict(recipe).to_pipeline().run()
    assert structure.n_atoms == 16


def test_pt111_slab_vacuum(tmp_path: Path):
    recipe = {
        "name": "Pt111_slab",
        "steps": [
            {"type": "builder", "name": "bulk",
             "params": {"element": "Pt", "crystalstructure": "fcc",
                        "a": 3.92, "cubic": True}},
            {"type": "transform", "name": "slab",
             "params": {"miller": [1, 1, 1], "layers": 4, "vacuum": 10.0}},
            {"type": "transform", "name": "supercell",
             "params": {"matrix": [3, 3, 1]}},
            {"type": "transform", "name": "vacuum",
             "params": {"thickness": 15.0}},
        ],
    }
    structure = Recipe.from_dict(recipe).to_pipeline().run()
    # 4 atoms / layer × 4 layers × 9 (3×3 in-plane) = 144
    assert structure.n_atoms == 144
    # vacuum c-axis must be larger than original 4-layer thickness alone
    assert structure.cell[2, 2] > 30.0
    out = tmp_path / "Pt111.vasp"
    write_structure(structure, str(out), format="poscar")
    assert out.exists()


def test_pt111_co_adsorbate(tmp_path: Path):
    recipe = {
        "name": "Pt111_CO",
        "steps": [
            {"type": "builder", "name": "bulk",
             "params": {"element": "Pt", "crystalstructure": "fcc",
                        "a": 3.92, "cubic": True}},
            {"type": "transform", "name": "slab",
             "params": {"miller": [1, 1, 1], "layers": 4}},
            {"type": "transform", "name": "supercell",
             "params": {"matrix": [3, 3, 1]}},
            {"type": "transform", "name": "adsorbate",
             "params": {"molecule": "CO", "site": "top", "height": 2.0}},
            {"type": "transform", "name": "vacuum",
             "params": {"thickness": 15.0}},
        ],
    }
    structure = Recipe.from_dict(recipe).to_pipeline().run()
    # 144 Pt + 2 (C, O)
    assert structure.n_atoms == 146
    assert structure.symbols[-2:] == ["C", "O"]
    out = tmp_path / "Pt111_CO.vasp"
    write_structure(structure, str(out), format="poscar")
    assert out.exists()


def test_box_builder_units(tmp_path: Path):
    """BoxBuilder size 必须按 Å 解释（Recipe schema 约定）。"""
    recipe = {
        "name": "empty_box",
        "steps": [
            {"type": "builder", "name": "box",
             "params": {"size": [25.0, 30.0, 40.0], "pbc": [True, True, True]}},
        ],
    }
    s = Recipe.from_dict(recipe).to_pipeline().run()
    assert s.n_atoms == 0
    assert tuple(s.cell.diagonal()) == (25.0, 30.0, 40.0)


def test_water_box_packmol(tmp_path: Path):
    """Recipe 3：依赖 Packmol；二进制不可用时跳过。"""
    from modeling.tools.packmol_tools import PackmolTools
    if not PackmolTools.is_executable():
        pytest.skip("Packmol binary not executable on this system "
                    "(likely missing runtime DLL on Windows)")

    recipe = {
        "name": "water_box",
        "steps": [
            {"type": "builder", "name": "box",
             "params": {"size": [20.0, 20.0, 20.0], "pbc": [True, True, True]}},
            {"type": "builder", "name": "filler",
             "params": {"molecule": "water", "density": 1.0, "seed": 12345}},
        ],
    }
    s = Recipe.from_dict(recipe).to_pipeline().run()
    assert s.n_atoms > 0
    assert s.n_atoms % 3 == 0  # 整数个水分子
    out = tmp_path / "water.vasp"
    write_structure(s, str(out), format="poscar")
    assert out.exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
