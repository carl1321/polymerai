# Modeling Skill — 设计思路

> 本文件总结项目的**设计哲学和核心决策**。
> 完整技术规格见 `references/design.md`（v0.8）。
> 当前迭代计划见 `PLAN.md`。

---

## 项目定位

**自然语言驱动的原子尺度建模 skill**——把用户的物理/化学体系描述转换成 MD/DFT 仿真软件可读的坐标文件。

覆盖：晶体、表面、缺陷、超胞、多孔材料、溶剂化体系、异质结、分子结构。

不覆盖：计算方法参数（基组、k 点、赝势、力场参数）、运行作业、后处理——这些由 `gaussian-agent`、`vasp-skills/*`、`vasp-potcar`、对应分析 skill 负责。

---

## 核心设计决策

### 决策 1：保持单一 skill，不按功能拆分

经过架构讨论确认：modeling 不应该按 transform 拆成多个原子 skill（如 `slab-skill`、`supercell-skill`）。理由：

- **Recipe 已经在数据层完成原子化**——每个 step 就是一个原子操作，再在 skill 层切碎是过度设计
- **单元封装价值低**——每个 transform 几乎是一次函数调用，没有内部状态。封装价值低、接口成本高，硬拆只暴露大量接口而无封装收益
- **跨单元参数全局耦合**——固液界面、纳米管+流体这类复合任务，参数相互制约（盒子→水分子数→密度），需要全局 planner 视角
- **Pipeline 是 coherent workflow**——按 Anthropic 官方原则 "merge skills only if they're so small they fragment a coherent workflow"，Recipe 流程不该被切碎

判据来自一个自创框架"封装价值/接口成本比"：vasp-agent 比值高（适合原子化），modeling 比值低（适合单一）。

### 决策 2：Recipe JSON + 薄 CLI 是唯一 LLM 交互方式

LLM 不写 Python，只产出 Recipe JSON 然后调 `modeling_cli.py run`。理由：

- **可重现性**：Recipe 是完整规格，可 git diff、可分发、可复现
- **Schema 校验**：参数错误在生成时就能发现，不是跑一半崩
- **避免幻觉**：材料/化学库（ASE / pymatgen / Atomsk / Packmol）API 碎片化严重，让 LLM 自由写 Python 出错率高
- **领域经验固化**：pipeline / builders / transforms 里累积的隐式约定（PBC 方向、真空轴、selective_dynamics 默认）通过代码保留，不会随 LLM 自由发挥而丢失

这条决策**显式拒绝**了"教 LLM 写 ASE/pymatgen 代码"的命令式路线。

### 决策 3：复合操作通过 scripts/ + Recipe `script` step 解决

Recipe schema 表达不了的复合操作（断键补全、Packmol 双区、纳米管嵌入），通过预制参数化脚本 + Recipe 新 step 类型解决。**LLM 不写脚本，只在 Recipe 里调用并填参数**。

参考 Anthropic 官方 excel skill 的模式——skill 提供脚本库，LLM 是脚本的使用者。

显式拒绝的两个反方案：
- ❌ 给 Recipe 加 if/else/loop —— 会退化成"伪代码"，丢失 schema 校验和可重现性
- ❌ 让 LLM 写 Python 调 modeling Python API —— 违反决策 2

### 决策 4：references 按领域分组 + 决策知识库

利用 progressive disclosure：SKILL.md 不全量加载所有领域文档，而是按用户意图路由 LLM 去读对应 references：

- `materials.md` 晶体/表面/缺陷
- `molecular.md` 分子建模
- `solvation.md` 溶剂化/MD
- `interfaces.md` 跨域复合
- `decision-rules.md` 经验规则与默认值（最高领域价值产出）

`decision-rules.md` 是关键——把"真空层 ≥15 Å"、"水密度 1.0 g/cm³"、"slab 底层固定 2 层"这类经验编码成 LLM 可读的决策规则。

### 决策 5：单一源 + Junction

`D:/code/modeling/` 是唯一源，`.claude/skills/modeling/` 是指向它的 Windows junction，避免双副本漂移。

---

## 架构分层

```
User Layer       自然语言描述
   ↓
Skill Layer      SKILL.md 引导 LLM 产出 Recipe JSON
   ↓
CLI Layer        modeling_cli.py {run, convert, validate, tools, list}
   ↓
Recipe Layer     JSON 操作序列（可序列化、可编辑、schema 校验）
   ↓
Pipeline Layer   Builder/Transform/Script 顺序执行
   ↓
Build Layer      Builders（创建）+ Transforms（修改）+ Scripts（复合操作）
   ↓
Validator Layer  L1 几何 → L2 化学 → L3 物理
   ↓
Output Layer     结构文件 + 验证报告
```

每层职责单一，Recipe 层是 LLM 与系统的契约边界。

---

## 与其他 skill 的协作边界

| 上游 skill | modeling 接收 |
|---|---|
| 用户上传文件（.pdb/.xyz/.cif/.poscar） | 直接读 |

| modeling 输出 | 下游 skill 接收 |
|---|---|
| POSCAR | `vasp-skills/*` 跑各种 VASP 计算 |
| `.gjf`（仅坐标） | `gaussian-agent` 加 route/basis/charge |
| LAMMPS data / GRO | MD/Force Field skill |

**关键约束**：modeling 只输出坐标，**不**输出 INCAR/route/k 点/力场——这些是各下游 skill 的职责。

---

## 范围边界

**In scope**：晶体/表面/分子/溶剂化/异质结/缺陷的原子坐标生成与多种格式导出。

**Out of scope**（明确委派）：

| 不做 | 委派给 |
|---|---|
| 基组、Gaussian route、电荷/多重度 | `gaussian-agent` |
| INCAR / KPOINTS / POTCAR | `vasp-skills/*` / `vasp-potcar` |
| 力场参数化 | MD/Force Field skill |
| 跑作业 | workflow skill |
| 后处理 | analysis skill |

---

## 进一步阅读

- **完整技术规格**：`references/design.md` (v0.8) — 模块清单、扩展模板、依赖矩阵、决策日志
- **当前迭代计划**：`PLAN.md` — onboarding + B0/B1/B2 工作包
- **使用入口**：`SKILL.md` — LLM 操作手册
- **CLI 子命令**：`python modeling_cli.py --help`
