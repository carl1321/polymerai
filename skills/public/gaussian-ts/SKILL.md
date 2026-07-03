---
name: gaussian-ts
description: Gaussian transition state search with second-order saddle-point optimization, frequency verification, and optional IRC validation. Use when user wants TS optimization, saddle point search, or 过渡态搜索/TS 优化/IRC 验证.
---

# gaussian-ts

## When to Use
User has a **TS guess structure** (already positioned near the saddle) and wants
to converge to a true transition state with exactly one imaginary frequency.

**TS guess generation is not in scope** — build the guess with the `modeling`
skill (e.g. SN2 builder) or external tools (GSM, NEB) first.

## Workflow
1. TS guess geometry → `modeling`
2. `python scripts/run.py ts_guess.xyz --preset b3lyp-d3 --charge 0 --mult 1 --work-dir ./ts_run`
3. Script runs Opt=(TS,CalcFC,NoEigenTest) + Freq; if one imaginary frequency and it matches
   the expected reaction mode, optionally chains to `gaussian-irc` for validation.

## Related
- `modeling` — TS guess builder (mandatory upstream)
- `gaussian-irc` — downstream path validation
- `gaussian-freq` — re-run frequency separately if needed

## Reference
- `references/ts-guide.md`

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
