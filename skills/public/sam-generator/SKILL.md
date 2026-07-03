---
name: sam-generator
description: SAM 分子能力集：分子生成、分子可视化、性质预测。必须通过本 skill 提供的三个工具调用，禁止用 bash 或脚本执行。
group: agentic
---

# SAM 分子能力集（生成 + 可视化 + 性质预测）

## 重要：必须使用工具，禁止执行脚本

- **必须**使用以下三个工具完成 SAM 相关任务：`generate_sam_molecules`、`visualize_sam_molecules`、`predict_sam_properties`。
- **禁止**使用 bash 或命令行执行本 skill 的脚本
- 所有生成、可视化、性质预测**只能**通过调用上述三个工具完成。工具内部会调用脚本，你只需传参给工具。

---

## 1. 分子生成（仅用工具）

根据骨架 SMILES 和锚定基团生成自组装单分子层（SAM）分子。

- **工具方式**：调用 **`generate_sam_molecules`** tool，直接返回带有 SMILES 与骨架信息的文本结果。
- **数量规则（必须遵守）**：`gen_size` 默认值保持 10；但只要用户明确说“生成 N 个”，就必须显式传 `gen_size=N`，不能使用默认值替代用户要求。

工具使用示例（伪代码）：

```text
tool: generate_sam_molecules
inputs:
  scaffold_condition: "c1ccccc1"
  anchoring_group: "O=P(O)(O)"
  gen_size: 10
```

| 工具参数 | 必填 | 说明 |
|----------|------|------|
| scaffold_condition | 是 | 骨架 SMILES，多个用逗号分隔 |
| anchoring_group | 是 | 锚定基团 SMILES |
| gen_size | 否 | 生成数量，默认 10；若用户明确给出数量，必须按用户数量传入 |

---

## 2. 分子可视化（仅用工具）

将 SMILES 转为 2D 结构网格图，输出为 SVG 文件（例如 `/mnt/user-data/outputs/molecular_structure.svg`）。  
结果中**不要使用 Markdown 图片语法**（如 `![...](...)`）在页面内直接展示图片；只展示文件本身并提供下载。  

- **工具**：调用 **`visualize_sam_molecules`** tool，传入包含 SMILES 的文本（通常直接使用 `generate_sam_molecules` 的输出），工具内部会解析 SMILES 并生成 SVG 网格图。
- 生成后使用 `present_files` 呈现输出文件（例如 `molecular_structure.svg`），让前端以文件形式展示并可下载。

工具调用示例（伪代码）：

```text
tool: visualize_sam_molecules
inputs:
  smiles_text: "<generate_sam_molecules 的输出文本>"
  width: 800
  height: 600
```

| 工具参数 | 必填 | 说明 |
|----------|------|------|
| smiles_text | 是 | 包含 SMILES 的文本，直接传入 `generate_sam_molecules` 的完整输出即可 |
| width / height | 否 | 可选，默认 800×600 |

---

## 3. 性质预测（仅用工具）

预测分子的 HOMO、LUMO、偶极矩（DM）等性质。

- **工具**：调用 **`predict_sam_properties`** tool，传入包含 SMILES 的文本（可直接用 `generate_sam_molecules` 输出或用户提供的 SMILES 列表），工具内部使用 backend 的 Predictor 进行预测。

工具调用示例（伪代码）：

```text
tool: predict_sam_properties
inputs:
  smiles_text: "<generate_sam_molecules 的输出文本，或用户提供的 SMILES 文本>"
  properties: "HOMO,LUMO,DM"
```

| 工具参数 | 必填 | 说明 |
|----------|------|------|
| smiles_text | 是 | 包含 SMILES 的文本（生成工具输出或用户提供） |
| properties | 否 | 逗号分隔：HOMO,LUMO,DM，默认 HOMO,LUMO,DM |

---

## 典型流程（每一步都只调用工具）

1. **生成**：调用 `generate_sam_molecules`，得到带 SMILES 的文本。
2. **可视化**：调用 `visualize_sam_molecules`，将上一步的**完整输出文本**作为 `smiles_text` 传入（不要自己写 .smi 文件或跑脚本）。
3. **性质预测**：调用 `predict_sam_properties`，同样将生成结果的文本作为 `smiles_text` 传入。

> 注意：
> 1. 在回答中不要构造 `/api/threads/...` 形式的 URL，只使用 `/mnt/user-data/outputs/...` 等虚拟路径，由前端转换。
> 2. 不要在回复里内嵌图片（包括 Markdown 图片语法）；仅以文件路径 + `present_files` 的方式交付结果。 
