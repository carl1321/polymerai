# Conventions shared across all gaussian-skills

## Input format

All skills accept a molecular structure via:

- An ASE-readable file: `.xyz`, `.gjf`, `.com`, `.mol`, `.sdf`, `.pdb`, …
- Or raw Cartesian coords in a `.xyz`-style block.

Charge/multiplicity must be supplied explicitly (CLI flag or config). The skills do not guess.

## Work directory layout

```
<work_dir>/
├── attempt_0/
│   ├── input.gjf
│   ├── input.log
│   └── result.json         # parsed outputs
├── attempt_1/              # present only if retries ran
└── summary.json            # final result + retry trail
```

## Config resolution

Each skill reads `~/.gaussian_skills/config.yaml` via `_lib.config.load_config`. CLI flags override config; config overrides defaults.

## Structure upstream

**Initial structures** (molecules, TS guesses, scan starting points) are the
responsibility of the `modeling` skill. Gaussian skills do **not** build
structures — they optimize, analyze, or probe them.

## Python package

Shared helpers live in package `gaussian_skills_lib` (installed from
`D:/code/gaussian-skills/` via `pip install -e .`). Skill `run.py` scripts must
not import the legacy `gaussian_agent` package.
