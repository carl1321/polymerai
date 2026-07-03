---
name: vasp-elastic
description: VASP elastic constants via stress-strain method (6 independent strains × 2 magnitudes = 12 calculations) using IBRION=6 + ISIF=3 or manual strain protocol. Computes C_ij stiffness tensor, bulk/shear/Young's moduli, Poisson ratio. Use when user wants elastic constants, stiffness tensor, bulk modulus, shear modulus, Young's modulus, Poisson ratio, mechanical properties, or 弹性常数/体弹模量/剪切模量. The 6×2 strain protocol is a physics convention — this skill generates it internally, do NOT use modeling skill for the strain set.
---

# vasp-elastic

## When to Use
Computes elastic tensor C_ij. Two methods:
- **VASP built-in**: `IBRION=6, ISIF=3, NFREE=2` (one calc, 6×2 internal strains)
- **Manual strain protocol**: 12 separate VASP runs on strained cells; more flexible (e.g. HSE elastic)

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **应变集**：6×2 应变由本 skill（`builtin` 或 `manual`）生成；**禁止用 modeling 或其它 skill 生成应变 POSCAR 列表**来代替本协议。
4. **边界**：输入一般为已弛豫 **CONTCAR**；需要 HSE 等弹性时用 `--method manual` 等文档选项，不要默认改写成非本 skill 支持的随意脚本链。

## Workflow (built-in)
```
python {skill_dir}/scripts/run.py CONTCAR --work-dir ./elastic --method builtin
```

## Workflow (manual)
```
python {skill_dir}/scripts/run.py CONTCAR --work-dir ./elastic --method manual
```
→ generates 12 subdirs under `./elastic/s01/ ... s12/`, each with a strained POSCAR; scheduler batches them.

## Physics note
The 6×2 strain directions are crystal-symmetry-reduced. See `references/strain_protocol.md` (pending) for the applied strain matrices.

## POTCAR 策略
- 每个应变任务默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

**Status**: SKILL.md complete; `scripts/run.py` + `scripts/strain_protocol.py` pending Phase 4.

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
