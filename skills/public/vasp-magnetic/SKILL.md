---
name: vasp-magnetic
description: VASP magnetic calculations — collinear FM/AFM/FiM with MAGMOM initialization, non-collinear with LNONCOLLINEAR, spin-orbit coupling (LSORBIT), magnetic anisotropy energy. Use when user wants magnetic moments, spin configuration, AFM/FM energy difference, SOC/spin-orbit, MAE/magnetic anisotropy, or 磁矩/自旋/反铁磁/自旋轨道耦合. Handles the tricky initial MAGMOM setup and high/low-spin convergence strategies.
---

# vasp-magnetic

## When to Use
Any VASP calc where magnetism is the primary target (not just a side-effect of relaxation).

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **边界**：磁性构型、MAFM/AFM 对比、SOC/MAE 等用本 skill；**普通无磁或弱磁结构弛豫**优先 **vasp-relax**，不要默认套本 skill。

## Workflow
```
python {skill_dir}/scripts/run.py POSCAR --work-dir ./mag --config fm
python {skill_dir}/scripts/run.py POSCAR --work-dir ./mag_afm --config afm --magmom "Fe:up,Fe:down,O:0,O:0"
python {skill_dir}/scripts/run.py POSCAR --work-dir ./mae --soc --quantization-axis 0 0 1
```

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
