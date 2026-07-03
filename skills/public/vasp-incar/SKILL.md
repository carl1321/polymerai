---
name: vasp-incar
description: >
  Generate VASP INCAR + KPOINTS files from a POSCAR and a calculation type, with
  automatic system detection (metal / semiconductor / insulator, Bravais lattice,
  magnetic elements), 30-rule conflict validator, and per-tag explainer. Use when
  user asks to generate INCAR, choose ENCUT/ISMEAR/SIGMA/ALGO/IBRION, build a
  KPOINTS mesh or band-path, validate an existing INCAR, or explain an INCAR
  parameter. Independent CLI; complements vasp-potcar (POTCAR) and vasp-agent
  (run-time correction).
---

# VASP INCAR & KPOINTS Generator

Read POSCAR + calc type → emit INCAR + KPOINTS + parameter explanation +
conflict report. Independent CLI; does not import vasp-agent.

## Trigger Conditions

Invoke when the user mentions:

- INCAR, KPOINTS, 生成输入文件, 输入参数
- ENCUT, ISMEAR, EDIFF, EDIFFG, SIGMA, ALGO, IBRION, NSW, PREC, LREAL, NCORE,
  KSPACING, MAGMOM
- 截断能, 电子步, 离子步, 展宽, k点, k-mesh, k-path, k 路径

## Quick Start

```bash
# Generate INCAR + KPOINTS for a band-structure calc
vasp-incar generate band --poscar POSCAR --out ./band_inputs/

# Validate an existing INCAR (returns conflict list, exit 1 on any error)
vasp-incar validate --incar INCAR

# Explain a single tag
vasp-incar explain ISMEAR

# Just talk through the parameter choices, do not write files
vasp-incar recommend hse --poscar POSCAR
```

## Subcommands

| Subcommand | Purpose |
|------------|---------|
| `generate <calc_type>` | Write INCAR + KPOINTS for the given calc type |
| `validate` | Run the 30-rule conflict detector on an existing INCAR |
| `explain <TAG>` | Print description, default, recommended range for one tag |
| `recommend <calc_type>` | Print parameter rationale without writing files |

### Calculation types

`relax`, `static`, `band`, `dos`, `phonon-finite`, `phonon-dfpt`, `elastic`,
`hse`, `scan`, `optical`, `defect`.

## Three-Layer Generation Strategy

```
POSCAR → system_detector → template (calc_type) → rules/overrides → validator → INCAR + KPOINTS
            │                  │                       │                  │
   metal / semi / insul.  pymatgen YAML defaults    3d magnetic        30 hard-rule
   Bravais lattice        + atomate2 auto_ismear    large cell etc.    detector
   magnetic elements      decision tree
```

Defaults come from `pymatgen.io.vasp.sets` (MPRelaxSet / MPStaticSet /
MPHSEBSSet) — validated by the Materials Project on 150K+ structures.

## Dependencies

`pymatgen`, `seekpath`, `pyyaml`, `numpy`. Install via
`pip install -e vasp-incar/` (or the linked path under `.claude/skills/`).

## Language

Respond in the user's language (English or 中文).
