# Solvation Domain Guide — 溶剂化 / Packmol / 密度

> 何时进入：用户要建**溶剂盒子、混合溶剂、溶质浸入溶剂、表面湿润、含离子电解质**。
> 用法：选区域形状（§2）→ 算分子数（§3，密度查 `decision-rules.md §5-§6`）→ 写 Recipe（§4）→ 验证密度（§7）。
> 跨域（固液界面、纳米管嵌入）走 `interfaces.md`。

---

## 1. 决策树

```
要建的体系
├─ 单一溶剂盒子（"3 nm 水盒子"）                         → §4 Recipe A
├─ 溶质浸入溶剂（"1 个分子 + 100 个水"）                 → §4 Recipe B
├─ 多溶剂混合（"水 + 乙醇 1:1 混合盒子"）                → §4 Recipe C
├─ 含盐电解质（"1 mol/L NaCl 水溶液"）                   → §4 Recipe D + §6 离子计算
├─ 区域分隔的双流体（"管内水管外乙醇"）                  → interfaces.md + B2 script
└─ 表面 + 水（润湿）                                      → interfaces.md
```

---

## 2. 区域形状（FillRegion）

| 形状 | 参数 | 用途 |
|---|---|---|
| `box` | xmin/ymin/zmin/xmax/ymax/zmax (Å) | 主流；溶剂盒子默认 |
| `cylinder` | x, y, z1, z2, radius (Å)，沿 z 轴 | 纳米管内 / 孔道填充 |
| `sphere` | x, y, z, radius (Å) | 笼内 / 微滴 |
| 任意 region 的 `inside=False` | 排除区域 | 在固体周围填、避开 slab 区 |

复杂区域：把"主区域 + 多个 outside 排除区"组合。

---

## 3. 数量 vs 密度

**Recipe 二选一**（FillRequest 的 `count` 与 `density`）：

| 你知道的 | 让 Recipe 给 |
|---|---|
| 浓度 / 密度 | `density: 0.997`（自动算 count，需要 region 体积） |
| 精确数量 | `count: 1000`（密度由几何决定） |

**密度→数量公式**：

```
分子数 = V_region(Å³) × ρ(g/cm³) × Nₐ / (M(g/mol) × 10²⁴)
       = V × ρ × 0.6022 / M
```

例：3×3×3 nm³ 立方盒子（V = 27000 Å³）填水（ρ=0.997, M=18.015）：
`27000 × 0.997 × 0.6022 / 18.015 ≈ 900` 个水。

**密度查表**：见 `decision-rules.md §5`。
**容差影响有效体积**：见 `decision-rules.md §6`。

---

## 4. 经典 Recipe 范式（⚠ B0-P2 待实装；当前 Filler 仍为占位）

> 下方 Recipe 是 B0-P2 完成后的目标接口。**当前 Filler 不会真正调用 Packmol**，
> 落实前若需要真实溶剂盒子，请用 fallback：手写 packmol input 直接调 `packmol < input.inp`。

**Recipe A — 纯水盒子 3×3×3 nm**：
```json
{
  "name": "water_box",
  "steps": [
    {"type": "builder", "name": "box", "params": {"size": 3.0}},
    {"type": "builder", "name": "filler",
     "params": {
       "requests": [
         {"molecule": "water", "density": 0.997, "region": {"type": "box_full"}}
       ],
       "tolerance": 2.0
     }}
  ],
  "metadata": {"output": {"format": "gro", "filename": "water.gro"}}
}
```

**Recipe B — 1 溶质 + 100 水**：
```json
{
  "requests": [
    {"molecule": "/path/solute.xyz", "count": 1, "region": {"type": "box_full"}},
    {"molecule": "water", "count": 100, "region": {"type": "box_full"}}
  ]
}
```

**Recipe C — 双溶剂混合**（按 mol ratio）：
```json
{
  "requests": [
    {"molecule": "water",   "count": 500, "region": {"type": "box_full"}},
    {"molecule": "ethanol", "count": 500, "region": {"type": "box_full"}}
  ],
  "tolerance": 2.5
}
```
注意：molfraction 要换算成 count；混合溶剂的总密度近似按 ideal mixing。

**Recipe D — 1 mol/L NaCl 水溶液**：
```json
{
  "requests": [
    {"molecule": "water", "density": 0.997, "region": {"type": "box_full"}},
    {"molecule": "Na+",   "count":  6,   "region": {"type": "box_full"}},
    {"molecule": "Cl-",   "count":  6,   "region": {"type": "box_full"}}
  ]
}
```
（10×10×10 nm³ → 1L 体积 ≈ 1 nm³ × 6.02e23 / 1000 → 100³ Å³ × 1 mol/L → 6 ions per side. 自行换算。）

---

## 5. 输出格式

| 用途 | 格式 |
|---|---|
| GROMACS MD | `.gro` |
| LAMMPS MD | `.data`（拓扑由 Moltemplate 单独生成） |
| AMBER | `.pdb` + tleap |
| 通用 / 可视化 | `.pdb` |
| 不要直接给 VASP | Packmol 出来的盒子原子重叠、无收敛能；先 MD 平衡，再喂 DFT |

---

## 6. 离子 / 电解质

- **数量**：`N = c (mol/L) × V (L) × Nₐ`，把 V 用 Å³ 换算：`N = c × V(Å³) × 6.022e-4`
- **电中性**：阴阳离子总电荷必须为 0，体系才能跑 LAMMPS / GROMACS PBC；含蛋白质 / 带电固体时补反离子
- **水分子排挤**：每个离子 ≈ 排掉 1-2 个水（一阶近似），高浓度时要校正密度
- **离子模型**：modeling 内置 Joung-Cheatham（默认），Lennard-Jones σ/ε 在 `molecules.md`

---

## 7. 验证

填充后必查（CLI `--validate --level 2`）：

- **几何**：原子两两距离 ≥ tolerance（filler 内部已保证；外部输入 + filler 时要检查）
- **密度**：实际 = 总质量 / 盒子体积；与目标差异 < 5%
- **化学计量**：分子数 × 每分子原子数 = 总原子数（防漏分子）
- **PBC**：分子未跨周期边界（gro/pdb 输出前 `wrap`）

---

## 8. 边界与陷阱

- **Packmol 没有 PBC**：通过 tolerance 让分子离边 ≥ 2 Å；后续 MD 盒子等于 Packmol 盒子（不要再减 tolerance）
- **大盒子（> 10 nm）**：Packmol 慢；考虑分块填或用 GROMACS `gmx solvate`
- **小盒子（< 2 nm）**：水分子数过少，统计意义弱，密度有显著有限大小效应
- **熔盐 / 离子液体**：Packmol 默认 LJ 半径偏松，必要时降低 tolerance
- **极性溶剂 + 极性表面**：初始构型要避免分子定向偏置（Packmol 是随机的，足够多 step MD 即可）

---

## 9. 与其他 skill 的边界

- 力场参数 / 拓扑 → Moltemplate / GROMACS / AmberTools
- VASP AIMD 含水：modeling 出几何，vasp-incar / vasp-agent 加 `LDIPOL` / 时间步 / 系综
- LAMMPS 输入 → 单独 LAMMPS skill（如有）
- 溶剂介电常数 / 极化模型 → 力场层面的事，不在此

---

## 维护说明

- B0-P2（filler 实装）完成后：
  - 删除 §4 顶部的 "⚠ 待实装" 警告
  - 在 `recipes.md` Recipe 3 上加 ✅ verified 标记
  - 在 `tests/test_cli_recipes.py` 增加密度回归用例
- 新增溶剂查 `decision-rules.md §5`；不要在本文件里维护密度表
- region 形状增加要在 §2 同步更新
