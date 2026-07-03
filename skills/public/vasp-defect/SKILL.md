---
name: vasp-defect
description: VASP point defect formation energy calculation with charge-state scan and image-charge correction (Freysoldt / Kumagai). Input MUST be an already-built defect supercell — this skill does NOT generate defect structures. Use when user wants defect formation energy, charge transition levels, vacancy/interstitial/substitutional defect energetics, or 缺陷形成能/电荷态/空位/间隙. For building the defect supercell (vacancy generation, substitution, supercell size selection), first use the modeling skill.
---

# vasp-defect

## When to Use
Formation energy of a specific defect configuration across charge states:

$$E_f[D^q] = E[D^q] - E[\text{bulk}] - \sum_i n_i \mu_i + q (E_F + E_{VBM}) + E_{\text{corr}}$$

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：各电荷态子任务仍走 `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **几何**：缺陷超胞 **必须由 modeling 预先构建**；本 skill **不生成** vacancy / interstitial / 替位结构。bulk 能量目录 `--bulk-dir` 须与协议一致。
4. **边界**：形成能与电荷态扫描用本 skill；介电张量用于 Kumagai 等时上游用 **vasp-dielectric**，不要凭空虚造 ε 张量。

## Input Contract
User provides:
1. Relaxed **bulk** supercell total energy (from vasp-relax)
2. Defect supercell POSCAR — **built by modeling skill**
3. Chemical potentials μ_i
4. Desired charge states

## Workflow
```
python {skill_dir}/scripts/run.py DEFECT.poscar \
    --bulk-dir ./bulk \
    --charges -2 -1 0 +1 +2 \
    --mu Ga=-3.0 --mu N=-4.5 \
    --correction freysoldt --epsilon 10.4
```
Spawns one vasp-relax per charge state (`LVHAR=.TRUE.` auto-enabled when
`--correction freysoldt|kumagai`, so each run writes LOCPOT for alignment).

## POTCAR 策略
- 每个电荷态计算默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

## Image-charge corrections
| `--correction` | Needs | Computed |
|---|---|---|
| `none` | — | 0 |
| `makov-payne` | `--epsilon` (scalar), cubic supercell | inline, 1st order |
| `freysoldt` | LOCPOT (defect + bulk), `--epsilon`, optional `--defect-frac-coords` | `pymatgen.analysis.defects.corrections.freysoldt` |
| `kumagai` | `--epsilon-tensor` (3×3 from vasp-dielectric) | EFNV anisotropic, `pymatgen.analysis.defects.corrections.kumagai` |

You can also bypass auto-computation by passing precomputed values:
`--e-corr '+1=0.18' --e-corr '-1=0.21'` (overrides `--correction`).

## Related
- **modeling** (upstream, required) — builds the defect supercell
- **vasp-dielectric** (upstream, optional) — provides ε for Freysoldt/Kumagai
- vasp-relax (invoked internally per charge state)

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
