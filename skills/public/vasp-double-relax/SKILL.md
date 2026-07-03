---
name: vasp-double-relax
description: Two-stage VASP structure relaxation — coarse relax followed by tight relax using CONTCAR from stage 1. Encodes the physical convention that a single relax may not fully converge cell shape + ionic positions simultaneously. Use when user wants "double relax", "two-step relax", "coarse then tight", or 两步弛豫/双步弛豫. Do NOT use for single-shot relax (vasp-relax).
---

# vasp-double-relax

## When to Use
User wants a two-stage relaxation where stage 1 uses coarser parameters and stage 2 tightens convergence criteria on the stage-1 CONTCAR.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **协议**：两阶段在同一 `run.py` 内顺序执行；禁止用两次独立 **vasp-relax** 调用冒充本 skill 的 stage1/stage2 约定（EDIFFG/NSW 等默认值不同）。
4. **边界**：两步弛豫用本 skill；单步弛豫用 **vasp-relax**。

## Workflow
```
python {skill_dir}/scripts/run.py POSCAR --work-dir ./double_relax
```

1. Stage 1: coarse relax (EDIFFG=-0.05, NSW=200)
2. Copy stage1/CONTCAR → stage2/POSCAR
3. Stage 2: tight relax (EDIFFG=-0.01, NSW=300, optionally higher ENCUT)
4. Output unified `summary.json` with both stages

## POTCAR 策略
- 每个阶段默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

## Key Parameters
| Flag | Default | Meaning |
|---|---|---|
| `--stage1-ediffg` | -0.05 | Force tolerance stage 1 |
| `--stage2-ediffg` | -0.01 | Force tolerance stage 2 |
| `--stage2-encut-boost` | 1.3 | Multiply ENCUT for stage 2 |

## Related Skills
- vasp-relax (single-shot)
- modeling (build input POSCAR)
- vasp-scf (next step after relax)

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
