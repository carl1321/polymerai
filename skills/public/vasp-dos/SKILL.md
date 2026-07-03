---
name: vasp-dos
description: VASP density of states (total DOS, orbital-projected DOS, site-projected DOS) on a uniform k-mesh. Use when user wants DOS, PDOS, LDOS, orbital/atom-projected DOS, Fermi level analysis, or 态密度/投影态密度. Requires a preceding vasp-scf (CHGCAR). Do NOT use for bands along high-symmetry path (vasp-band).
---

# vasp-dos

## When to Use
Uniform-mesh NSCF for (projected) DOS. Inputs a relaxed POSCAR + CHGCAR from vasp-scf.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **依赖**：必须提供 **`--scf-dir`** 且其中含 **CHGCAR**（来自 **vasp-scf**）；输入结构与 SCF 一致，禁止无 CHGCAR 或晶胞不一致时硬算。
4. **边界**：均匀 k 网 DOS / PDOS 用本 skill；沿高对称路径的 **E(k)** 必须用 **vasp-band**，禁止互替。

## Workflow
```
python {skill_dir}/scripts/run.py CONTCAR --scf-dir ./scf --work-dir ./dos
```
- ICHARG=11, LORBIT=11, NEDOS=3000 by default
- Denser KPOINTS than SCF (default 2×)

## POTCAR 策略
- 默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

## Key Parameters
| Flag | Default |
|---|---|
| `--nedos N` | 3000 |
| `--kpt-scale F` | 2.0 × SCF |

## Related
- vasp-scf (upstream, required)
- vasp-analysis dos (plot)

**Status**: SKILL.md complete; `scripts/run.py` pending Phase 3.

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
