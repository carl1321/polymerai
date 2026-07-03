---
name: gaussian-tddft
description: Gaussian TD-DFT excited-state calculations including vertical excitations, oscillator strengths, and optional excited-state optimization. Use when user wants UV-Vis spectra, excitation energies, singlet/triplet states, fluorescence geometries, or 激发态/TDDFT.
---

# gaussian-tddft

## When to Use
Ground-state minimum already available (use `gaussian-opt` first if not).

## Workflow
`python scripts/run.py gs.log --states 10 --preset m062x --work-dir ./td_run`

Optional `--opt-state N` to optimize the Nth excited state.

## Reference
- `references/excited-states.md`

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
