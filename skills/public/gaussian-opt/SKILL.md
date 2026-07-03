---
name: gaussian-opt
description: Gaussian geometry optimization. Use when user wants to optimize a molecular structure with DFT/HF/MP2, minimize a closed-shell ground state, or 几何优化/结构优化 a single molecule.
---

# gaussian-opt

## When to Use
User asks to optimize a molecular geometry in Gaussian (no frequency, no TS).
For opt→freq use `gaussian-optfreq`. For transition states use `gaussian-ts`.

## Workflow
1. User provides structure via `modeling` skill or a `.xyz` / `.gjf`.
2. Choose method/basis (or preset) + charge/multiplicity.
3. Run `python scripts/run.py input.xyz --preset b3lyp-d3 --charge 0 --mult 1 --work-dir ./opt_run`.
4. Result written to `<work_dir>/summary.json`.

## Key Parameters
| Flag | Meaning |
|---|---|
| `--preset` | method+basis preset from `gaussian_skills_lib.inputs.sets.PRESETS` |
| `--method` / `--basis` | override preset |
| `--charge` / `--mult` | molecular charge / multiplicity |
| `--solvent` | SMD solvent name (optional) |
| `--tight` | add `Opt=Tight SCF=Tight` |

## Related
- `modeling` — builds/prepares the input geometry
- `gaussian-freq` — add vibrational analysis
- `gaussian-optfreq` — combined opt+freq

## Reference
- `references/parameters.md`
- `references/examples.md`

<!-- HPC_CONFIG_BLOCK -->
## HPC 配置

本 skill 通过 `~/.hpc/profiles.yaml` 读取超算凭据（SSH key / SCNet API key 等）。
首次使用：

```bash
mkdir -p ~/.hpc
cp _shared-gaussian/hpc-profiles.template.yaml ~/.hpc/profiles.yaml
chmod 600 ~/.hpc/profiles.yaml      # 文件含密钥路径，限制权限
# 编辑填入至少一个 profile（local / generic-slurm / scnet-h100）
```

项目级配置 `~/.gaussian_skills/config.yaml` 只放 `profile: <name>` + 项目专属设置。
完整说明见 [`_shared-gaussian/HPC.md`](../_shared-gaussian/HPC.md)。
