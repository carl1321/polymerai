# vasp-relax — 示例

## 1. Si 体相

```bash
# 先用 modeling 构建
modeling-cli bulk Si --output Si.poscar

# 弛豫
python vasp-relax/scripts/run.py Si.poscar --work-dir ./Si_relax
```

输出：
```json
{
  "success": true,
  "converged": true,
  "final_energy_eV": -10.84,
  "contcar": "./Si_relax/CONTCAR",
  "attempts": 1
}
```

## 2. Pt(111) slab，固定晶胞

```bash
modeling-cli surface Pt 1 1 1 --layers 5 --vacuum 15 --output Pt111.poscar
python vasp-relax/scripts/run.py Pt111.poscar --work-dir ./Pt111 --isif 2
```

## 3. 用用户自定义 INCAR

```bash
# 生成 INCAR（vasp-incar skill）
vasp-incar Si.poscar --type relax --output my.incar --encut 520

# 弛豫时用它
python vasp-relax/scripts/run.py Si.poscar --work-dir ./Si_hi --incar my.incar
```

## 4. 本地 dry-run 检查输入

```bash
python vasp-relax/scripts/run.py Si.poscar --work-dir ./check --dry-run
ls ./check/   # INCAR POSCAR POTCAR KPOINTS
```

## 5. 关闭错误自动纠错（调试用）

```bash
python vasp-relax/scripts/run.py Si.poscar --work-dir ./Si --no-handlers
```
