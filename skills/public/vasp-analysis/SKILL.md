---
name: vasp-analysis
description: >
  Post-process VASP calculations into publication-quality figures and summary
  tables. Use when user asks for band/DOS plots, phonon dispersion, Fermi
  surface, optical spectra, elastic constants, defect formation energy,
  convergence tests, or wants to compare multiple VASP runs. Reads a VASP work
  directory, auto-detects the calculation type, and delegates to sumo / pyprocar
  / pymatgen / phonopy as appropriate.
---

# VASP Analysis & Visualization

Read a VASP work directory → auto-detect calculation type → produce
publication-ready figures + a markdown summary table. Independent CLI; does not
import vasp-agent.

## Trigger Conditions

Invoke when the user mentions:

- 后处理, 画图, 绘图, plot, 出版图, 可视化
- 能带图, band plot, band structure
- DOS图, 态密度, density of states
- 声子谱, 声子色散, phonon dispersion
- 介电函数, 吸收谱, 反射率, optical spectra, dielectric function
- 弹性常数, elastic constants
- 缺陷形成能, defect formation energy
- 收敛测试, convergence test, ENCUT 收敛, KPOINTS 收敛
- Fermi surface, 费米面, band unfolding, 有效质量
- 分析结果, OUTCAR 分析

## Quick Start

```bash
# Auto: detect calc type from workdir, produce all relevant figures + summary
vasp-analysis auto --workdir ./Si_band

# Single plot
vasp-analysis band --workdir ./Si_band --projected
vasp-analysis dos  --workdir ./Si_dos  --orbital --element

# Phonon (assumes phonopy run already produced FORCE_SETS in workdir)
vasp-analysis phonon --supercell 2 2 2 --mode finite

# Compare multiple runs (e.g. PBE vs HSE)
vasp-analysis compare ./Si_PBE ./Si_HSE
```

## Backend Delegation

| Task                                    | Backend                                  |
|-----------------------------------------|------------------------------------------|
| band, dos, band+dos, optical            | sumo (CLI/API)                           |
| phonon                                  | sumo + phonopy CLI                       |
| Fermi surface, unfolding, spin-texture  | pyprocar                                 |
| elastic                                 | pymatgen.analysis.elasticity (in-house)  |
| defect formation energy                 | pymatgen.analysis.defects (in-house)     |
| convergence                             | matplotlib (in-house)                    |

## Subcommands

| Subcommand                              | Purpose                                              |
|-----------------------------------------|------------------------------------------------------|
| `auto`                                  | Detect calc type → run all relevant plotters         |
| `band`, `dos`, `phonon`, `optical`      | Single-task plotters                                 |
| `elastic`, `defect`, `convergence`      | Specialised analysis                                 |
| `summary`                               | Markdown table: total energy, band gap, magmom, ... |
| `compare DIR1 DIR2 ...`                 | Multi-run comparison table                           |

## Dependencies

`pymatgen`, `sumo`, `pyprocar`, `phonopy`, `matplotlib`, `numpy`, `seekpath`.
Install via `pip install -e .claude/skills/vasp-analysis/`.

## Language

Respond in the user's language (English or 中文).
