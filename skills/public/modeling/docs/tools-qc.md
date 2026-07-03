# Quantum Chemistry Tools

## Wrapped Tools

These tools are integrated into the modeling library via wrapper classes.

### BSE (Basis Set Exchange)

**Install**: `pip install basis_set_exchange`

| Method | Purpose |
|--------|---------|
| `BSETools.get_basis(name, elements, fmt)` | Get basis set definition text |
| `BSETools.get_basis_for_structure(structure, name, fmt)` | Auto-detect elements from structure |
| `BSETools.list_basis_sets(elements)` | List available basis sets |
| `BSETools.get_references(name)` | Get citations for a basis set |
| `BSETools.get_ecp(name, elements, fmt)` | Get pseudopotential (ECP) definitions |

**Output formats**: gaussian94, nwchem, orca, psi4, molpro, gamess, turbomole, cfour, dalton

**Common basis sets**: STO-3G, 6-31G\*, 6-311+G\*\*, cc-pVDZ, aug-cc-pVDZ, def2-SVP, def2-TZVP, LANL2DZ

---

## Ecosystem Tools

Not wrapped — use directly via `pip install`.

### RDKit

**Install**: `conda install -c conda-forge rdkit` | **License**: BSD | https://www.rdkit.org/

Cheminformatics toolkit for molecular modeling from SMILES/InChI representations.

| Feature | Details |
|---------|---------|
| SMILES/InChI parsing | String to molecule object conversion |
| 3D coordinate generation | ETKDG algorithm |
| Conformer search | Multi-conformer generation and optimization |
| Force field optimization | MMFF94, UFF |
| Substructure search | SMARTS pattern matching |
| Fingerprints | Morgan, MACCS, RDK |

```python
from rdkit import Chem
from rdkit.Chem import AllChem

mol = Chem.MolFromSmiles('CCO')
mol = Chem.AddHs(mol)
AllChem.EmbedMolecule(mol, AllChem.ETKDG())
AllChem.MMFFOptimizeMolecule(mol)

# Conformer search
confs = AllChem.EmbedMultipleConfs(mol, numConfs=50)
```

### Open Babel

**Install**: `conda install -c conda-forge openbabel` | **License**: GPL | http://openbabel.org/

Format conversion hub supporting 100+ chemical file formats, with 3D coordinate generation and conformer search.

| Feature | Details |
|---------|---------|
| Format conversion | 100+ chemical file formats |
| 3D coordinate generation | `--gen3d` |
| Conformer generation | Confab module |
| Force field optimization | MMFF94, UFF, GAFF |
| Protonation | pH-dependent protonation states |
| Symmetry analysis | Point group identification |

```bash
# SMILES to XYZ with optimization
obabel -:"CCO" -oxyz --gen3d --ff MMFF94 -O ethanol.xyz

# Conformer search
obabel input.mol2 -O conformers.sdf --conformer --nconf 100
```

### Avogadro 2

**Install**: Download from https://www.openchemistry.org/projects/avogadro2/ | **License**: BSD

GUI-based molecular editor with fragment library, ligand attachment, built-in force field optimization, and input file generation for Gaussian, ORCA, NWChem, Psi4. Useful for visual construction and orbital/vibration visualization.

### xTB + CREST

**Install**: `conda install -c conda-forge xtb crest` | **License**: LGPL | https://xtb-docs.readthedocs.io/

Fast semi-empirical methods (GFN2-xTB) for geometry optimization, vibrational analysis, thermochemistry, and implicit solvation (GBSA/ALPB).

| xTB Feature | Details |
|-------------|---------|
| Fast optimization | GFN2-xTB semi-empirical method |
| Vibrational analysis | Numerical Hessian |
| Thermochemistry | Free energy corrections |
| Implicit solvation | GBSA/ALPB models |

| CREST Feature | Details |
|---------------|---------|
| Conformer search | Metadynamics-based global search |
| Tautomer search | Proton migration isomers |
| Reaction path | Nanoreactor exploration |
| TS guessing | Automatic transition state location |

```bash
# Conformer search
crest molecule.xyz --gfn2

# Protonation state search
crest molecule.xyz --protonate
```

### cclib

**Install**: `pip install cclib` | **License**: LGPL | https://cclib.github.io/

Parser for quantum chemistry output files. Supports Gaussian, ORCA, NWChem, Psi4, Q-Chem, GAMESS, Molpro, Turbomole, ADF, Dalton, xTB.

| Parsed Data | Details |
|-------------|---------|
| Coordinates | Optimization trajectory |
| Energies | SCF, correlation, total energy |
| Orbitals | Coefficients, energy levels, occupancies |
| Vibrations | Frequencies, IR intensities |
| Excited states | TD-DFT energies, oscillator strengths |
| Population analysis | Mulliken, NBO |

### chemcoord

*Upcoming integration.* Internal coordinate (Z-matrix) manipulation library for systematic geometry modifications.

---

## Feature Comparison — Molecular Modeling

| Feature | RDKit | OpenBabel | Avogadro | xTB/CREST |
|---------|-------|-----------|----------|-----------|
| SMILES parsing | Yes | Yes | - | - |
| 3D generation | Yes | Yes | Yes | - |
| Conformer search | Yes | Yes | - | Yes |
| Transition state | - | - | - | Yes |
| Force field optimization | Yes | Yes | Yes | Yes |

---

## Tool Selection Guide

### By Task

| Task | Recommended Tools |
|------|------------------|
| SMILES/InChI to 3D structure | RDKit, Open Babel |
| Conformer search (small molecule) | CREST, RDKit |
| Conformer search (quick, large molecule) | RDKit |
| Transition state guessing | CREST |
| Quick geometry pre-optimization | xTB |
| Basis set lookup | BSETools |
| QM output parsing | cclib |
| Format conversion (molecular) | Open Babel |
| Visual molecular editing | Avogadro |
| Force field pre-optimization | RDKit (MMFF94), Open Babel (MMFF94/UFF/GAFF) |

### By Scale

```
Atom count:   1-50           50-200          200-500
             +---------------+---------------+---------------+
Tools:       | RDKit         | xTB           | xTB           |
             | OpenBabel     | RDKit         | GFN-FF        |
             | Avogadro      | CREST         |               |
             +---------------+---------------+---------------+
Method:       High-level QM   DFT / xTB       xTB / semi-emp
```

---

## Interoperability

### Format Conversion Paths

```
SMILES ←──→ RDKit ←──→ Open Babel
  ↓            ↓            ↓
Avogadro    .mol/.sdf    100+ formats
  ↓            ↓
Gaussian     ORCA / NWChem / Psi4 input
  ↓
cclib (output parsing)
```

### Python Ecosystem Integration

```python
# RDKit → file → Open Babel
from rdkit import Chem
Chem.MolToMolFile(mol, 'molecule.mol')

# Open Babel via pybel
import pybel
mol = next(pybel.readfile('mol', 'molecule.mol'))
mol.write('xyz', 'molecule.xyz', overwrite=True)

# cclib — parse QM output
import cclib
data = cclib.io.ccread('gaussian_output.log')
coords = data.atomcoords[-1]  # final geometry
energies = data.scfenergies
```
