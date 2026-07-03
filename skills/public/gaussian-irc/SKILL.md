---
name: gaussian-irc
description: Gaussian intrinsic reaction coordinate (IRC) path following with 3-tier progressive error recovery (HPC → LQA → smaller-step). Use when user wants to trace a reaction path from a verified TS, validate that a TS connects the expected reactant and product, or 反应路径/IRC 跟踪.
---

# gaussian-irc

## When to Use
Input must be a **verified TS** (one imaginary frequency already confirmed).
Validate with `gaussian-freq` or `gaussian-ts` first.

## Workflow
`python scripts/run.py verified_ts.log --direction both --maxpoints 50 --work-dir ./irc_run`

If the forward/backward IRC fails, the skill auto-degrades:
1. HPC: tighten SCF, CalcFC, larger maxpoints
2. LQA: switch integrator to `IRC=(LQA)`
3. Smaller-step: reduce step, allow partial paths

## Related
- `gaussian-ts` — produces the verified TS upstream

## Reference
- `references/irc-recovery.md`

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
