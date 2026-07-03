---
name: gaussian-batch
description: Gaussian high-throughput batch dispatch of the same calculation type across many molecules. Use when user has a set of molecules and wants to run the same workflow on all of them, or 高通量/批量计算.
---

# gaussian-batch

## When to Use
Multiple input structures + a common workflow type. Builds a manifest and dispatches
to another `gaussian-*` skill per structure.

## Workflow
`python scripts/run.py --type opt --inputs mols/*.xyz --preset b3lyp-d3 --work-dir ./batch_run`

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
