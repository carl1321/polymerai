# Materials Science Tools

## Wrapped Tools

These tools are integrated into the modeling library via wrapper classes.

### ASE (Atomic Simulation Environment)

**Install**: `pip install ase`

| Method | Purpose |
|--------|---------|
| `ASETools.build_bulk(name, crystalstructure, a)` | Create crystal (fcc, bcc, hcp, diamond...) |
| `ASETools.build_molecule(name)` | Create molecule (H2O, CO2, CH4...) |
| `ASETools.build_nanotube(n, m, length, bond)` | Create carbon nanotube |
| `ASETools.read_file(path, format)` | Read any format ASE supports |
| `ASETools.write_file(structure, path, format)` | Write any format ASE supports |
| `ASETools.to_ase_atoms(structure)` | Convert to ASE Atoms |
| `ASETools.from_ase_atoms(atoms)` | Convert from ASE Atoms |

### PyXtal

**Install**: `pip install pyxtal`

| Method | Purpose |
|--------|---------|
| `PyXtalTools.random_crystal(sg, species, nums)` | Random crystal by space group |
| `PyXtalTools.random_crystal_2d(lg, species, nums)` | Random 2D crystal |
| `PyXtalTools.random_molecular_crystal(sg, mols, nums)` | Molecular crystal |
| `PyXtalTools.get_symmetry(structure)` | Symmetry analysis |
| `PyXtalTools.list_wyckoff_positions(sg)` | List Wyckoff sites |

### Atomsk

**Install**: Download from https://atomsk.univ-lille.fr/

| Method | Purpose |
|--------|---------|
| `AtomskTools.create_vacancy(structure, position)` | Vacancy defect |
| `AtomskTools.create_interstitial(structure, element, pos)` | Interstitial atom |
| `AtomskTools.create_substitution(structure, pos, element)` | Substitution |
| `AtomskTools.create_edge_dislocation(structure, pos, b)` | Edge dislocation |
| `AtomskTools.create_screw_dislocation(structure, pos, b)` | Screw dislocation |
| `AtomskTools.create_polycrystal(structure, box, n_grains)` | Polycrystal (Voronoi) |
| `AtomskTools.create_supercell(structure, nx, ny, nz)` | Supercell |

Additional CLI features (not wrapped): crack insertion (`-crack`), strain (`-deform`), Nye tensor calculation, core-shell model support, ferroelectric polarization analysis.

### Packmol

**Install**: `conda install -c conda-forge packmol`

| Method | Purpose |
|--------|---------|
| `PackmolTools.run(requests, output, tolerance)` | Fill molecules in regions |

**Region types**: box, sphere, cylinder (inside/outside)

### Moltemplate

**Install**: `pip install moltemplate`

| Method | Purpose |
|--------|---------|
| `MoltemplateTools.build_system(lt_file)` | Build LAMMPS system from .lt |
| `MoltemplateTools.generate_lt_file(structure, ff)` | Generate .lt template |
| `MoltemplateTools.create_box_lt(size, molecules)` | Create box definition |

**Forcefields**: OPLS-AA, GAFF, GAFF2, MARTINI, TraPPE, COMPASS, DREIDING, AMBER

Additional features (not wrapped): polymer chain growth, automatic angle/dihedral/improper detection, ATB/LigParGen force field import, coarse-grained model support.

### OVITO

**Install**: `pip install ovito`

| Method | Purpose |
|--------|---------|
| `OvitoTools.compute_rdf(structure, cutoff)` | Radial distribution function |
| `OvitoTools.identify_crystal_structure(structure)` | CNA/PTM analysis |
| `OvitoTools.analyze_dislocations(structure, type)` | DXA dislocation analysis |
| `OvitoTools.compute_voronoi(structure)` | Voronoi analysis |
| `OvitoTools.render_image(structure, output)` | Render structure image |

### VASPKIT

**Install**: Download from https://vaspkit.com/

| Method | Task | Purpose |
|--------|------|---------|
| `VaspkitTools.build_heterostructure(s1, s2)` | 804 | Heterostructure (auto lattice match) |
| `VaspkitTools.build_random_alloy(structure, subs)` | 802 | Random substitutional alloy |
| `VaspkitTools.build_surface(structure, miller)` | 803 | Surface by Miller index |
| `VaspkitTools.build_supercell(structure, matrix)` | 401 | Supercell (non-diagonal OK) |
| `VaspkitTools.find_orthogonal_supercell(structure)` | 800 | Find orthogonal cell |
| `VaspkitTools.fix_atoms_by_layers(structure, n)` | 402 | Selective dynamics |

Additional modules (not wrapped): format conversion (1xx), nanotube/nanowire (403/404), defect construction (405), high-symmetry k-path (302-303).

---

## Ecosystem Tools

Not wrapped — use directly via `pip install`.

### Pymatgen (Python Materials Genomics)

**Install**: `pip install pymatgen` | **License**: MIT | https://pymatgen.org/

Structure manipulation, symmetry analysis, phase diagrams, and database interfaces (Materials Project, AFLOW, COD). Strong DFT pre/post-processing support.

| Module | Capabilities |
|--------|-------------|
| `pymatgen.core.surface` | Miller index slabs, adsorption sites |
| `pymatgen.analysis.defects` | Vacancy, interstitial, antisite defects |
| `pymatgen.transformations` | Substitution, ordering, distortion |
| `pymatgen.analysis.interfaces` | Heterostructure interface matching |
| `pymatgen.symmetry` | Space group identification, standardization |
| `pymatgen.io.ase` | `AseAtomsAdaptor` for ASE interop |

### spglib

**Install**: `pip install spglib` | **License**: BSD | https://spglib.readthedocs.io/

Symmetry analysis library (C core with Python bindings).

| Function | Purpose |
|----------|---------|
| `get_spacegroup()` | Space group identification |
| `get_symmetry()` | Symmetry operation search |
| `find_primitive()` | Primitive cell finding |
| `standardize_cell()` | Conventional cell standardization |
| `get_symmetry_dataset()` | Wyckoff positions |
| `get_ir_reciprocal_mesh()` | Irreducible k-point mesh |

### SeeK-path

**Install**: `pip install seekpath` | **License**: MIT | https://seekpath.materialscloud.io/

Determines Brillouin zone high-symmetry points and generates band structure k-paths based on crystallographic conventions. Integrates with spglib. Also provides an online visualization tool.

### VMD + TopoTools

**Install**: Download from https://www.ks.uiuc.edu/Research/vmd/ | **License**: Free for academic use

| Feature | Details |
|---------|---------|
| Topology editing | Create/delete bonds, angles, dihedrals |
| Molecular merging | Combine multiple molecules into one system |
| Replication | Unit cell duplication for large systems |
| Format conversion | Output LAMMPS DATA files |
| Membrane Builder | `package require membrane` for lipid bilayers |
| Solvate Plugin | `package require solvate` for solvation boxes |

### CHARMM-GUI

**URL**: https://charmm-gui.org/ (web service) | **License**: Free for academic use

| Module | Capabilities |
|--------|-------------|
| Membrane Builder | 670+ lipid types |
| Solution Builder | Ionic strength, pH control |
| Glycan Modeler | Glycosylated protein construction |
| Ligand Reader | Small molecule parameterization |
| Martini Maker | Coarse-grained models |

**Output formats**: CHARMM, NAMD, GROMACS, AMBER, OpenMM, LAMMPS, Desmond

### MDAnalysis

**Install**: `pip install MDAnalysis` | **License**: LGPL | https://www.mdanalysis.org/

Trajectory analysis library supporting GROMACS, AMBER, NAMD, LAMMPS formats. Provides atom selection language, RDF/RMSD/hydrogen-bond analysis, trajectory merging/slicing/alignment, and PBC handling.

---

## Feature Comparison

### Structure Creation

| Feature | ASE | Pymatgen | Atomsk | Packmol |
|---------|-----|----------|--------|---------|
| Crystal | Yes | Yes | Yes | - |
| Molecule | Yes | - | - | - |
| Surface/slab | Yes | Yes | Yes | - |
| Nanotube | Yes | - | - | - |
| Filling/solvation | - | - | - | Yes |

### Structure Manipulation

| Feature | ASE | Pymatgen | Atomsk | VESTA | VMD |
|---------|-----|----------|--------|-------|-----|
| Supercell | Yes | Yes | Yes | Yes | Yes |
| Cutting | Yes | Yes | Yes | - | - |
| Defects | - | Yes | Yes | - | - |
| Doping/substitution | Yes | Yes | Yes | Yes | - |
| Dislocations | - | - | Yes | - | - |
| Polycrystal | - | - | Yes | - | - |

### Symmetry Analysis

| Feature | spglib | Pymatgen | VESTA | seekpath |
|---------|--------|----------|-------|----------|
| Space group | Yes | Yes | Yes | Yes |
| Primitive/conventional cell | Yes | Yes | - | Yes |
| k-path | - | Yes | - | Yes |
| Wyckoff positions | Yes | Yes | - | - |

---

## Tool Selection Guide

### By Task

| Task | Recommended Tools |
|------|------------------|
| Quick crystal creation | ASETools, AtomskTools |
| Surface adsorption modeling | Pymatgen, ASETools |
| Defect calculation modeling | Pymatgen, AtomskTools |
| Dislocation/grain boundary | AtomskTools |
| Heterostructure | VaspkitTools, Pymatgen |
| Protein solvation | CHARMM-GUI, VMD |
| Membrane systems | CHARMM-GUI |
| Polymer systems | MoltemplateTools |
| Band structure k-path | seekpath, Pymatgen |
| Random crystal generation | PyXtalTools |
| Structure analysis/visualization | OvitoTools |

### By Scale

```
Atom count:   100-1000        1000-10^6        >10^6
             +---------------+----------------+---------------+
Tools:       | ASE           | Packmol        | Moltemplate   |
             | Pymatgen      | Moltemplate    | VMD           |
             | Atomsk        | CHARMM-GUI     |               |
             | VESTA         | VMD            |               |
             +---------------+----------------+---------------+
Domain:        DFT             MD               MD
```
