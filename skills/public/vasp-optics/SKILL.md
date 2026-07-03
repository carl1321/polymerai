---
name: vasp-optics
description: VASP frequency-dependent optical properties — ε(ω), absorption, reflectivity, refractive index via independent-particle approximation (LOPTICS=.TRUE.) or BSE. Use when user wants optical spectrum, absorption, refractive index n(ω), extinction coefficient k(ω), ε1(ω)/ε2(ω), or 光学性质/吸收谱/介电函数. For static dielectric only, use vasp-dielectric.
---

# vasp-optics

## When to Use
Frequency-dependent ε(ω), α(ω), n(ω). Requires dense k-mesh and many empty bands.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **物理**：频散 ε(ω)/吸收等用本 skill（LOPTICS 等）；**仅静态介电张量 / DFPT** 用 **vasp-dielectric**，禁止混用技能回答。

## Workflow
```
python {skill_dir}/scripts/run.py CONTCAR --work-dir ./optics --nbands-factor 3
```
INCAR: `LOPTICS=.TRUE., NBANDS=high, CSHIFT=0.1`

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
