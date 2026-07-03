---
name: vasp-dielectric
description: VASP dielectric tensor calculation via DFPT (LEPSILON=.TRUE.) — static dielectric constant, Born effective charges, ion-clamped dielectric. Use when user wants dielectric constant, ε, Born charges, DFPT dielectric, or 介电常数. For frequency-dependent optics, use vasp-optics instead.
---

# vasp-dielectric

## When to Use
Static (ion-clamped + ionic contribution) dielectric tensor and Born effective charges via DFPT.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **物理**：静态介电 / Born 电荷 / DFPT 用本 skill 的 INCAR 约定；**频散光学**（LOPTICS、ε(ω)）属于 **vasp-optics**，禁止用 vasp-optics 流程回答「只求静态 ε」类问题，反之亦然。

## Workflow
```
python {skill_dir}/scripts/run.py CONTCAR --work-dir ./eps
```
INCAR: `LEPSILON=.TRUE., IBRION=8, NSW=1, LPEAD=.TRUE.`

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
