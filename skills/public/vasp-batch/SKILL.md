---
name: vasp-batch
description: High-throughput VASP workflow — apply the same calculation type (relax / scf / band / etc.) to a batch of POSCAR structures with scheduler coordination, failure isolation, and a summary table. Use when user wants to screen multiple materials, run the same calc on 10+ structures, high-throughput DFT, 高通量筛选/批量计算. The batch of structures should come from modeling (or a local directory).
---

# vasp-batch

## When to Use
Same VASP calc on N structures (N ≥ 5 typically). Individual failures don't block the batch.

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准；每个子结构仍由子 skill 的 `run.py` 经同一套 executor 提交（默认 SCNet）。除非用户明确要求本机调试，不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：子任务 POTCAR 仍由各子 skill 内 `vasp_skills_lib.potcar` 生成；缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR。
3. **编排**：必须通过 **本 skill 的 `run.py`** 调用子 skill（`--calc` + 可选 `--` 透传参数），以保留 handler / scheduler 行为；禁止自写 shell 循环直接 `mpirun` 绕过子 skill。

## Workflow
```
python {skill_dir}/scripts/run.py ./structures/*.poscar --calc relax --work-dir ./batch --parallel 10
```
Produces `batch/<name>/` per structure + `batch/summary.csv`.

## POTCAR 策略
- 批处理中的每个任务默认优先调用 `vasp-potcar` 技能生成 POTCAR。
- 仅当 `vasp-potcar` 不可用或执行失败时，才回退到 pymatgen 兜底逻辑。

**Status**: SKILL.md complete; run.py pending Phase 5.

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
