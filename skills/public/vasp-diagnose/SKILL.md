---
name: vasp-diagnose
description: Diagnose a failed VASP calculation — scan OUTCAR / vasp.out / stderr for the 30+ known VASP error patterns, report severity, and suggest INCAR fixes without running anything. Read-only. Use when user asks "why did my VASP job fail", "what does this error mean", "ZBRENT fatal error", "BRMIX", "EDDRMM", or 诊断/报错/出错/为什么不收敛. Does NOT submit any job — only analyzes existing output.
---

# vasp-diagnose

## When to Use
Post-mortem on a failed run. User points at a work directory containing OUTCAR / vasp.out.

## Workflow
```
python {skill_dir}/scripts/run.py ./failed_job_dir
```
Output: JSON report with detected errors, severity, ranked correction suggestions, and the matching regex span.

**Status**: SKILL.md complete; run.py pending Phase 5.

<!-- HPC_CONFIG_BLOCK -->
## HPC 配置

本 skill 通过 `/mnt/skills/public/_shared-vasp/profiles.yaml` 读取超算凭据（SSH key / SCNet API key 等）。
首次使用：

```bash
cp /mnt/skills/public/_shared-vasp/config.template.yaml /mnt/skills/public/_shared-vasp/config.yaml
chmod 600 /mnt/skills/public/_shared-vasp/profiles.yaml      # 文件含密钥路径，限制权限
chmod 600 /mnt/skills/public/_shared-vasp/config.yaml
```

项目级配置 `/mnt/skills/public/_shared-vasp/config.yaml` 只放 `profile: <name>` + 项目专属设置。
完整说明见 [`_shared-vasp/HPC.md`](../_shared-vasp/HPC.md)。
