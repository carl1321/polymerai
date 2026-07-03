---
name: vasp-phonon
description: VASP phonon dispersion and density of states via finite-displacement method driven by phonopy. Generates symmetry-reduced displaced supercells, runs VASP force calculations, collects forces, outputs phonon bands + DOS + thermodynamics. Use when user wants phonon dispersion, phonon DOS, 声子谱/声子态密度, imaginary modes check, vibrational free energy, specific heat from phonons, or zero-point energy of a solid. The phonopy supercell is a physics convention — this skill generates it internally, do NOT use modeling's supercell for phonon inputs.
---

# vasp-phonon

## When to Use
Harmonic phonons of a periodic crystal. For molecular vibrations, use gaussian-agent instead.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **输入**：必须是 **原胞 primitive** POSCAR；**超胞与位移由 phonopy 在本 skill 内生成**。禁止用 **modeling** 预先搭好的声子超胞替代 phonopy 协议（见 frontmatter）。
4. **边界**：周期固体谐振声子用本 skill；分子振动不要用本 skill（走 Gaussian 等工作流）。

## Workflow
```
python {skill_dir}/scripts/run.py PRIMITIVE_POSCAR --work-dir ./phonon --supercell 3 3 3
```
1. phonopy generates displaced supercells
2. For each: VASP force calc (ISIF=2, IBRION=-1, NSW=1, high-ENCUT)
3. phonopy collects FORCE_SETS → bands, DOS, thermodynamics

## POTCAR 策略
- 默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

## Requires
- `phonopy` (pip install phonopy)
- Primitive-cell POSCAR (not a pre-made supercell — phonopy builds its own)

## Key Parameters
| Flag | Default |
|---|---|
| `--supercell a b c` | 2 2 2 |
| `--disp F` | 0.01 Å |
| `--mesh a b c` | 31 31 31 (for DOS) |
| `--band-path` | auto (HighSymmKpath) |

**Status**: SKILL.md complete; `scripts/run.py` + `scripts/phonopy_driver.py` pending Phase 4.

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
