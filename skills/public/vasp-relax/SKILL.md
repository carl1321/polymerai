---
name: vasp-relax
description: VASP structure relaxation (geometry optimization) for crystals, slabs, and molecules. Use when the user wants to relax / optimize / minimize a structure with VASP, check IBRION/ISIF/EDIFFG choices, or get CONTCAR from a POSCAR. Keywords - relax, geometry optimization, ionic relaxation, 结构弛豫, 结构优化, CONTCAR, IBRION, ISIF, EDIFFG. In DeerFlow/bash always invoke `scripts/run.py` **without** `--wait` (detached submit + async_tasks poll only; never add `--wait`). Do NOT use for SCF-only (vasp-scf), band structure (vasp-band), or phonon displacements (vasp-phonon).
---

# vasp-relax

## When to Use

User wants to relax / optimize an atomic structure with VASP and obtain the converged CONTCAR + final energy. Typical asks:
- "帮我弛豫这个结构"
- "optimize Si bulk with VASP"
- "I need IBRION=2 geometry optimization"

## 模型硬约束（Agent rules）

1. **算力**：以 `/mnt/skills/public/_shared-vasp/config.yaml` 为准提交 VASP（默认 `executor: scnet`）。**禁止**使用本机 `local` 执行器提交生产任务；`vasp_skills_lib.runner` 在无 `VASP_SKILLS_ALLOW_LOCAL=1` 时会拒绝 `executor: local` 与 `--executor local`。不要假设在当前环境直接 `mpirun vasp_*`。
2. **赝势**：只通过本 skill 的 `run.py` → `vasp_skills_lib.potcar`（先 `vasp-potcar`，失败再 pymatgen，见 `.potcar_source`）。缺库时配置 `potcar.potcar_dir` 或 `PMG_VASP_PSP_DIR` / `VASP_PP_PATH`，禁止手拼 POTCAR 绕过流程。
3. **边界**：本 skill 只做几何弛豫。不要用它替代 vasp-scf（固定几何电荷密度）、vasp-band（沿路径 NSCF）、vasp-phonon（有限位移声子）。
4. **`--wait`（硬禁止）**：对话 / 沙箱里调用 `run.py` 时**不得**附加 `--wait`。本 CLI 仅支持 **detach 提交 + stderr DeerFlow envelope + 网关轮询**；加 `--wait` 会阻塞工具、破坏 `async_tasks` 捕获，且 `run.py` 会报错退出。用户口头要「等算完」时，说明由对话长任务与 `poll.py`/网关轮询负责。

## Inputs

- `POSCAR` — the starting structure (build it with the `modeling` skill first if needed).
- Optional `INCAR` — if not given, MPRelaxSet defaults are used; generate with `vasp-incar` skill for finer control.
- Optional `KPOINTS` — otherwise MPRelaxSet default.
- HPC config at `/mnt/skills/public/_shared-vasp/config.yaml` (see `_shared-vasp/config.template.yaml`).

## Workflow

Default (**async submit**, non-blocking — DeerFlow `async_tasks` + gateway poll):

```
python {skill_dir}/scripts/run.py POSCAR --work-dir /abs/path/to/relax [--config ...]
```

1. Build inputs (INCAR/KPOINTS/POTCAR) under `work_dir`.
2. **Enqueue** remote/HPC job only (`vasp_skills_lib.runner.submit_job_only`) — does not wait for VASP to finish.
3. Print a **DeerFlow async envelope** (JSON) on **stderr** as the final line of process output so the gateway capture sees `status=submitted` + `poll_command` pointing at `scripts/poll.py`.
4. Background polling runs `poll.py` (same `work_dir`), which `fetch`es outputs when the scheduler job completes, then emits one-line JSON (`completed` / `failed` / `running`) for the dispatcher.

（不再支持在单进程内阻塞等到 VASP 结束；**不要**在文档或命令里出现 `--wait`。）

## Key Parameters

| Flag | Purpose | Default |
|---|---|---|
| `--isif N` | 1/2 ions-only, 3 full cell, 4 shape+ions | 3 |
| `--ibrion N` | 1 RMM, 2 CG, 3 damped MD | 2 |
| `--ediffg X` | force tolerance (eV/Å, negative) or energy (positive) | -0.02 |
| `--nsw N` | max ionic steps | 100 |
| `--encut N` | plane-wave cutoff (eV); defaults from POTCAR max × 1.3 | auto |

See `references/parameters.md` for guidance on each.

## Outputs

- `{work_dir}/CONTCAR` — relaxed structure
- `{work_dir}/OUTCAR`, `{work_dir}/vasprun.xml`
- `{work_dir}/.calc_runtime/history/attempt_*/` — per-iteration INCAR snapshots
- `{work_dir}/.calc_runtime/progress.json` / `events.jsonl` / `job.json` — unified runtime status
- stdout + `{work_dir}/summary.json` — final energy, converged flag, number of attempts

## Related Skills

- **modeling** — build the input POSCAR (supercell / slab / defect)
- **vasp-incar** — generate a hand-tuned INCAR
- **vasp-potcar** — POTCAR selection (invoked automatically)
- **vasp-scf** — next step after relax
- **vasp-analysis** — post-processing plots

## Reference

- `references/parameters.md`
- `references/examples.md`

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
