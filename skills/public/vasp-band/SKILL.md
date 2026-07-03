---
name: vasp-band
description: VASP electronic band structure calculation. Generates a k-path via pymatgen's HighSymmKpath, runs a line-mode NSCF from a precomputed SCF CHGCAR, and outputs a band structure suitable for plotting. Use when user wants band structure, band gap from band plot, CBM/VBM locations, direct/indirect gap classification, or 能带结构/能带计算/带隙. Requires a preceding vasp-scf run (provides CHGCAR). Do NOT use for total DOS (vasp-dos) or orbital-projected DOS alone.
---

# vasp-band

## When to Use
User wants a band structure (E(k) along high-symmetry path). Typical: "算 Si 的能带", "band structure of MoS2", "plot CBM/VBM".

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **依赖**：必须先完成 **vasp-scf** 且 `--scf-dir` 指向含 **CHGCAR** 的目录；`--scf-dir` 与能带输入 **POSCAR/CONTCAR 晶胞必须与 SCF 一致**（同一套网格），禁止跳步或混用未收敛电荷密度。
4. **边界**：沿高对称路径的 E(k) 只用本 skill；均匀网格态密度用 **vasp-dos**，不要混用。

## Workflow
```
# 1) relax and SCF first
python vasp-relax/scripts/run.py POSCAR --work-dir ./relax
python vasp-scf/scripts/run.py ./relax/CONTCAR --work-dir ./scf

# 2) band NSCF (uses ./scf/CHGCAR)
python vasp-band/scripts/run.py ./relax/CONTCAR --work-dir ./band --scf-dir ./scf
```

Internally:
1. Build KPOINTS via `HighSymmKpath` (physics protocol — stays inside this skill)
2. INCAR uses ICHARG=11 (read CHGCAR), ISMEAR=0, LORBIT=11
3. Copy CHGCAR from `--scf-dir`
4. Run VASP with handler loop
5. Parse → emit `band_structure.json` (eigenvalues per k-point + kpath labels)

## POTCAR 策略
- 默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

## Key Parameters
| Flag | Default | Meaning |
|---|---|---|
| `--scf-dir DIR` | required | directory containing CHGCAR (from vasp-scf) |
| `--line-density N` | 20 | k-points per reciprocal Å along path |
| `--nbands N` | auto | override NBANDS |

## Output
`band_structure.json` is the input format for `vasp-analysis band` (sumo/pymatgen plotter).

## Related Skills
- vasp-scf (upstream, mandatory — provides CHGCAR)
- vasp-analysis (downstream — makes the plot)

## Reference
- `references/kpath.md` — HighSymmKpath conventions, Seekpath vs. Setyawan-Curtarolo

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
