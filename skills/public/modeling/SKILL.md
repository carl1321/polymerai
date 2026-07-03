---
name: modeling
description: >
  Atomic-scale structure modeling for MD/DFT simulations. Builds crystal structures,
  surfaces, supercells, defects, porous materials, solvated systems, heterostructures,
  and molecular structures. Use this skill whenever the user asks to build, create,
  or generate atomic structures, simulation boxes, or prepare coordinate files for
  VASP, LAMMPS, GROMACS, or other simulation software. Also trigger when users mention
  建模, 构建结构, 创建超胞, 切表面, 填充溶剂, or describe any system they want to
  simulate at the atomic level (e.g. "SiO2 with water", "Pt surface with CO",
  "Cu vacancy supercell"). For Gaussian/ORCA calculation parameters (route, basis
  set, charge/multiplicity), defer to the `gaussian-agent` skill — this skill only
  writes coordinates to `.gjf` / `.com` if requested.
---

# Modeling Skill

Atomic-scale structure building system for computational materials science and chemistry.

## What This Skill Does

Takes a user's description of a physical/chemical system and produces atomic coordinate files
ready for simulation software (VASP, LAMMPS, GROMACS, etc.). The core workflow is:
**generate a Recipe JSON → run it through `modeling_cli.py`**, not hand-written Python.

## Core Workflow

```
User describes system → Collect parameters → Resolve conflicts → Generate Recipe JSON → Run CLI → Validate → Export
```

## Step 1: Understand the Request

Parse the user's description and identify:

- **Target system**: What are they trying to build?
- **Simulation method**: DFT, MD (all-atom or coarse-grained)?
- **Output format**: POSCAR, LAMMPS data, GRO, PDB, XYZ, CIF, or `.gjf` (coordinates only — route/basis handled by `gaussian-agent`)?
- **Components**: What molecules, crystals, surfaces are involved?

## Step 2: Collect Parameters (Interactive)

Follow these principles until all parameters are complete:

### Principle 1: Identify and Report Conflicts

When parameters contradict each other (e.g., molecule count vs density vs box size),
clearly state the conflict with quantitative analysis.

Example:
```
I notice a conflict in your water layer parameters:
- You specified 10000 water molecules AND density 0.9 g/cm³
- Available volume: 112.5 nm³
- At 0.9 g/cm³ → ~3400 molecules
- With 10000 molecules → density ~2.7 g/cm³ (unphysical)

Please choose: (1) prioritize density, (2) prioritize count, (3) adjust box size
```

### Principle 2: Quantify Everything

Never say "too big" or "too small". Always compute the actual numbers:
- Estimate atom counts
- Calculate volumes, densities, concentrations
- Check if the system fits in the box

### Principle 3: Offer Clear Options

When ambiguity exists, present 2-3 concrete options with recommendations.

### Principle 4: Clarify Ambiguous Units

Proactively ask about:
- Concentration: mol/L vs wt% vs mol%?
- Length: nm vs Å?
- Temperature: K vs °C?

### Principle 5: Suggest Feasible Simplifications

When the user's system is too large for atomic simulation, suggest reduced models:
- Representative unit cells instead of full particles
- Pore channel models instead of full porous structures
- Slab models instead of bulk interfaces

Explain the scientific justification for each simplification.

### Completeness Checklist

Keep asking until ALL of these are resolved:

- [ ] Box/cell dimensions defined
- [ ] All components identified (elements, molecules, structures)
- [ ] Quantities or densities for each component specified
- [ ] No parameter conflicts remain
- [ ] Output format confirmed
- [ ] Boundary conditions clear (PBC, vacuum layers, etc.)

## Step 3: Plan the Build

Generate a step-by-step build plan. Read `references/tools.md` for the tool capability
matrix and `references/recipes.md` for Recipe JSON templates that cover common scenarios.

### Domain Guide Routing (按需 Read，不要全量加载)

按用户意图加载对应 domain guide：

| 用户意图 | 必读 |
|---|---|
| 晶体 / 表面 / 缺陷 / 超胞 / 异质结 | `references/materials.md` |
| 离散分子 / fragment / 装配 | `references/molecular.md` |
| 溶剂盒子 / Packmol 填充 / 电解质 | `references/solvation.md` |
| 跨域复合（界面 / 异质 / 复杂体系） | `references/interfaces.md` |
| 任意建模——参数选择 | `references/decision-rules.md`（**始终参考**） |

`decision-rules.md` 是规则汇总（真空层厚度、Slab 层数、Packmol 密度、k 点估算等），
任何 Recipe 在选默认值前应先查表，避免凭直觉写。

Example plan for "5×5 nm hydroxylated SiO₂ surface solvated in water":
```
1. Read user's SiO₂ unit cell          → io/readers
2. Cut (001) surface                    → SlabTransform
3. Expand to 5×5 nm                    → SupercellTransform
4. Hydroxylate surface                  → (tool: Atomsk / manual)
5. Fill water + ions                    → Filler (Packmol)
6. Add vacuum layer                     → VacuumTransform
7. Validate geometry                    → GeometryValidator
8. Export to LAMMPS format              → io/writers
```

Present the plan to the user for confirmation before executing.

## Step 4: Execute — Recipe JSON + CLI

The skill exposes a thin CLI at `modeling_cli.py`. LLMs should generate a **Recipe JSON**
describing the build steps, then invoke the CLI. Do NOT write multi-line Python
imports — the Recipe format is the sanctioned interaction path.

### Recipe JSON schema

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
    "output": {"format": "poscar", "filename": "Pt111_CO.poscar"}
  }
}
```

See `references/recipes.md` for ready-to-use templates.

### CLI commands

```bash
# Run a Recipe → structure file
python modeling_cli.py run recipe.json -o output.poscar [--validate]

# Convert between formats
python modeling_cli.py convert -i input.cif -o output.poscar

# Validate a structure (level 1=geometry, 2=+chemistry, 3=+physics)
python modeling_cli.py validate structure.poscar --level 2

# Check which backend tools (ASE, Packmol, Atomsk, VASPKIT, ...) are installed
python modeling_cli.py tools

# List all available builders / transforms
python modeling_cli.py list builders
python modeling_cli.py list transforms
```

### Tool Selection Guide

Read `references/tools.md` for the full tool capability matrix. Quick reference:

| Task | Primary Tool | Fallback |
|------|-------------|----------|
| Crystal bulk | ASE `build_bulk()` | PyXtal |
| Random crystal | PyXtal `random_crystal()` | - |
| Cut surface | ASE / VASPKIT (803) | Atomsk |
| Supercell | ASE | VASPKIT (401), Atomsk |
| Point defects | Atomsk | Pymatgen |
| Dislocations | Atomsk | - |
| Grain boundaries | Atomsk | - |
| Heterostructure | VASPKIT (804) | Manual |
| Random alloy | VASPKIT (802) | Pymatgen |
| Fill molecules | Packmol | - |
| LAMMPS topology | Moltemplate | - |
| Structure analysis | OVITO | - |

The tool table describes the backend libraries that the CLI's builders/transforms
call into. When a tool is unavailable on the user's machine (`modeling_cli.py tools`
reports missing), suggest installation or pick the fallback in the Recipe.

## Step 5: Validate

The CLI can validate as part of `run` (`--validate`) or standalone:

```bash
python modeling_cli.py validate output.poscar --level 2
```

- Level 1 (required): overlaps, boundaries, periodic images
- Level 2 (recommended): bond lengths, chemistry sanity
- Level 3 (optional): density, energy sanity

Report validation results to the user. If errors are found, adjust the Recipe and re-run.

## Step 6: Export

Recipe `metadata.output` controls the format, or pass `-o path.ext` to the CLI.
Supported output formats:

| Extension | Format | Use |
|-----------|--------|-----|
| `.poscar` / `POSCAR` | VASP | DFT with VASP |
| `.data` | LAMMPS | MD with LAMMPS |
| `.gro` | GROMACS | MD with GROMACS |
| `.pdb` | PDB | General / visualization |
| `.xyz` | XYZ | General / visualization |
| `.cif` | CIF | Crystal exchange |
| `.gjf` / `.com` | Gaussian (coordinates only) | Hand off to `gaussian-agent` for route/basis |

`.gjf` output contains only coordinates — no route section, no basis set, no
charge/multiplicity. If the user wants a complete Gaussian input file, invoke the
`gaussian-agent` skill after the structure is built.

## Scope Boundaries

This skill generates atomic structures and writes coordinate files. It does NOT
produce calculation-method parameters (basis sets, k-points, pseudopotentials,
force-field parameters, etc.).

| In Scope | Details |
|----------|---------|
| Structure generation | Crystal, surface, molecule, solvated system, heterostructure, defect |
| Coordinate file export | POSCAR, LAMMPS, GRO, PDB, XYZ, CIF, `.gjf` (coords only) |
| Structure validation | Geometry / chemistry / physics checks |

| Out of Scope | Redirect To |
|--------------|-------------|
| Basis set selection, Gaussian route, charge/multiplicity | `gaussian-agent` skill |
| VASP INCAR / KPOINTS / POTCAR | `vasp-agent` / `potcar` skill |
| Force field parameterization | MD / force-field skill |
| Running simulations | Workflow skill |
| Post-processing results | Analysis skill |

If the user asks about these, acknowledge and suggest the appropriate skill.

## Language Support

Respond in the same language the user uses. Support both English and Chinese (中文).
