---
name: gaussian-diagnose
description: Analyze an existing Gaussian log file for errors, convergence issues, or anomalies — without running any new calculation. Use when user wants to understand why a Gaussian job failed, check an existing .log, or Gaussian 错误诊断.
---

# gaussian-diagnose

## When to Use
Read-only inspection of a `.log` file. Does not submit jobs.

## Workflow
`python scripts/run.py path/to/run.log`

Outputs a structured report of any matched error patterns and suggested fixes
(without applying them).

## Related
- The error catalog used here is shared with other gaussian-* skills via
  `gaussian_skills_lib.handlers.gaussian_errors`.

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
