---
name: vasp-scf
description: VASP self-consistent field (SCF) single-point calculation on a relaxed structure to get the converged charge density / WAVECAR / total energy. Use when user asks for SCF, single point, charge density, total energy at fixed geometry, or needs to run a prerequisite static calc before band/DOS. Keywords - SCF, single point, CHGCAR, WAVECAR, static, 自洽, 静态计算, 总能. Do NOT use for geometry relaxation (vasp-relax) or band structure (vasp-band).
---

# vasp-scf

## When to Use
User wants a fixed-geometry SCF on a (usually already relaxed) POSCAR — e.g. to produce CHGCAR for a following NSCF band/DOS calculation, or to get the converged total energy at higher precision.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **依赖**：输入 POSCAR 通常来自 **vasp-relax** 的 CONTCAR；下游 **vasp-band / vasp-dos** 依赖本步产出的 **CHGCAR**，禁止在缺 CHGCAR 时继续提交能带或 DOS。
4. **边界**：本 skill 为固定几何单点/静态自洽，不替代 **vasp-relax**（弛豫）或 **vasp-band**（能带路径）。

## Workflow
```
python {skill_dir}/scripts/run.py POSCAR --work-dir ./scf
```

1. Write INCAR (MPStaticSet default, or user-provided)
2. Write KPOINTS, POTCAR
3. Run VASP with handler loop
4. Parse vasprun.xml → report band gap, Fermi level, total energy

## POTCAR 策略
- 默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

## Key Parameters
| Flag | Default | Meaning |
|---|---|---|
| `--ediff X` | 1e-6 | electronic SCF tolerance |
| `--lwave` | true | keep WAVECAR |
| `--lcharg` | true | keep CHGCAR (needed for downstream band/DOS) |

## Related Skills
- vasp-relax (upstream) — get the relaxed POSCAR first
- vasp-band / vasp-dos (downstream) — use CHGCAR from here
- vasp-incar — custom INCAR

## Reference
See vasp-relax for shared conventions. Parameters reference TBD.

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
