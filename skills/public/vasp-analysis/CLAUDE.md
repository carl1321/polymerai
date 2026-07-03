# vasp-analysis — internal notes

This skill is **independent**: it does not import `vasp-agent`. The
`vasp-agent` package keeps its own `visualizer.py` for now; future Phase-2 work
may delegate from vasp-agent into this skill.

## Architecture

```
vasp_analysis/
├── cli.py              # argparse subcommands
├── detector.py         # detect calc type from workdir contents
├── parser/             # thin wrappers around pymatgen + phonopy IO
├── plotters/           # one module per figure type, all return Figure or write file
├── reporters/          # markdown / csv summary + comparison tables
├── workflows/          # multi-step pipelines (phonon, auto)
└── styles/             # matplotlib stylesheets
```

## Detection rules (detector.py)

| Signal in workdir                            | Calc type        |
|----------------------------------------------|------------------|
| `KPOINTS` line-mode header                   | band             |
| `DOSCAR` with high NEDOS, no line-mode       | dos              |
| `band.yaml` or `FORCE_SETS`                  | phonon           |
| `OUTCAR` contains "ELASTIC MODULI"           | elastic          |
| `vasprun.xml` with `LOPTICS=T`               | optical          |
| sibling dirs with shared name pattern + ENCUT scan | convergence|

## Why sumo

sumo is already pymatgen-based, ships publication-style defaults, supports
projected band/DOS in one call, and shares its k-path generator (seekpath) with
atomate2 and the upstream vasp-incar skill — no path mismatch when chaining.

## Why pyprocar

pyprocar is the de-facto choice for Fermi surface (2D/3D) and band unfolding;
sumo does not cover these. Spin-texture also lives here.

## Adding a new plotter

1. New module in `plotters/foo.py` exposing `plot(workdir, **opts) -> Path`.
2. Register in `cli.py` as a subcommand or in `workflows/auto.py` for auto-mode.
3. Add fixture + test in `tests/`.

## Tests

`pytest tests/` — fixtures live in `tests/fixtures/`. Image diffs use a 5%
pixel tolerance to absorb sumo style tweaks.
