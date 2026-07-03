# Materials Domain Guide — 晶体 / 表面 / 缺陷 / 超胞

> 何时进入：用户要建**周期性体相、表面 slab、点缺陷、超胞、异质结**。
> 用法：先读这份，按场景拼 Recipe；参数取值查 `decision-rules.md`；工具能力查 `tools.md` / `tools-materials.md`。

---

## 1. 决策树

```
用户描述
├─ 体相晶体（"FCC Pt", "rocksalt NaCl"）         → §2 BulkBuilder
├─ 切表面（"Pt(111)", "ZnO(0001)"）               → §3 SlabTransform
├─ 重复扩胞（"3×3×1 supercell", "n-fold"）        → §4 SupercellTransform
├─ 点缺陷（空位 / 替位 / 间隙）                    → §5 DefectTransform [B0-P3 待实装]
├─ 异质结 / 界面（含 §3 + 异种 §2）               → §6 + interfaces.md
├─ 提供的 CIF / POSCAR                            → §7 文件读入
└─ 复杂场景（demo crystal, random alloy, twin）   → §8 工具 fallback
```

---

## 2. BulkBuilder — 体相晶体

**何时用**：
- 单元素 / 简单二元化合物，结构类型已知（fcc, bcc, hcp, rocksalt, …）
- 不知道结构类型 / 多元化合物 / 非常规相 → §7 文件读入

**最小 Recipe**：
```json
{"type": "builder", "name": "bulk", "params": {"element": "Pt"}}
```

**完整参数**：
- `element`：元素或化学式（"Pt", "NaCl", "MgO"）
- `crystalstructure`：`fcc`/`bcc`/`hcp`/`diamond`/`sc`/`rocksalt`/`cesiumchloride`/`zincblende`/`wurtzite`，None=ASE 自动
- `a`, `c`：晶格常数 (Å)，None=ASE 默认实验值
- `cubic=True`：返回常规立方胞（fcc 4 atom，bcc 2 atom），方便后续 supercell
- `orthorhombic=True`：hcp 转正交

**陷阱**：
- ASE 默认晶格常数是 0K 经验值，不一定匹配 DFT 优化结果。论文复现时 `a` 显式给。
- `cubic=True` 改变原子数和 supercell 行为。Pt fcc primitive=1 atom, cubic=4 atom；做 supercell 前确认。

---

## 3. SlabTransform — 切表面

**何时用**：从 bulk 切出特定密勒指数表面。

**最小 Recipe**：
```json
{"type": "transform", "name": "slab",
 "params": {"miller": [1,1,1], "layers": 4}}
```

**完整参数**：
- `miller`：(h, k, l)，整数三元组
- `layers`：层数（默认 4），按 `decision-rules.md §2` 取
- `vacuum`：切割时直接加真空 (Å)，**推荐留 None**，用单独的 `VacuumTransform` 控制（语义清晰）
- `periodic`：a/b 方向是否周期（默认 True）

**输出 PBC**：a/b 周期、c 取决于 vacuum。

**陷阱**：
- `surface()` 期待**常规胞**输入。primitive cell 输入会得到非直观切割。先 `bulk(..., cubic=True)`。
- 极性表面（ZnO 0001 / GaAs 110）默认非对称终止，重构需要额外脚本（B2 待）。
- 高指数面（>(3,1,1)）原子数膨胀很快，先估算。

---

## 4. SupercellTransform — 超胞

**何时用**：扩胞用于覆盖度控制、缺陷分离、k 点削减。

**两种输入形式**：
```json
// 对角扩胞（最常见）
{"type": "transform", "name": "supercell", "params": {"matrix": [3, 3, 1]}}

// 一般 3×3 矩阵（reshape，例如 √3×√3 R30°）
{"type": "transform", "name": "supercell",
 "params": {"matrix": [[2,1,0],[-1,1,0],[0,0,1]]}}
```

**取值**：见 `decision-rules.md §3`、`§8`。

**陷阱**：
- 对 slab 做 supercell：第三维（法线）一定 1，否则会复制真空层。
- 一般矩阵的行列式 = 新原子数 / 旧原子数。先算一遍再用。

---

## 5. DefectTransform — 点缺陷  ⚠ B0-P3 待实装

**计划接口**（实装前供 LLM 参考）：
```json
{"type": "transform", "name": "defect",
 "params": {"kind": "vacancy", "element": "Cu", "n": 1}}
```

**支持类型**：`vacancy`（空位）、`substitution`（替位，加 `replace_with`）、`interstitial`（间隙，加 `position`）。

实装前的 fallback：用 Atomsk (`-rmatom` / `-substitute`) 直接处理 POSCAR，再 `convert` 回流。

---

## 6. 异质结 / 界面

简单堆叠（同晶系 in-plane 匹配）走 `interfaces.md`。
跨晶系 / lattice mismatch 大 → VASPKIT 804 / pymatgen `Interface` / 手动 Recipe（B2）。

---

## 7. 文件读入（用户给 CIF / POSCAR）

CLI：
```bash
python modeling_cli.py convert -i input.cif -o output.poscar
```

Recipe 中读入 → 后续做 transform：当前没有 `read` builder，临时方案是先 `convert` 出 POSCAR，再起一个新 Recipe 不带 builder（pipeline 接收一个外部输入）。**B0-P3** 会引入 `bulk` 的 `file:` 源支持：
```json
{"type": "builder", "name": "bulk", "params": {"file": "input.cif"}}
```

---

## 8. 工具 fallback

| 任务 | 主路线 | Fallback |
|---|---|---|
| 体相 + 复杂结构 | BulkBuilder + ASE | PyXtal 随机晶体 |
| 高对称切面 | SlabTransform + ASE surface | VASPKIT 803 |
| 一般矩阵 supercell | SupercellTransform + ASE make_supercell | VASPKIT 401, Atomsk |
| 点缺陷 | DefectTransform [待] | Atomsk -rmatom |
| 位错 / 晶界 | — | Atomsk |
| 随机合金 (SQS) | — | VASPKIT 802 |
| 异质结匹配 | 手动 Recipe + B2 script | VASPKIT 804 |

---

## 9. 常见 Recipe 范式

**清洁金属表面**（Recipe 1，已验证）：
```
bulk(cubic) → slab → supercell(in-plane) → vacuum
```

**金属 + 吸附**（Recipe 2，待 B0-P2）：
```
bulk → slab → supercell → adsorbate → vacuum
```

**金属空位**（Recipe 4，待 B0-P3）：
```
bulk → supercell → defect(vacancy)
```

**氧化物表面 + 修饰**（B2 复合）：
```
bulk(file=cif) → slab → script(saturate_dangling_bonds) → vacuum
```

---

## 10. 输出选择

- DFT (VASP)：`.poscar` / `POSCAR`，记得 `selective_dynamics` 通过 `decision-rules.md §2` 固定底层
- DFT (其他)：`.cif`（pymatgen 接得住）
- MD：取决于体系，纯固体一般不在这条路线（→ `solvation.md`）
- 可视化：`.xyz`（OVITO/VMD/Ovito）

---

## 维护说明

- 新增 builder/transform 时同步在 §2-§5 增段
- 对应实现状态变化（待实装 → 已实装）要更新 ⚠ 标记
- 实装中的接口变更（如 defect 接口）要保持本文档与 Recipe schema 一致
