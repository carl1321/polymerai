# vasp-incar — internal notes

This skill is independent of `vasp-agent`. The two are complementary:

| Layer            | Skill        | Where it acts                           |
|------------------|--------------|-----------------------------------------|
| Static defence   | vasp-incar   | Validates INCAR **before** submission   |
| Runtime recovery | vasp-agent   | Custodian fixes **during** the run      |

## Architecture

```
vasp_incar/
├── cli.py              # generate / validate / explain / recommend
├── generator.py        # main pipeline: load → detect → template → override → validate
├── system_detector.py  # metal / semi / insul, Bravais lattice, magnetic elements
├── kpoints.py          # Bravais-aware mesh + seekpath line-mode + KPOINTS_OPT
├── validator.py        # rules engine over rules/conflicts.yaml
├── explainer.py        # reads references/incar_params.yaml
├── templates/          # one module per calc_type
├── rules/              # YAML data: overrides + conflicts
└── references/         # parameter database + VASP wiki copies
```

## Three layers of generation

1. **pymatgen YAML defaults** (`templates/base.py` extends MPRelaxSet etc.)
2. **calc-type template** (overrides specific to band / dos / phonon / …)
3. **rules/overrides.yaml** for system-dependent tweaks (3d-magnetic LDAU,
   semiconductor ISMEAR, large-cell LREAL=Auto, …)

The `validator` runs **after** all three layers and refuses to write the file
if any of the 30 hard rules trip.

## auto_ismear decision tree (replicated from atomate2)

```python
if bandgap is None:
    ISMEAR = 0;  SIGMA = 0.2     # safe default
elif bandgap < 1e-4:             # metal
    ISMEAR = 2;  SIGMA = 0.2
else:                            # semiconductor / insulator
    ISMEAR = -5                  # tetrahedron, requires ≥4 k-points
```

## Tests

`pytest tests/` — fixtures are small POSCARs (Si / Cu / Fe2O3 / Pt-slab /
H2O-mol). Each of the 30 conflict rules has its own unit test.
