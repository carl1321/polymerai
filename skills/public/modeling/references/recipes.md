# Common Modeling Recipes

Ready-to-use Recipe JSON templates. Load with:

```bash
python modeling_cli.py run <recipe.json> -o <output> [--validate]
```

Output path resolution: `-o` argument > `metadata.output.filename` > error.
Format detection: extension by default, override with `--format` or `metadata.output.format`.

Registered builders (`list builders`): `bulk`, `box`, `molecule`, `filler`.
Registered transforms (`list transforms`): `slab`, `supercell`, `defect`, `adsorbate`, `vacuum`, `rotate`, `translate`, `mirror`.

---

## Recipe 1 — Metal slab with vacuum (Pt(111))  ✅ verified (B0-P1)

Use when: need a clean FCC/BCC/HCP metal surface for DFT.
Key params: `miller` = surface plane; `layers` = slab thickness; `vacuum.thickness` ≥ 12 Å to decouple periodic images.

```json
{
  "name": "Pt111_slab",
  "steps": [
    {"type": "builder",   "name": "bulk",      "params": {"element": "Pt"}},
    {"type": "transform", "name": "slab",      "params": {"miller": [1, 1, 1], "layers": 4}},
    {"type": "transform", "name": "supercell", "params": {"matrix": [3, 3, 1]}},
    {"type": "transform", "name": "vacuum",    "params": {"thickness": 15.0}}
  ],
  "metadata": {
    "output": {"format": "poscar", "filename": "Pt111.vasp"}
  }
}
```

## Recipe 2 — Surface adsorption (CO on Pt(111))  ✅ verified (B0-P2)

Use when: placing a small adsorbate on a metal surface.
Key params: `molecule` = adsorbate name (must be known or loadable); `site` = `top`/`bridge`/`fcc`/`hcp`; `height` in Å above the surface.

```json
{
  "name": "Pt111_CO",
  "steps": [
    {"type": "builder",   "name": "bulk",      "params": {"element": "Pt"}},
    {"type": "transform", "name": "slab",      "params": {"miller": [1, 1, 1], "layers": 4}},
    {"type": "transform", "name": "supercell", "params": {"matrix": [3, 3, 1]}},
    {"type": "transform", "name": "adsorbate", "params": {"molecule": "CO", "site": "top", "height": 2.0}},
    {"type": "transform", "name": "vacuum",    "params": {"thickness": 15.0}}
  ],
  "metadata": {
    "output": {"format": "poscar", "filename": "Pt111_CO.vasp"}
  }
}
```

## Recipe 3 — Solvent box (pure water)  ✅ verified (B0-P2, requires Packmol)

Use when: generating a starting configuration for classical MD.
Key params: `box.size` in Å; `filler.density` in g/cm³; Packmol must be available (`modeling_cli.py tools`).

```json
{
  "name": "water_box",
  "steps": [
    {"type": "builder", "name": "box",    "params": {"size": [30.0, 30.0, 30.0], "pbc": [true, true, true]}},
    {"type": "builder", "name": "filler", "params": {"molecule": "water", "density": 1.0}}
  ],
  "metadata": {
    "output": {"format": "gro", "filename": "water.gro"}
  }
}
```

## Recipe 4 — Defect supercell (Cu vacancy)

Use when: computing point-defect formation energies.
Key params: `defect.type` = `vacancy` / `substitution` / `interstitial`; `site` = atom index (use 0 if unknown; check with visualizer afterwards).

```json
{
  "name": "Cu_vacancy",
  "steps": [
    {"type": "builder",   "name": "bulk",      "params": {"element": "Cu"}},
    {"type": "transform", "name": "supercell", "params": {"matrix": [3, 3, 3]}},
    {"type": "transform", "name": "defect",    "params": {"type": "vacancy", "site": 0}}
  ],
  "metadata": {
    "output": {"format": "poscar", "filename": "Cu_vacancy.vasp"}
  }
}
```

## Recipe 5 — Single-molecule coordinate export to Gaussian

Use when: preparing coordinates for a Gaussian calculation. This skill **only writes
coordinates** — the route section, basis set, charge, and multiplicity are handled
by the `gaussian-agent` skill. Call that skill after this recipe finishes.

```json
{
  "name": "ethanol_coords",
  "steps": [
    {"type": "builder", "name": "molecule", "params": {"name": "ethanol"}}
  ],
  "metadata": {
    "output": {"format": "gaussian", "filename": "ethanol.gjf"}
  }
}
```

## Recipe 6 — Solvated surface (SiO₂ + water interface)

Use when: simulating a solid/liquid interface. Requires a starting SiO₂ CIF on disk.
Key params: `filler.region` restricts solvent to a sub-volume; `vacuum.thickness` creates head-space above the water.

```json
{
  "name": "SiO2_water_interface",
  "steps": [
    {"type": "builder",   "name": "molecule",  "params": {"name": "SiO2.cif", "source": "file"}},
    {"type": "transform", "name": "slab",      "params": {"miller": [0, 0, 1], "layers": 6}},
    {"type": "transform", "name": "supercell", "params": {"matrix": [5, 5, 1]}},
    {"type": "builder",   "name": "filler",    "params": {"molecule": "water", "density": 0.9, "region": "above_slab"}},
    {"type": "transform", "name": "vacuum",    "params": {"thickness": 20.0}}
  ],
  "metadata": {
    "output": {"format": "lammps", "filename": "sio2_water.data"}
  }
}
```

---

## Tips

- **Unknown transform/builder?** Run `python modeling_cli.py list transforms` /
  `list builders` to see the current registry. Recipe fields that reference
  unregistered names will fail at `Recipe.to_pipeline()`.
- **Missing backend tool?** Run `python modeling_cli.py tools`. `Packmol` is
  required for `filler`; `ASE` is required for most operations; `Atomsk`/`VASPKIT`
  are optional fallbacks.
- **Validate before trusting the output** — add `--validate` to the `run` command,
  or invoke `python modeling_cli.py validate <file> --level 2` after.
