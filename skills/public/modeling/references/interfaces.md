# Interfaces Domain Guide — 固液界面 / 异质结 / 复合体系

> 何时进入：体系**跨域**（晶体 + 分子 / 多种材料堆叠 / 含约束区域的填充）。
> 这是 modeling 表达力被推到极限的领域：单一 transform 不够、需要组合 + （未来）`script` 步骤。
> 用法：先识别域（§1）→ 复用各域 doc 的子流程 → 处理跨域参数耦合（§2）→ 必要时落到 `script`（§4）。

---

## 1. 跨域识别

| 体系 | 涉及域 | 关键耦合 |
|---|---|---|
| 金属表面 + 吸附分子 | materials + molecular | 吸附位置、覆盖度、真空层 |
| 金属表面 + 水溶剂（润湿 / 电化学界面） | materials + solvation | 水层厚度、真空层、表面终止 |
| 氧化物表面 + 修饰（OH / NH₂ / 烷链） | materials + molecular + 反应化学 | 断键补全、覆盖度、几何应变 |
| 二维材料异质结 | materials + materials | 晶格匹配、层间距、对齐 |
| 多孔材料 + 客体分子 | materials + solvation | 孔大小、客体进出可达性 |
| 纳米管 + 流体（管内 / 管外不同） | materials + solvation × 2 | 区域分隔、双密度、轴向对齐 |
| 蛋白质 + 膜 + 水 | molecular + solvation × 2 | 残基插入深度、双层取向 |

---

## 2. 跨域参数耦合（必读）

复合体系的"参数全局耦合"是为什么不该按"功能点"拆 skill 的核心理由。典型耦合：

### 盒子大小 ↔ 水分子数 ↔ 密度
建固液界面时三者只能定两个。Recipe 推荐：**先固定盒子（in-plane = supercell, 法向 = slab + water_layer + vacuum），再让 filler 按密度推分子数**。

### 真空层 ↔ 偶极校正 ↔ 镜像距离
- 表面 + 极性吸附（CO 立式吸附） → 真空 ≥ 18 Å + IDIPOL=3
- 表面 + 双侧水（电化学界面） → 真空可省略，但要 symmetric slab 避免净偶极

### 晶格匹配 ↔ 应变 ↔ supercell 大小
异质结 in-plane 用最小公倍数 supercell。失配 < 5% 直接锁一边；> 5% 要查 CSL 或换 method。

### 覆盖度 ↔ supercell ↔ 吸附能定义
覆盖度 = N_adsorbate / N_surface_site。改 supercell 时 N_site 改、Reference state 改、吸附能数值改。**Recipe 必须把 supercell 写在 adsorbate 之前**。

---

## 3. 经典 Recipe 范式

### A. 金属表面 + 吸附分子（CO / Pt(111)）  ⚠ B0-P2
对应 `recipes.md` Recipe 2，pipeline：
```
bulk(Pt, cubic) → slab(111, 4 layers) → supercell(3,3,1) → adsorbate(CO, top, 2.0Å) → vacuum(15)
```

### B. 固液界面（金属 + 水）
```
bulk → slab → supercell(in-plane) → vacuum(slab + water_layer + 12)
→ filler(water, region=box[z_slab_top : z_slab_top + water_layer], density=0.997)
→ selective_dynamics fix bottom 2 layers
```
（fix bottom 当前需要外部脚本或手动改 POSCAR；后续 transform 会原生支持。）

### C. 氧化物表面 + OH 修饰
切完表面有断键（dangling bonds）。三种处理：
1. **B2 `saturate_dangling_bonds` 脚本**（待实装）：自动找 undercoordinated 原子，加 H/OH
2. 用 Atomsk 后处理
3. 手写小 Python（不推荐，违反 SKILL.md "no multi-line Python"）

### D. 二维异质结（graphene / MoS₂）
```
bulk(graphene) → slab(0001, 1 layer)
bulk(MoS2)    → slab(0001, 1 layer)
[手动选 supercell 让两者 in-plane 失配 < 1%]
combine(stacking, distance=3.4Å) → vacuum(20)
```
combine 当前要 `combinatorial.py`（未实装），fallback 是 VASPKIT 804。

### E. 纳米管 + 双流体（管内水 / 管外乙醇）
单个 Recipe 表达不出来 "axis embed + region split"，必须落到 B2 script：
```
bulk(SiO2) → supercell → slab(001, 6) → script(saturate_dangling_bonds, OH)
→ vacuum(30) → script(nanotube_embed, axis=x, r=5, type=CNT)
→ script(dual_region_pack, inside=water, outside=ethanol, ρ_in=1.0, ρ_out=0.789)
```

---

## 4. 何时落到 `script`（B2）  ⚠ B2 待实装

判断规则（讨论决定的红线）：

| 判据 | 用 transform 组合 | 用 `script` |
|---|---|---|
| 单一原子操作？ | ✅ | ❌ |
| 需要状态机 / 内部分支？ | ❌ | ✅ |
| 参数 < 4 个？ | ✅ | （都行） |
| 需要在 Recipe 内表达 if/loop？ | （Recipe 不允许） | ✅ |
| 跨多种 region / 多次 Packmol 调用？ | ❌ | ✅ |
| 需要算几何（断键检测、轴向对齐）？ | ❌ | ✅ |

**新增 script 的门槛**：先问"能不能用现有 transform 组合"。能就别加，避免 scripts/ 杂物间。

---

## 5. 输出与下游

| 体系 | 推荐格式 | 下游 skill |
|---|---|---|
| 静态 DFT 界面 | `.poscar` | `vasp-incar` + `vasp-agent` |
| AIMD | `.poscar` | 同上，IBRION=0, MDALGO 等参数让 vasp-incar 加 |
| 经典 MD 界面 | `.gro` / `.data` | GROMACS / LAMMPS（拓扑另算） |
| 大体系预可视化 | `.xyz` | OVITO |

---

## 6. 验证

复合体系比单域更容易出问题，必须查：

- **整体几何**（CLI level 1）：原子重叠、跨边界
- **化学合理**（level 2）：键长合理、配位数对
- **物理合理**（level 3）：密度、固液界面无气隙、电中性
- **目视**：任何复合体系一定要 OVITO/VMD 看一眼

---

## 7. 与其他 skill 的关系

- DFT 参数（INCAR / KPOINTS / POTCAR）→ vasp-incar / vasp-potcar
- DFT 运行 / 错误恢复 → vasp-agent
- Gaussian QM 用于复合体系的子片段计算 → gaussian-agent
- 力场参数 / 拓扑 → 单独 MD skill
- 复合体系的后处理（界面密度分布、PMF）→ vasp-analysis 或 mdanalysis

---

## 维护说明

- §4 的判据要随 B2 实装演化（哪些 transform 可以组合替代 script，要更新）
- §3 各 Recipe 范式要标注实装状态；P2/P3 完成后去掉 ⚠
- 新增跨域类型先加到 §1 表，再考虑要不要单独建 doc
