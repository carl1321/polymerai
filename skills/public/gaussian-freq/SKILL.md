---
name: gaussian-freq
description: Gaussian vibrational frequency and thermochemistry analysis on a pre-optimized geometry. Use when user wants to verify minima/TS via frequencies, compute ZPE, enthalpy, Gibbs free energy, IR/Raman intensities, or 频率计算/热力学.
---

# gaussian-freq

## When to Use
The geometry is already optimized and you need vibrational/thermo data.
If the geometry is not yet optimized, chain `gaussian-opt` first or use `gaussian-optfreq`.

## Workflow
`python scripts/run.py opt.log --preset b3lyp-d3 --temperature 298.15 --work-dir ./freq_run`
(Input can also be a `.xyz` / `.gjf` of the optimized structure.)

## Key Parameters
- `--temperature` / `--pressure` — thermochemistry conditions
- `--anharmonic` — add `Freq=Anharm`
- `--raman` — add Raman intensities
- `--readfc` — reuse force constants from `.chk`

## Related
- `gaussian-opt` — produces the input geometry
- `gaussian-optfreq` — combined opt+freq in one skill call

## Reference
- `references/thermochemistry.md`

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
