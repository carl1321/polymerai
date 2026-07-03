# Molecular Domain Guide — 分子建模 / Fragment 组合

> 何时进入：用户要建**离散分子、有机片段、装配产物（不含周期性体相、不含溶剂填充）**。
> 用法：先选分子来源（§1），再决定单分子 / 多分子组装（§2）；力场 / QM 参数走 `gaussian-agent`，本 skill 只产坐标。
> 内置分子库的**完整名单和电荷参数**见 `molecules.md`，本文件不重复列表。

---

## 1. 分子来源决策

```
分子描述
├─ 内置库已有（"water", "CO", "CH4"...）          → §2 MoleculeBuilder source=builtin
├─ ASE g2 库（"H2O", "C2H2", "CH3CH2OH"...）      → §2 MoleculeBuilder source=ase
├─ 用户提供 .xyz / .pdb / .gjf                     → §2 MoleculeBuilder source=file
├─ SMILES / InChI（小分子）                        → §3 SMILES → 3D
├─ 蛋白质 / 大分子（PDB ID）                       → §4 外部数据库
└─ 完全没有源（要画出来）                          → §5 不在 modeling 范围
```

**优先级**：内置库 > ASE g2 > 文件 > SMILES。
**`source: "auto"`** 会按这个顺序自动探测，绝大多数场景直接用 auto。

---

## 2. MoleculeBuilder

**最小 Recipe**：
```json
{"type": "builder", "name": "molecule", "params": {"name": "water"}}
```

**完整参数**：
- `name`：分子名 / 文件路径
- `source`：`auto` (默认) / `builtin` / `ase` / `file`

**返回**：单个 `Structure`，无 cell（独立分子），位于其本身坐标系。

**陷阱**：
- 内置库与 ASE g2 名字风格不同（`water` vs `H2O`）。`auto` 会找到，但写 Recipe 用 builtin 名（已在 `molecules.md` 列出）更稳定。
- 文件来源：相对路径相对 CLI 调用目录。Recipe 里建议绝对路径。
- 内置库的电荷已带（用于 MD），用于 DFT 时 vasp/gaussian 会忽略 charges 字段。

---

## 3. SMILES → 3D

modeling 当前**不内置 SMILES 解析**。两种 fallback：

1. **Open Babel CLI**（推荐）：
   ```bash
   obabel -:"CCO" -O /tmp/etoh.xyz --gen3d
   ```
   再用 `MoleculeBuilder(name="/tmp/etoh.xyz", source="file")` 引入。

2. **RDKit Python** —— 不写在 Recipe 里，让用户在 shell 跑 RDKit 后给文件。
   理由：RDKit 是命令式 API，不符合 Recipe 声明式约定。

**何时不要走 SMILES**：分子已有公认结构（小分子、常见溶剂）→ 直接 `source=builtin/ase`。

---

## 4. 大分子 / 蛋白质

- **PDB ID**：用 `wget https://files.rcsb.org/download/{PDB}.pdb` 下载，再 `MoleculeBuilder(file=...)`
- **去水 / 去配体**：本 skill 没做，建议用 PyMOL / VMD 处理后再喂入
- **力场 / 拓扑**：modeling 不产生拓扑，→ Moltemplate（LAMMPS）/ AmberTools / GROMACS pdb2gmx

---

## 5. 不在 modeling 范围

- 自由设计 / 从头画分子（→ 化学绘图工具：ChemDraw / MarvinSketch）
- 从反应路径生成产物结构（→ gaussian-agent 的 IRC）
- 蛋白结构预测（→ AlphaFold）
- 构象搜索（→ CREST / xTB / Conformator）

---

## 6. 多分子组装

modeling 当前的多分子组装路线：

| 场景 | Recipe 方法 |
|---|---|
| 几个固定位置的分子 | 多个 `molecule` builder + `Assembler`（坐标手动） |
| 随机均匀填充（有盒子） | `box` + `filler` （走 `solvation.md`） |
| 主客体复合（笼内单分子） | 手动定义 region + filler n=1 |
| 链 / 高分子（重复单元） | 使用 **`polymer-build`** skill（SMILES → PySoftK 链 → Packmol 装箱）；或 `modeling` 的 `box` + `filler` 仅做溶剂填充 |
| 分子晶体 | 走 `materials.md` (cif 文件) |

**Assembler**（builders/assembler.py，部分实现）：把多个独立 Structure 拼到一个盒子里，参数是位置矩阵。复杂场景目前推荐落到 `solvation.md` 走 Packmol。

---

## 7. 输出格式

| 用途 | 推荐 |
|---|---|
| Gaussian QM | `.gjf` (modeling 只写坐标) → 移交 `gaussian-agent` 加 route/basis |
| ORCA / NWChem | `.xyz` |
| MD 单分子模板 | `.pdb`（带残基 / 力场原子类型可选） |
| 可视化 | `.xyz` |
| 加入晶胞 / pbc 体系 | `.cif` 或 `.poscar` |

`.gjf` 输出**仅含坐标**，无 route / 基组 / 电荷自旋。需要完整 Gaussian 输入：调 `gaussian-agent` skill。

---

## 8. 常见 Recipe 范式

**单分子 → Gaussian 坐标**：
```
molecule(name="water") → 输出 .gjf
```

**多分子（已知坐标）+ 盒子**：
```
box(...) + 多个 molecule + Assembler → 输出 .pdb
```

**单分子 + 真空盒子**（孤立分子做 DFT 但需要 PBC）：
```
molecule → box(margin=10) → 输出 .poscar
```

**含分子的固液界面**（跨域）→ 见 `interfaces.md`。

---

## 9. 与其他 skill 的边界

- 路由 / 基组 / 电荷自旋 / 频率分析 → `gaussian-agent`
- 反应坐标 / TS guess（修改坐标方向）→ `gaussian-agent` 或 modeling 的 `sn2_ts` builder（特化场景）
- 分子动力学初构 → 走 `solvation.md` 的 Packmol 路线
- 力场参数 → modeling 不做

---

## 维护说明

- 内置库列表更新写到 `molecules.md`，本文件只引用
- 新增 SMILES / RDKit 集成（如果做）必须加在 §3
- Assembler 的实现完成度和 §6 表格保持同步
