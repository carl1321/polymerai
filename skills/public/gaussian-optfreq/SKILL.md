---
name: gaussian-optfreq
description: Gaussian combined geometry optimization followed by frequency analysis. Use when user wants a fully characterized minimum with thermochemistry in one go, or 优化加频率/opt+freq.
---

# gaussian-optfreq

## When to Use
Ground-state minimum + thermochemistry in one dispatch.
Not for transition states (use `gaussian-ts`).

## Workflow
`python scripts/run.py mol.xyz --preset b3lyp-d3 --charge 0 --mult 1 --work-dir ./run`
Internally runs `Opt Freq` in a single Gaussian job (or as a 2-step chain depending on config).

## Related
- `gaussian-opt`, `gaussian-freq` — use these if you need finer control

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
