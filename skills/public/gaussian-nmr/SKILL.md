---
name: gaussian-nmr
description: Gaussian GIAO NMR chemical shift prediction on a relaxed geometry. Use when user wants 1H/13C/19F NMR shifts, shielding tensors, or NMR 化学位移.
---

# gaussian-nmr

## When to Use
Geometry already optimized (use `gaussian-opt` first if not).

## Workflow
`python scripts/run.py opt.log --nuclei "1H 13C" --preset b3lyp-d3 --work-dir ./nmr_run`

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
