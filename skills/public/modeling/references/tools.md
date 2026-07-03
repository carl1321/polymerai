# Modeling Tools Reference — Index

## Tool Availability Check

```python
from modeling.tools import check_tools_availability
status = check_tools_availability()
# {'ASE': True, 'Packmol': False, 'PyXtal': True, ...}
```

Always check before using a tool. If unavailable, suggest installation or use fallback.

## I/O Formats

| Format | Read | Write | Dependency |
|--------|------|-------|-----------|
| PDB | Yes | Yes | None |
| XYZ | Yes | Yes | None |
| Gaussian .gjf/.com | Yes | Yes | None |
| CIF | Yes | Yes | ASE |
| POSCAR/VASP | Yes | Yes | ASE |
| LAMMPS data | Yes | Yes | ASE |
| GRO | Yes | Yes | ASE |

### Gaussian I/O Details

**Writing .gjf files** — pass Gaussian parameters via `Structure.properties`:
```python
structure.properties = {
    "gaussian_route": "# MP2/aug-cc-pVDZ opt=(ts,calcfc) freq",
    "charge": -1,
    "multiplicity": 1,
    "link0": {"chk": "mol.chk", "nproc": "16", "mem": "16GB"},
    "title": "TS structure",
    "basis_extra": "",  # optional Gen/GenECP section
}
write_structure(structure, "output.gjf")
```

**Reading .gjf files** — Gaussian parameters are parsed into `Structure.properties`:
```python
structure = read_structure("input.gjf")
charge = structure.properties["charge"]
route = structure.properties["gaussian_route"]
```

## Transforms Reference

| Transform | Purpose | Example |
|-----------|---------|---------|
| `SlabTransform(miller, layers, vacuum)` | Cut surface | `SlabTransform(miller=(1,1,1), layers=4)` |
| `SupercellTransform(matrix)` | Build supercell | `SupercellTransform(matrix=(3,3,1))` |
| `DefectTransform(defect_type, site)` | Create defects | `DefectTransform(defect_type="vacancy", site=0)` |
| `AdsorbateTransform(molecule, site)` | Add adsorbate | `AdsorbateTransform(molecule="CO", site="top")` |
| `VacuumTransform(thickness, axis)` | Add vacuum | `VacuumTransform(thickness=15.0)` |
| `RotateTransform(angle, axis)` | Rotate | `RotateTransform(angle=45, axis="z")` |
| `TranslateTransform(vector)` | Translate | `TranslateTransform(vector=(0,0,5))` |
| `MirrorTransform(plane)` | Mirror | `MirrorTransform(plane="xy")` |
| `SaturateTransform(method)` | Surface saturation | `SaturateTransform(method="hydroxylate")` |
| `CarveTransform(shape, radius)` | Carve pore/hole | `CarveTransform(shape="cylinder", radius=1.5)` |

## Builders Reference

| Builder | Purpose | Example |
|---------|---------|---------|
| `BoxBuilder.create_box_info(size, pbc)` | Empty box | `BoxBuilder.create_box_info(5.0)` |
| `BulkBuilder().build(element)` | Crystal bulk | `BulkBuilder().build(element="Pt")` |
| `MoleculeBuilder().build(name)` | Molecule | `MoleculeBuilder().build(name="water")` |
| `Filler().build(requests, box)` | Fill molecules | See Packmol integration |

---

For detailed tool APIs, see `tools-materials.md` (materials science) and `tools-qc.md` (quantum chemistry).
