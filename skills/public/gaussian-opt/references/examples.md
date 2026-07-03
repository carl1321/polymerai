# gaussian-opt examples

```bash
# Ethanol at B3LYP-D3/6-31G(d)
python scripts/run.py ethanol.xyz --preset b3lyp-d3 --charge 0 --mult 1 --work-dir ./ethanol_opt

# Water at MP2/6-311+G(d,p) in SMD methanol
python scripts/run.py water.xyz --preset mp2 --solvent methanol --work-dir ./h2o_mp2

# Dry run (inspect .gjf before running Gaussian)
python scripts/run.py mol.xyz --dry-run --work-dir ./sanity
```
