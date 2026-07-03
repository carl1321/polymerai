# Modeling System Design Document

*Version: 0.8 | Updated: 2026-04-20*

---

## 1. System Overview

### 1.1 Goals

Build a natural-language-driven atomic-scale modeling system supporting MD and DFT
structure generation. Quantum-chemistry input preparation (Gaussian route, basis
sets, charge/multiplicity) is out of scope and delegated to the `gaussian-agent`
skill.

### 1.2 Core Principles

- **Natural language driven** — users describe modeling needs in plain language.
- **Recipe-first LLM interface** — LLM emits a Recipe JSON; the CLI executes it.
  Hand-written Python against the `modeling` package is for library consumers, not
  for the skill runtime.
- **Auto-validation** — multi-level validation after construction.
- **Tool abstraction** — unified wrappers over external tools.
- **Extensible** — new open-source tools integrate through standard interfaces.

### 1.3 Scope Boundary

This skill handles **atomic coordinate generation** only. Coordinate export to
`.gjf` / `.com` is supported, but route, basis set, charge, and multiplicity are
not set by this skill.

| Out of Scope | Responsible Skill |
|---|---|
| Basis set selection, Gaussian route, charge/multiplicity | `gaussian-agent` |
| k-points, pseudopotentials, INCAR | `vasp-agent` / `potcar` |
| Force field parameterization, topology | MD/Force Field skill |
| Job management, workflows | Workflow skill |
| Post-processing / analysis | Analysis skill |

---

## 2. Architecture

```
User Layer          NL description / file upload (.pdb .xyz .cif ...)
       |
Skill Layer         SKILL.md guides the LLM to author a Recipe JSON
       |
CLI Layer           modeling_cli.py {run, convert, validate, tools, list}
       |
Recipe Layer        JSON operation sequence (serializable, editable)
       |
Pipeline Layer      Sequential Builder/Transform execution (preview, rollback)
       |
Build Layer         Builders (create) + Transforms (modify) + Assembler (merge)
       |
Validator Layer     L1 Geometry → L2 Chemistry → L3 Physics
       |
Output Layer        Structure files + validation report
```

The **Skill Layer** and **CLI Layer** are new in v0.8. Earlier designs had the
LLM call the Python API directly; this was replaced because the multi-line import
+ instantiation pattern was error-prone. The Recipe JSON is now the sanctioned
interaction surface.

### Data Flow (example: Pt(111)+CO)

1. User: "Adsorb CO on Pt(111)."
2. LLM parses → Recipe JSON (`bulk → slab → supercell → adsorbate → vacuum`).
3. LLM runs `python modeling_cli.py run pt111_co.json -o out.poscar --validate`.
4. CLI loads Recipe → Pipeline → Structure → writer → validators.
5. Output: `out.poscar` + validation summary.

---

## 3. Core Data Structure

```python
@dataclass
class Structure:
    positions: np.ndarray          # (N,3) in Angstrom
    symbols: List[str]
    cell: Optional[np.ndarray]     # (3,3) or (3,)
    pbc: List[bool]

    # Optional
    charges: Optional[np.ndarray]
    bonds: Optional[List[tuple]]
    selective_dynamics: Optional[np.ndarray]  # (N,3) bool, VASP
    atom_types: Optional[List[str]]           # force-field types, LAMMPS
    residues: Optional[List[str]]             # PDB/GRO
    velocities: Optional[np.ndarray]          # LAMMPS/GRO

    # Metadata
    name: str
    source_file: str
    properties: Dict[str, Any]     # extensible; builders/transforms attach
                                   # backend-specific metadata here
```

`properties` is an ASE-style extensible bag. It may carry backend state (e.g.,
Packmol region hints) but should not carry QM calculation parameters — those
belong to the `gaussian-agent` skill's own data path.

---

## 4. Core Modules

### 4.1 Tools

External tool wrappers under `tools/`.

| Tool | Key Capabilities | Install |
|---|---|---|
| ASE | Structure I/O, bulk/molecule/nanotube build, slab, supercell | `pip install ase` |
| Packmol | Molecular packing | `conda install -c conda-forge packmol` |
| PyXtal | Random crystal generation (3D, 2D, molecular) | `pip install pyxtal` |
| Atomsk | Point defects, dislocations, grain boundaries, polycrystal | binary download |
| Moltemplate | LAMMPS topology from .lt templates | `pip install moltemplate` |
| OVITO | RDF, CNA/PTM, DXA, Voronoi, rendering | `pip install ovito` |
| VASPKIT | Heterostructure, random alloy, surface, orthogonal supercell | binary download |

**Internal-only tools** (kept in the package but not exposed by `SKILL.md`):
`BSETools` (basis sets) and `XTBTools` (semi-empirical pre-check) — these are
QM-adjacent and the skill layer no longer guides the LLM toward them. They remain
callable from Python if a downstream consumer needs them.

**Tool selection guide** for modeling operations:

| Task | Primary | Alternative |
|---|---|---|
| Crystal structure | ASE | PyXtal |
| Random crystal | PyXtal | — |
| Surface slab | ASE | VASPKIT, Atomsk |
| Supercell | ASE | VASPKIT, Atomsk |
| Point defects | Atomsk | Pymatgen |
| Dislocations | Atomsk | — |
| Grain boundary / polycrystal | Atomsk | — |
| Heterostructure | VASPKIT | manual |
| Random alloy | VASPKIT | Pymatgen |
| Molecular packing | Packmol | — |
| LAMMPS topology | Moltemplate | fftool |
| Structure analysis | OVITO | MDAnalysis |

### 4.2 Builders

Create structures from scratch. Signature: `build(**params) -> Structure`.

| Builder | Purpose | Backend |
|---|---|---|
| BoxBuilder | Empty simulation box | pure Python |
| BulkBuilder | Crystal structures | ASE |
| MoleculeBuilder | Molecules | ASE |
| Filler | Region packing | Packmol |
| Assembler | Merge components | pure Python |
| CombinatorialBuilder | Exhaustive substituent enumeration | RDKit (planned) |

### 4.3 Transforms

Modify existing structures. Signature: `apply(structure, **params) -> Structure`.

| Transform | Purpose | Backend |
|---|---|---|
| SlabTransform | Cut surface slab | ASE/Pymatgen |
| SupercellTransform | Build supercell | ASE |
| DefectTransform | Point defects | Pymatgen |
| AdsorbateTransform | Add adsorbate | ASE |
| VacuumTransform | Add vacuum layer | ASE |
| RotateTransform | Rotate structure | pure Python |
| TranslateTransform | Translate structure | pure Python |
| MirrorTransform | Mirror structure | pure Python |

### 4.4 Validators

| Level | Content | Time | Required |
|---|---|---|---|
| L1 Geometry | Overlap, boundary, periodic image | ~1s | Yes |
| L2 Chemistry | Bond length, coordination, charge balance | ~2s | Recommended |
| L3 Physics | Density, energy pre-check | ~10s | Optional |

### 4.5 I/O

| Format | Read | Write | Backend |
|---|---|---|---|
| PDB | Y | Y | pure Python |
| XYZ | Y | Y | pure Python |
| CIF | Y | Y | ASE |
| POSCAR | Y | Y | ASE |
| LAMMPS data | Y | Y | ASE |
| GRO | Y | Y | ASE |
| Gaussian .gjf/.com | Y | Y (coords only) | built-in |

Gaussian output is **coordinates only** — no route, basis, charge, or
multiplicity. A downstream `gaussian-agent` invocation completes the input file.

### 4.6 Pipeline & Recipe

**Recipe** — JSON operation sequence, serializable, LLM-generatable:

```json
{
  "name": "Pt111_CO_adsorption",
  "steps": [
    {"type": "builder",   "name": "bulk",      "params": {"element": "Pt"}},
    {"type": "transform", "name": "slab",      "params": {"miller": [1,1,1], "layers": 4}},
    {"type": "transform", "name": "supercell", "params": {"matrix": [3,3,1]}},
    {"type": "transform", "name": "adsorbate", "params": {"molecule": "CO", "site": "top"}},
    {"type": "transform", "name": "vacuum",    "params": {"thickness": 15.0}}
  ],
  "metadata": {
    "output": {"format": "poscar", "filename": "Pt111_CO.vasp"}
  }
}
```

**Pipeline** — executor with `run()`, `run_next()`, `preview()`, `rollback()`,
`to_recipe()`, `from_recipe()`.

### 4.7 CLI (`modeling_cli.py`)

Thin argparse wrapper exposing five subcommands. Single-step operations are
expressed as one-step Recipes rather than dedicated subcommands; adding more
subcommands was explicitly rejected — one JSON schema is easier for the LLM to
produce than twenty argparse flag sets.

| Subcommand | Purpose |
|---|---|
| `run <recipe.json>` | Execute a Recipe and write output (optional `--validate`) |
| `convert -i <in> -o <out>` | Convert between structure formats |
| `validate <file> --level {1,2,3}` | Validate a structure file |
| `tools` | Report backend tool availability |
| `list {builders,transforms}` | Dump the Recipe registry |

See `references/recipes.md` for ready-to-use Recipe templates.

---

## 5. Extensibility Templates

### 5.1 New Builder

```python
from modeling.builders.base import BaseBuilder

class MyBuilder(BaseBuilder):
    name = "my_builder"
    required_params = ["param1"]
    default_params = {"param2": "default"}

    def build(self, **params) -> Structure:
        ...
```

Register it in `Recipe._get_builder_registry()` so Recipe JSON can reference it.

### 5.2 New Transform

```python
from modeling.transforms.base import BaseTransform

class MyTransform(BaseTransform):
    name = "my_transform"

    def apply(self, structure: Structure, **params) -> Structure:
        ...

    def to_dict(self) -> dict:
        ...
```

Register it in `Recipe._get_transform_registry()`.

### 5.3 New Validator

```python
from modeling.validators.base import BaseValidator

class MyValidator(BaseValidator):
    def validate(self, structure: Structure) -> ValidationResult:
        ...
```

---

## 6. Conventions

### 6.1 Units

- Positions: Angstrom
- Cell: Angstrom
- Energies (when present): eV

### 6.2 User Interaction Principles (SKILL.md)

- **Identify conflicts** — state which parameters contradict, with quantified impact.
- **Provide options** — 2-3 actionable choices per conflict.
- **Ask for ambiguous params** — e.g., "1% concentration" → mol/L or wt%?
- **Collect until complete** — geometry, composition, no conflicts, output format
  all confirmed before building.

---

## 7. Directory Structure

```
modeling/                       # single source; .claude/skills/modeling is a junction
├── SKILL.md                    # LLM operating manual (Recipe + CLI)
├── modeling_cli.py             # CLI entry
├── pyproject.toml
├── modeling/                   # Python package
│   ├── __init__.py
│   ├── session.py
│   ├── pipeline.py
│   ├── recipe.py
│   ├── core/                   # Structure, Molecule, Box, Component
│   ├── builders/               # bulk, box, molecule, filler, assembler, sn2_ts, ...
│   ├── transforms/             # slab, supercell, defect, adsorbate, vacuum, ...
│   ├── validators/             # geometry, chemistry, physics
│   ├── io/                     # readers, writers
│   ├── tools/                  # ase, packmol, pyxtal, atomsk, moltemplate, ovito,
│   │                           # vaspkit, bse, xtb (last two internal-only)
│   └── resources/              # built-in molecule library
├── references/                 # surface-facing docs loaded with the skill
│   ├── design.md               # this document
│   ├── recipes.md
│   ├── tools.md
│   ├── tools-materials.md
│   └── molecules.md
└── docs/                       # internal docs not loaded by the skill
    ├── tools-qc.md             # legacy QM tool notes
    └── ts-builder.md           # SN2 TS builder notes
```

---

## 8. Roadmap

### Active

| Scope | Status | Notes |
|---|---|---|
| Skill layer refactor (Recipe + CLI) | ✅ v0.8 | Landed 2026-04 |
| Scope alignment with `gaussian-agent` | ✅ v0.8 | QM triggers moved out |
| Builder/Transform backing implementations | 🔄 IN PROGRESS | Many are still placeholders; see `docs/` |
| `references/decision-rules.md` (domain heuristics) | Planned | Vacuum thickness, slab layers, water density guidance |

### Deferred / Delegated

| Scope | Decision |
|---|---|
| Gaussian I/O with route/basis | Delegated to `gaussian-agent` skill |
| Fragment library, combinatorial builder (QM focus) | Delegated / lower priority |
| TS automation (autodE, geomeTRIC, Sella, pysisyphus) | Out of scope for this skill |
| Reaction paths (NEB/IRC) | Out of scope |
| ML-potential pre-screening (xTB, TorchANI, AIMNet2) | Out of scope |

### Long-term

| Scope | Notes |
|---|---|
| Phase 3 I/O breadth | CIF/POSCAR/LAMMPS/GRO via ASE — partial |
| Phase 5 advanced | OVITO visualization, batch modeling, recipe library |
| Phase 6 coarse-grained | AA↔CG mapping, MARTINI, martinize2 |

### Dependencies

| Dependency | Required | Install |
|---|---|---|
| numpy | Yes | `pip install numpy` |
| ASE | Optional | `pip install ase` |
| Packmol | Optional | `conda install -c conda-forge packmol` |
| Pymatgen | Optional | `pip install pymatgen` |
| PyXtal | Optional | `pip install pyxtal` |
| Atomsk | Optional | binary download |
| Moltemplate | Optional | `pip install moltemplate` |
| OVITO | Optional | `pip install ovito` |
| VASPKIT | Optional | binary download |
| basis_set_exchange | Optional (internal) | `pip install basis_set_exchange` |
| xTB | Optional (internal) | conda / binary |

---

## 9. Design Decisions Log

### 2026-04-20 — v0.8 refactor

**Problems identified in v0.7:**

1. SKILL.md asked the LLM to write multi-line Python (`sys.path.insert` + 7
   imports + multiple class instantiations). Error rate was high.
2. Scope contradiction: v0.7 §1.3 declared basis sets out-of-scope, yet
   SKILL.md's description advertised `量子化学`, `基组`, and Gaussian route
   setup, and Step 6 walked the LLM through `BSETools.get_basis_for_structure`.
3. Description triggers overlapped with the `gaussian-agent` skill (`MP2`,
   `高斯输入`, `optimize ethanol with MP2`). Both skills competed for the same
   prompts.
4. `D:\code\modeling\` and `D:\code\.claude\skills\modeling\` held duplicate
   copies of SKILL.md, the package, and references. Any edit needed to touch
   both or silently drifted.

**Decisions:**

| Item | Decision |
|---|---|
| Split vs. combined skill | Keep a single modeling skill; cross-domain builds (e.g. solid/liquid interfaces) argue against splitting |
| LLM interface | Recipe JSON + thin CLI. No multi-line Python from the LLM. |
| Scope boundary | `design.md` wins: QM calculation parameters → `gaussian-agent` |
| Python package | Keep as the backend library for the CLI and for direct consumers |
| Directory layout | Single source at `D:\code\modeling\`; `.claude/skills/modeling/` is a Windows junction pointing there |

**CLI scope — rejected alternatives:**

A proposed ~20-subcommand design (`build bulk`, `transform slab`, `sn2ts`,
`combinatorial`, …) was rejected. Recipe already covers multi-step and
single-step cases as 1-N-step JSON; adding flag sets per operation duplicated
the same schema and raised the LLM's memorization burden. Final CLI is
`run / convert / validate / tools / list`.

**Not changed:**

- QM / DFT / MD remain in one skill (cross-domain builds are common).
- `Structure.properties` remains an extensible metadata bag (ASE-style).
- `BSETools`, `XTBTools`, `SN2TSBuilder` stay in the package as internal
  utilities; they are no longer surfaced through SKILL.md.
