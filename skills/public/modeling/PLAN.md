# modeling — 迭代补全计划

> 这份计划由一次架构讨论产出，目标是在**保持 modeling 单一 skill 不拆分**的前提下，深化能力、补齐占位实现、增加复合场景表达力。本文件是后续实施 CLI 的 onboarding 文档，同时合并了原 `TODO_REFACTOR.md` 的未完成任务清单。

---

## 实施进度（实时维护）

| 工作包 | 状态 | 备注 |
|---|---|---|
| **B0-P1** bulk + supercell + slab + vacuum | ✅ 完成 (2026-04-24) | ASE 后端实装；`tests/test_cli_recipes.py` 4 项绿；Recipe 1 端到端通过 |
| **B0-P2** adsorbate；box + filler/Packmol | ✅ 完成 (2026-04-24) | adsorbate (ASE add_adsorbate)、box（统一 Å）、filler（Packmol 后端 + density→count）；Recipe 2 端到端绿；Recipe 3 测试随 Packmol 可用性自动 skip |
| **B0-P3** defect；molecule file 源 | ⏳ 待开始 | 对应 Recipe 4 / 5 / 6 |
| **B1** references 分组 + decision-rules | ✅ 完成 (2026-04-24) | 5 个 doc + SKILL.md 路由 |
| **B2** scripts/ + Recipe `script` 类型 | ⏳ 待开始 | 等 B0 / B1 后做 |

### B1 子任务进度

| 文件 | 状态 |
|---|---|
| `references/decision-rules.md` | ✅ 完成 (2026-04-24)  — 11 节经验规则 |
| `references/materials.md` | ✅ 完成 (2026-04-24) — 决策树 + 4 个核心 builder/transform 详解 |
| `references/molecular.md` | ✅ 完成 (2026-04-24) — 来源决策 + SMILES/PDB fallback + 多分子组装路线 |
| `references/solvation.md` | ✅ 完成 (2026-04-24) — region/数量·密度/Recipe 4 范式/离子计算/陷阱 |
| `references/interfaces.md` | ✅ 完成 (2026-04-24) — 跨域识别/参数耦合/5 个范式/script 门槛 |
| `SKILL.md` Step 3 路由段落 | ✅ 完成 (2026-04-24) — 加 Domain Guide Routing 表 |

---

## Part 1 — Onboarding：你需要先知道的事

### 讨论背景摘要

讨论从一个架构问题出发："modeling 是否应该按"功能点"原子化拆 skill（每个 transform 一个 skill）？"

经过多轮分析，结论是 **modeling 不应该按 transform 拆 skill**，理由：

1. **Recipe pipeline 已经在数据层完成了原子化**——每个 step 就是一个原子操作，再在 skill 层切碎是过度设计
2. **"单元"封装价值低**——每个 transform 几乎是一次函数调用，没有复杂内部状态。封装价值低而接口成本高，硬拆会暴露大量 skill 间接口而没封装到任何东西
3. **跨单元参数全局耦合**——固液界面、纳米管+流体这种复合任务，参数是相互制约的（盒子大小→水分子数→密度），需要全局视角的 planner
4. **声明式 pipeline 是 coherent workflow**——按 Anthropic 官方原则 "merge skills only if they're so small they fragment a coherent workflow"，Recipe 流程不该被切碎

但讨论也发现 modeling 当前实现存在三类问题需要补：

- **B0**：很多 builder/transform 还是占位 stub（详见 Part 2 §B0）
- **B1**：references/ 没有按领域分组，且缺少决策知识库
- **B2**：Recipe schema 表达不了复合操作（断键补全、Packmol 双区、纳米管嵌入等）

### 关键决策（不要推翻）

1. **不拆 skill，保持 modeling 为单一 skill**
2. **保留 Recipe JSON + CLI 作为 LLM 主交互方式**——不要让 LLM 写 Python 调 modeling Python API。SKILL.md 明确写着 "Do NOT write multi-line Python imports — the Recipe format is the sanctioned interaction path."
3. **复合操作通过 scripts/ + Recipe 新 step 类型解决，不是 LLM 写 Python**——复用 Anthropic excel skill 的模式：skill 提供预制参数化脚本，LLM 在 Recipe 里调用
4. **references 按领域分组（progressive disclosure）**：LLM 按用户意图按需 Read 对应领域文档，不全量加载
5. **decision-rules.md 是最高领域价值产出**——把材料/化学的经验规则编码成 LLM 可读的决策规则

### 注意事项与陷阱

- **不要变成"教 LLM 写 ASE/pymatgen 代码"的 skill**：那是命令式架构，和官方 git/excel skill 路线类似。modeling 选择的是声明式 Recipe 路线，两者不要混
- **不要扩 Recipe schema 到 if/else/loop**：声明式的优势是可重现性和 schema 校验，加控制流就退化成"伪代码"。复杂控制流应该写在 scripts/ 里，Recipe 只调脚本
- **scripts/ 里的脚本必须参数化、确定性**：LLM 不写脚本，只填参数。脚本作者对正确性负责
- **B0 是前置任务，不能跳过**：references 写得再好，如果 builder 是占位 stub，所有引用都是空头支票
- **decision-rules.md 不要写成"教科书"**：写成 LLM 决策时直接可用的"if 用户做 X 则参数选 Y"形式，不是综述
- **跨领域协作通过对话上下文，不是新 skill**：固液界面就是 modeling 内部 Pipeline 的连续步骤，不要因为"涉及多个领域"就觉得要拆
- **保持 SKILL.md 精简**：按 Anthropic best practice，SKILL.md 是 process steps + references 路由表，不是教程

### 与其他 skill 的关系

| Skill | 关系 |
|---|---|
| `vasp-skills/*` | 下游：modeling 输出 POSCAR，VASP skill 接收 |
| `vasp-defect` | modeling 必须能生成缺陷 supercell（B0 P3） |
| `vasp-phonon` | modeling 提供 primitive cell，phonopy 内部的 supercell 不调 modeling |
| `gaussian-agent` | 平行：modeling 写 .gjf 坐标，gaussian-agent 加 route/basis |

### 与之前讨论中"另一段对话"的关系

讨论中曾参考一段先前 IDE agent 对 modeling 的分析，那段对话的部分结论是错的（推荐"LLM 写 Python 调 API"路线），违反了 SKILL.md 的明确契约。**本计划不采纳那段建议**。本计划走"声明式 Recipe + scripts 逃生通道"的混合路线，更接近官方 excel skill 模式。

### 项目背景：v0.8 已完成

v0.8（2026-04-20 landing）已经完成的工作（详见 `references/design.md §9 Design Decisions Log`）：

- SKILL.md 重写为 Recipe JSON + CLI 模式，QM 触发词全部移除
- `modeling_cli.py` 落地（run / convert / validate / tools / list 五子命令）
- `references/recipes.md` 重写为 6 个可运行模板
- `references/tools-qc.md`、`references/ts-builder.md` 移至 `docs/`（不再加载到 skill 上下文）
- `D:\code\.claude\skills\modeling\` 改为指向 `D:\code\modeling\` 的 junction，单一源头

本计划是 v0.8 之后的延续：骨架和契约已定，接下来是**补齐实现 + 深化领域知识 + 扩展复合场景**。

---

## Part 2 — 实施计划

### 目标

按"单一 skill + 内部分层 + 决策知识库 + scripts 逃生通道"方向迭代。三个工作包：

- **B0（前置）**：补齐 builders/transforms 占位实现
- **B1**：references 按领域分组 + 决策知识库
- **B2**：引入 `scripts/` 与 Recipe `script` 步骤类型

---

### B0 — 补齐核心 builder/transform 实现（前置）

#### 核心阻塞

`modeling_cli.py run` 子命令能加载 Recipe 并走通 Pipeline 调度，但绝大多数 builder / transform 的 `build()` / `apply()` 只返回占位结构（`Structure(positions=np.zeros((0,3)), ...)`）。需要真正的后端实现。

#### 占位文件现状

| 模块 | 文件 | 状态 |
|------|------|------|
| builder | `modeling/builders/bulk.py` | ✅ 已实现 (ASE bulk, B0-P1) |
| builder | `modeling/builders/filler.py` | ✅ 已实现 (Packmol 后端, B0-P2) |
| builder | `modeling/builders/molecule.py` | 占位 |
| builder | `modeling/builders/box.py` | ✅ 已实现 (正交 Å 盒子, B0-P2) |
| builder | `modeling/builders/combinatorial.py` | 占位 |
| transform | `modeling/transforms/slab.py` | ✅ 已实现 (ASE surface, B0-P1) |
| transform | `modeling/transforms/supercell.py` | ✅ 已实现 (ASE repeat/make_supercell, B0-P1) |
| transform | `modeling/transforms/defect.py` | 占位 |
| transform | `modeling/transforms/adsorbate.py` | ✅ 已实现 (ASE add_adsorbate, B0-P2) |
| transform | `modeling/transforms/vacuum.py` | ✅ 已实现 (ASE add_vacuum, B0-P1) |
| transform | `modeling/transforms/mirror.py` | 部分占位 |

> B0-P1 完成：`tests/test_cli_recipes.py` 4 项端到端测试通过，Recipe 1 (Pt(111) slab) 可端到端跑通。

#### 优先顺序（对应 `references/recipes.md` 模板）

| 优先级 | 模块 | 对应 Recipe 模板 |
|---|---|---|
| P1 | `builders/bulk.py` + `transforms/supercell.py` | Recipe 4（Cu 空位基础） |
| P1 | `transforms/slab.py` + `transforms/vacuum.py` | Recipe 1（Pt(111) slab） |
| P2 | `transforms/adsorbate.py` | Recipe 2（CO/Pt(111)） |
| P2 | `builders/box.py` + `builders/filler.py` | Recipe 3（纯水盒子） |
| P3 | `transforms/defect.py` | Recipe 4 完整（Cu 空位） |
| P3 | `builders/molecule.py`（含 file 源） | Recipe 5、6（分子/界面） |

#### 交付规范

- **每项一个 PR**，附单元测试
- **实现完成一项就更新** `references/recipes.md` 的"已验证"标记
- **端到端回归测试**：在 `tests/` 下放一个 `test_cli_recipes.py`，对每个 recipe 模板跑 `modeling_cli.py run`，断言输出文件存在且 `validate --level 1` 通过

---

### B1 — references 按领域分组 + 决策知识库

新建/重组 `D:/code/modeling/references/`：

```
references/
├── tools.md                  # (保留) 工具能力总览 + 路由表
├── recipes.md                # (保留) 端到端模板
├── tools-materials.md        # (保留) 材料类工具详解
├── molecules.md              # (保留) 内置分子库
├── design.md                 # (保留) 完整技术规格（v0.8）
├── materials.md              # 【新】晶体/表面/缺陷/超胞 — domain guide
├── molecular.md              # 【新】分子建模 / fragment 组合
├── solvation.md              # 【新】溶剂化 / Packmol / 密度
├── interfaces.md             # 【新】固液界面、异质结、复合体系
└── decision-rules.md         # 【新】经验规则与默认值
```

**SKILL.md 改动**：在 Step 3 ("Plan the Build") 新增段落：

```
按用户意图加载对应 domain guide（按需 Read，不全量加载）：
- 晶体/表面/缺陷    → references/materials.md
- 分子/conformation → references/molecular.md
- 溶剂/MD 体系       → references/solvation.md
- 跨域复合           → references/interfaces.md
始终参考 references/decision-rules.md 选择默认参数
```

**decision-rules.md 内容示例**（最高领域价值产出）：

```markdown
## 固液界面建模
- 真空层：≥15 Å (AIMD) / ≥20 Å (静态 DFT)
- 水层厚度：≥10 Å 模拟 bulk water
- Slab 底层固定：≥2 层 (selective_dynamics)
- VASP 偶极校正：LDIPOL=.TRUE., IDIPOL=3
- k 点：表面方向 ≥3×3，法线方向 1

## 真空层方向约定
- ASE / pymatgen 默认 c 轴
- 多组分异质结时显式声明，不依赖默认

## Packmol 密度（300 K）
- 水 1.0 g/cm³
- 乙醇 0.789 g/cm³
- 离子液体查表

## Slab 层数选择
- 金属表面：4-6 层
- 半导体/绝缘体：6-8 层
- 包含吸附计算：底 2-3 层 fixed
```

---

### B2 — scripts/ 目录 + Recipe `script` 步骤类型

#### B2.1 引入 scripts 包

```
modeling/modeling/scripts/
├── __init__.py
├── base.py                       # ScriptStep 基类
├── saturate_dangling_bonds.py    # 切表面后用 H/OH 补断键
├── dual_region_pack.py           # Packmol 双区填充
├── nanotube_embed.py             # 纳米管嵌入指定轴
└── README.md                     # 贡献规范
```

每个 script 必须**参数化、确定性**。LLM 不写脚本，只在 Recipe 里调用并填参数。

#### B2.2 扩展 Recipe schema

修改 `modeling/modeling/recipe.py`：
- 新增 `add_script(name, **params)` 方法
- 解析时支持 `{"type": "script", "name": "...", "params": {...}}`

修改 `modeling/modeling/pipeline.py`：
- 类型分派增加 `"script"` 分支
- 注册表机制从 `modeling/scripts/` 加载脚本类（参考现有 builders/transforms 注册）

Recipe 示例（讨论中提到的复杂例子）：

```json
{
  "name": "SiO2_nanotube_dual_fluid",
  "steps": [
    {"type": "builder",   "name": "bulk",      "params": {"file": "SiO2.cif"}},
    {"type": "transform", "name": "supercell", "params": {"matrix": [4,4,1]}},
    {"type": "transform", "name": "slab",      "params": {"miller": [0,0,1], "layers": 6}},
    {"type": "script",    "name": "saturate_dangling_bonds", "params": {"capping": "OH"}},
    {"type": "transform", "name": "vacuum",    "params": {"thickness": 30.0}},
    {"type": "script",    "name": "nanotube_embed", "params": {"axis": "x", "radius": 5.0, "type": "CNT"}},
    {"type": "script",    "name": "dual_region_pack", "params": {"inside": "water", "outside": "ethanol", "density_in": 1.0, "density_out": 0.789}}
  ]
}
```

#### B2.3 references 文档同步

- `references/interfaces.md` 给"何时用 transform / 何时用 script"判断规则
- `references/recipes.md` 增加复合 recipe 范例（含 script 步骤）

---

### 可选：文档补充

- **`references/commands.md`**：完整 CLI 参数参考。当前靠 `--help` 顶住，argparse 的 help 够用，除非后续 CLI 参数变多再写
- **`references/decision-rules.md`** 的落笔时机：建议**在实现核心 transform 之后**再写，以免规则和实现错位（规则写"默认真空层 15 Å"但 transform 还没实现就尴尬）

---

### 关键文件

**新建**：
- `D:/code/modeling/references/{materials,molecular,solvation,interfaces,decision-rules}.md`
- `D:/code/modeling/modeling/scripts/{__init__,base,saturate_dangling_bonds,dual_region_pack,nanotube_embed}.py`
- `D:/code/modeling/modeling/scripts/README.md`
- `D:/code/modeling/tests/test_cli_recipes.py`（端到端回归）

**修改**：
- `D:/code/modeling/modeling/builders/*` 占位 builder（B0）
- `D:/code/modeling/modeling/transforms/*` 占位 transform（B0）
- `D:/code/modeling/modeling/recipe.py` — 增加 script 类型支持
- `D:/code/modeling/modeling/pipeline.py` — 增加 script 分派
- `D:/code/modeling/SKILL.md` — Step 3 增加 domain guide 路由说明
- `D:/code/modeling/references/recipes.md` — 增加复合 recipe 范例、更新"已验证"标记

---

### 实施顺序

1. **B0** 必须先做（builder 不实现，B1/B2 写的 doc 就是空头支票）
   - 按 P1 → P2 → P3 顺序，每项单独 PR + 单元测试
2. B0 完成后 **B1 与 B2 可并行**
3. B1 优先做 `decision-rules.md`（最高领域价值）
4. B2 优先做 `dual_region_pack.py`（复合场景最常用）
5. 最后补 `tests/test_cli_recipes.py` 端到端回归

---

### 验证方法

- **B0 验证**：`python modeling_cli.py run` 跑通 `references/recipes.md` 的 6 个示例，全部成功生成结构文件；`test_cli_recipes.py` 全绿
- **B1 验证**：fresh Claude Code session 输入"建 Pt(111) 上吸附水"→ LLM 应按 SKILL.md 路由读 `interfaces.md` + `decision-rules.md`，生成的 Recipe 真空层、底层固定、k 点等参数符合 decision-rules
- **B2 验证**：fresh session 输入复杂例子（SiO₂ + 纳米管 + 双流体）→ 生成包含 `script` 步骤的 Recipe，CLI 跑完产出可视化结构

---

### 风险与备注

- **B0 工作量不小**：builder 占位实现填充工作量大，如果优先级冲突可降级（先做 B1 + B2 的脚手架，builder 实现按 P 优先级排期）
- **scripts 易膨胀**：scripts 增长要节制，每加一个新 script 都问"能不能用现有 transform 组合实现"，避免 scripts/ 变成杂物间
- **不在范围**：modeling 设计文档 v0.7 Phase 4 LLM 集成、CG 建模、3D 可视化等远期路线项（见 `references/design.md §8 Roadmap`）

---

### 参考资源

- **当前实现**：`D:/code/modeling/modeling/`
- **设计哲学**：`D:/code/modeling/design.md`（高层决策总结）
- **完整技术规格**：`D:/code/modeling/references/design.md`（v0.8 full spec）
- **Skill 主入口**：`D:/code/modeling/SKILL.md`
- **Recipe 模板**：`D:/code/modeling/references/recipes.md`
- **配套 vasp-skills 拆分计划**：`D:/code/vasp-skills/PLAN.md`（独立推进）
- **Skill 设计原则**：[Anthropic Skill Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
