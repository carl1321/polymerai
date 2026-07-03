# Built-in Molecules & Fragments Reference

## Quick Access

```python
from modeling.resources.molecules import BuiltinMolecules

# Get any molecule or fragment by name (case-insensitive)
water = BuiltinMolecules.get("water_tip3p")
ch3 = BuiltinMolecules.get_fragment("CH3")  # validates it's a fragment

# List what's available
BuiltinMolecules.list_available()    # all entries
BuiltinMolecules.list_fragments()    # fragments only
BuiltinMolecules.list_molecules()    # complete molecules only
```

## Water Models

| Model | Identifiers | Charge (O/H) |
|-------|------------|---------------|
| TIP3P | `water`, `water_tip3p`, `h2o` | -0.834/+0.417 |
| SPC/E | `water_spce` | -0.8476/+0.4238 |

## Ions

| Ion | Identifiers | Charge |
|-----|------------|--------|
| Na+ | `na`, `na+`, `sodium` | +1.0 |
| K+ | `k`, `k+`, `potassium` | +1.0 |
| Cl- | `cl-`, `chloride` | -1.0 |
| F- | `f-`, `fluoride` | -1.0 |
| Br- | `br-`, `bromide` | -1.0 |
| I- | `i-`, `iodide` | -1.0 |
| OH- | `oh-`, `hydroxide` | -1.0 |
| OOH- | `ooh-`, `hydroperoxide` | -1.0 |

## Small Molecules

| Molecule | Identifiers | Formula |
|----------|------------|---------|
| Methane | `methane`, `ch4` | CH4 |
| Ethane | `ethane`, `c2h6` | C2H6 |
| Ethanol | `ethanol`, `c2h5oh` | C2H5OH |
| Carbon monoxide | `co`, `carbon_monoxide` | CO |
| Carbon dioxide | `co2`, `carbon_dioxide` | CO2 |
| Ammonia | `nh3`, `ammonia` | NH3 |
| Hydrogen | `h2`, `hydrogen` | H2 |
| Nitrogen | `n2`, `nitrogen_molecule` | N2 |
| Oxygen | `o2`, `oxygen_molecule` | O2 |
| Benzene | `benzene`, `c6h6` | C6H6 |

## Fragments (Functional Groups)

Fragments are marked with `properties["fragment"] = True` and have a `connection_atom` index
indicating which atom bonds to the parent structure.

| Fragment | Identifiers | Connection Atom | Description |
|----------|------------|-----------------|-------------|
| Methyl | `ch3`, `methyl` | C (idx 0) | -CH3 tetrahedral |
| Nitro | `no2`, `nitro` | N (idx 0) | -NO2 trigonal planar |
| Hydroxyl | `oh`, `hydroxyl` | O (idx 0) | -OH |
| Hydroperoxy | `ooh`, `hydroperoxy` | O (idx 0) | -OOH |
| Amino | `nh2`, `amino` | N (idx 0) | -NH2 pyramidal |
| Carboxyl | `cooh`, `carboxyl` | C (idx 0) | -COOH planar |
| Trifluoromethyl | `cf3`, `trifluoromethyl` | C (idx 0) | -CF3 tetrahedral |
| Cyano | `cn`, `cyano` | C (idx 0) | -CN linear |
| Thiol | `sh`, `thiol` | S (idx 0) | -SH |
| Methoxy | `och3`, `methoxy` | O (idx 0) | -OCH3 |
| Fluorine | `f_fragment` | F (idx 0) | -F single atom |
| Chlorine | `cl_fragment` | Cl (idx 0) | -Cl single atom |
| Bromine | `br_fragment` | Br (idx 0) | -Br single atom |
| Iodine | `i_fragment` | I (idx 0) | -I single atom |
| Phenyl | `phenyl`, `c6h5` | C (idx 0) | -C6H5 planar ring |
| Vinyl | `vinyl`, `ch=ch2` | C (idx 0) | -CH=CH2 |
| Acetyl | `acetyl`, `coch3` | C (idx 0) | -COCH3 |

### Fragment Properties Convention

```python
fragment = BuiltinMolecules.get_fragment("CH3")
fragment.properties == {
    "fragment": True,
    "connection_atom": 0,    # atom index that bonds outward
    "formal_charge": 0,
}
```

## CombinatorialBuilder Integration

Fragments work directly with `CombinatorialBuilder` for combinatorial enumeration:

```python
from modeling.builders import CombinatorialBuilder

builder = CombinatorialBuilder()
structures = builder.build_all(
    template=template,
    substitutions={
        "R": ["CH3", "NO2", "F_fragment"],
        "Nu": ["F-", "Cl-", "Br-"],
    },
)
# → 9 structures (3 × 3)
```

## When a Molecule is Not Available

1. **Try ASE molecule library**: `ASETools.build_molecule("molecule_name")`
2. **Ask the user** for a structure file (.pdb, .xyz, .mol2)
3. **Search online databases**: PubChem, RCSB PDB, COD
