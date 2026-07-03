# vasp-skills 共享约定

所有 skill 的 `scripts/run.py` 都遵循以下约定，这样用户学会一个就能用全部。

## 命令行接口

```
python {skill}/scripts/run.py POSCAR [options]
```

所有 skill 接受的公共参数：

| 参数 | 含义 | 默认 |
|---|---|---|
| `POSCAR` | 结构文件（位置参数） | 必填 |
| `--work-dir PATH` | 工作目录（本地 / 远程创建） | `./{skill_type}` |
| `--incar PATH` | 用户提供的 INCAR（覆盖默认） | 无，用内置默认 |
| `--potcar PATH` | 用户提供的 POTCAR | 自动调 `vasp-potcar` 生成 |
| `--kpoints PATH` | 用户提供的 KPOINTS | 自动生成 |
| `--executor {local,ssh,scnet}` | 执行器 | 读 config（共享 `config.yaml` 默认 `executor: scnet`） |
| `--config PATH` | 配置文件路径 | `/mnt/skills/public/_shared-vasp/config.yaml` |
| `--dry-run` | 只生成输入不提交 | off |
| `--no-handlers` | 关闭错误自动纠错 | off |
| `--max-errors N` | 单次最多重试次数 | 5 |

每个 skill 可以额外加 skill 特有参数（见其 SKILL.md）。

## 工作目录结构

`run.py` 运行后 `--work-dir` 下：

```
{work_dir}/
├── INCAR           # 生成或用户提供
├── POSCAR          # 拷贝自输入
├── POTCAR          # vasp-potcar 生成
├── KPOINTS         # 生成或用户提供
├── submit.sh       # HPC 脚本
├── run.log         # 本地执行日志
├── .calc_runtime/  # 中间状态
│   ├── progress.json  # 统一状态快照
│   ├── events.jsonl   # 事件流
│   ├── job.json       # 任务元数据（job_id, executor, attempts）
│   └── history/       # 错误纠错历史快照
└── （执行后 VASP 产出：OUTCAR / OSZICAR / CHGCAR / WAVECAR / vasprun.xml）
```

## 退出码

| code | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 用户错误（缺少输入、配置错） |
| 2 | VASP 收敛失败，纠错已尽 |
| 3 | HPC 执行错误（SSH/排队/超时） |
| 4 | 未知 VASP 错误 |

## 配置文件

`/mnt/skills/public/_shared-vasp/config.yaml`，见 `_shared-vasp/config.template.yaml`。

## POTCAR 协作

每个 skill 不内嵌 POTCAR 生成。`_lib/potcar.py` 负责：
1. 若用户提供 `--potcar` 则直接用
2. 否则 shell-out 到 `vasp-potcar` skill 的 CLI（若已安装）
3. 否则回退到 `pymatgen.io.vasp.Potcar`（需 `PMG_VASP_PSP_DIR` 环境变量）

## 输入契约

- POSCAR 必须是已由 `modeling` skill 构建的合理结构（包括 defect supercell、slab、bulk 等）
- 计算方法特定的结构协议（phonon 位移、elastic 应变、band k-path）在 skill **内部**完成，不走 modeling

## 实测固化的约束（2026-04-26 更新自 BUGFIX_LOG.md）

以下规则在真实计算中触发过 bug，已修复并固化为约定：

### SSH executor — 文本 vs 二进制
- `_TEXT_EXTS` **严禁包含空字符串**：空串会匹配所有无扩展名文件，把 `CHGCAR/WAVECAR/OUTCAR` 这类二进制当作文本做 CRLF 转换，破坏内容。
- 文本文件 CRLF→LF 后，必须把 `len(normalized)` 作为 `file_size` 传给 `sftp.putfo()`，否则 paramiko 用原始大小校验会报 `size mismatch in put`。
- `INCAR/POSCAR/POTCAR/KPOINTS/submit.sh` 等无后缀文本文件走 `_TEXT_NAMES` 白名单，不靠扩展名兜底。

### 远端 work_dir 命名
- `_resolve_remote_work` **不能只取本地末级目录名**：多结构并行 (`<mat_A>/relax`、`<mat_B>/relax`) 会全部映射到同一远端 `/<root>/relax`，互相覆盖。
- 约定：远端目录用本地路径**末两级**拼接：`<parent>_<leaf>`（例 `D:/.../C/relax → vasp_agent/C_relax`）。

### custodian handler 的工作目录
- custodian 内置 handler 用 `./INCAR` 等相对路径，假设进程已 `chdir` 到 VASP 工作目录。
- runner.py 在调用 `bundle.check_and_correct()` 前必须 `with _cwd(work_dir):`，否则 handler 找不到 INCAR。

### vasp-band — 原胞 vs 输入晶胞
- k-path 必须用 `SpacegroupAnalyzer.get_primitive_standard_structure()` 生成（HighSymmKpath 只对原胞正确）。
- 但 **POSCAR/INCAR/CHGCAR 必须沿用上游 SCF 的同一晶胞**，否则 NSCF 读 CHGCAR 时网格不匹配，VASP 报 `charge density could not be read`。
- 约定：`build_band_inputs(structure, ...)` 用原始结构；`HighSymmKpath(prim)` 仅用于写 KPOINTS。

### slab POTCAR 排序
- `pymatgen.SlabGenerator(symmetrize=True)` 按终止层分组，生成的 POSCAR 可能出现重复 species 行（例 `Li Zr Cl Li Zr Cl`），与 POTCAR 的 species 数不一致。
- 调用方在写 POSCAR 前必须 `structure.get_sorted_structure()` 合并同种元素行。

### vasp-defect 的 supercell 来源
- defect 结构由 `modeling` skill 构建并通过 `<defect_poscar>` 传入；vasp-defect 不生成 vacancy/interstitial。
- 形成能曲线 E_f(q, E_F) 由 vasp-defect 内部计算；Freysoldt/Kumagai 修正需 LOCPOT + `pymatgen.analysis.defects`，目前作为外部后处理，结果通过 `--e-corr 'q=value'` 注入。Makov-Payne 一阶修正在 skill 内置（需 `--epsilon`）。

### 编排约束（新增固化）

- executor 选择必须来自项目 config / profile / CLI override；通用 workflow 与示例脚本不得硬编码 `ssh`。
- downstream stage 继续前，必须同时满足：
  - 上游 returncode 为 0；
  - 上游关键产物存在（如 `CONTCAR`、`CHGCAR`、完整的 `disp-*` 结果）；
  - 若上游写 `summary.json`，其 `success` / `ready_for_downstream` 语义不得与 returncode 冲突。
- `vasp-band` 的下游可消费条件应以 `ready_for_downstream` 为准，而不只是“VASP 跑过了”。
- `vasp-phonon` 的 `collect` 不允许在位移只完成一部分时继续；必须校验 `completed_displacements == expected_displacements`。
- 对超过 5 分钟的远端轮询，executor 应输出一次结构化摘要，并在 `.calc_runtime/events.jsonl` 记录 `long_wait_notice`，提示用户远端作业会继续运行，可关闭对话。

## 典型 workflow recipe

- `relax -> scf -> band`
  - `band` 读取 `relax/CONTCAR` 与 `scf/CHGCAR`
  - 只有当 `scf` returncode 为 0 且 `CHGCAR` 存在时才继续
- `relax -> phonon(prepare -> run -> collect)`
  - `phonon` 输入应来自 relaxed primitive cell
  - `collect` 只在所有 `disp-*` 均完成后运行
- 多分支并行只允许发生在前驱产物已经明确落盘之后；“并行”不等于“跳过依赖”。

## 子 skill 子进程契约（用于 vasp-batch 等编排者）
- 每个 skill 的 `scripts/run.py` 都是同步阻塞——只在 VASP 实际跑完（local 直接、HPC 轮询完成）后才退出，stdout 末尾 print 一份 JSON summary，并写入 `<work-dir>/summary.json`。
- 编排脚本应：
  - `subprocess.run(...)` 同步调用，按 returncode 判定是否继续；
  - 在每段开始/结束打 banner（含时间戳与耗时），便于 agent 不必另行 tail 子日志；
  - 把每段 `summary.json` 汇入顶层 `summary.json`。
- 不允许子 skill 把 VASP 作业扔到后台后立即返回——这会让上游误以为成功并继续提交下一段。
