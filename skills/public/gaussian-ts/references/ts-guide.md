# TS guide

Key Gaussian keywords for TS optimization:
- `Opt=(TS, CalcFC, NoEigenTest)` — second-order saddle point
- `Opt=(TS, CalcAll)` — compute Hessian every step (expensive, last resort)
- `Freq` — verify exactly one imaginary frequency

TS guess quality matters more than Gaussian flags. See `modeling` skill.
