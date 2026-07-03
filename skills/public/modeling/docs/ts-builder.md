# SN2 TS Builder Reference

## Quick Start

```python
from modeling.builders import SN2TSBuilder

builder = SN2TSBuilder()

# Single structure
ts = builder.build(r_group="CH3", nucleophile="Br", leaving_group="Br")

# Batch: all R x Nu x LG combinations
structures = builder.build_all(
    r_groups=["F", "CH3", "NO2"],
    nucleophiles=["F", "Cl", "Br", "OH", "OOH"],
    leaving_groups=["F", "Cl", "Br", "OH", "OOH"],
)
# -> 75 structures (3 x 5 x 5)
```

## Supported Species

| Role | Species | Notes |
|------|---------|-------|
| R group | F, CH3, NO2 | Equatorial position (xy-plane) |
| Nucleophile | F, Cl, Br, OH, OOH | Axial (-z direction) |
| Leaving group | F, Cl, Br, OH, OOH | Axial (+z direction) |

## Empirical TS Bond Lengths (C-X axial)

| Species | Distance (A) |
|---------|-------------|
| F | 1.94 |
| Cl | 2.33 |
| Br | 2.54 |
| OH | 1.98 |
| OOH | 1.98 |

## Geometry

- Trigonal bipyramidal: Nu---C---LG axial (~180 deg), H,H,R equatorial
- Symmetry: when Nu == LG, both C-X distances are forced equal
- Central C at origin, H1 at 90 deg, H2 at 210 deg, R at 330 deg in xy-plane

## Default Gaussian Parameters

```python
route: "# MP2/aug-cc-pVDZ opt=(ts,calcfc,noeigentest) freq"
charge: -1
multiplicity: 1
link0: {"nproc": "16", "mem": "16GB"}
```

Override via `build()` kwargs:

```python
ts = builder.build(
    r_group="CH3", nucleophile="F", leaving_group="Cl",
    gaussian_route="# B3LYP/6-31+G(d) opt=(ts,calcfc) freq",
    charge=-1, multiplicity=1,
)
```

## Writing Output

```python
from modeling.io import write_structure

write_structure(ts, "TS_CH3_NuBr_LGBr.gjf", format="gaussian")
```
