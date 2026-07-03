---
name: vasp-lobster
description: VASP preparation for LOBSTER bonding analysis — crystal orbital Hamilton population (COHP), integrated COHP (ICOHP), COOP, bond analysis. Generates a VASP static calc with LOBSTER-compatible settings (NBANDS covers all basis functions, LWAVE=.TRUE., ISYM=-1), then optionally invokes lobster binary on the output. Use when user wants bonding analysis, COHP, ICOHP, bond strength, chemical bonding, 成键分析/COHP分析.
---

# vasp-lobster

## When to Use
Want to do bonding analysis (COHP/COOP/Madelung) with LOBSTER after a VASP SCF.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **协议**：VASP 静态步须满足文档中的 NBANDS/ISYM/LWAVE/LORBIT 等约定，再衔接 `lobster`；禁止跳过本 skill 的 VASP 阶段直接编造 COHP 数值。

## Workflow
```
python {skill_dir}/scripts/run.py CONTCAR --work-dir ./lobster --basis pbeVASPfit2015
```
INCAR constraints: `NBANDS ≥ basis size`, `ISYM=-1`, `LWAVE=.TRUE.`, `LORBIT=11`.
Then runs `lobster` binary if available.

## POTCAR 策略
- 默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

**Status**: SKILL.md complete; run.py pending Phase 3.

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
