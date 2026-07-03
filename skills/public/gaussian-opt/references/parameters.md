# gaussian-opt parameters

Port from `D:/code/gaussian-agent/gaussian_agent/input_sets/` in Step 2.
Key knobs:

- `Opt=(MaxCycles=N)` — cap optimization steps
- `Opt=Tight` — tighter convergence (use when `--tight`)
- `Opt=CalcFC` — compute force constants at start (helps difficult systems)
- `Opt=Cartesian` — avoid internal-coord failures
- `SCF=(MaxCycle=N,XQC)` — SCF convergence aid (also invoked by error handler)
