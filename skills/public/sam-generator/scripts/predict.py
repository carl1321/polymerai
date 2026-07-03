#!/usr/bin/env python3
"""
Predict molecular properties (HOMO, LUMO, DM) from SMILES. Run from skill dir.
Usage: python predict.py --smiles "CCO" [--smiles "CCCO"] --properties HOMO,LUMO,DM
   or: python predict.py --input /path/to/text.txt --properties HOMO,LUMO,DM
Uses skill-local lib (property_predictor), no backend/extensions dependency.
"""
import argparse
import re
import sys
from pathlib import Path

# Skill root = parent of scripts/ (sam-generator dir), so "from lib.property_predictor..." works
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

try:
    from rdkit import Chem
except ImportError:
    print("错误：需要安装 rdkit。请运行 pip install rdkit-pypi", file=sys.stderr)
    sys.exit(1)


def _extract_smiles(text: str) -> list[str]:
    matches = re.findall(r'\d+\.\s*SMILES:\s*`?([^`\n]+)`?', text, re.IGNORECASE)
    if not matches:
        matches = re.findall(r'`([^`]+)`', text)
    if not matches:
        for line in text.split("\n"):
            line = line.strip()
            if line and Chem.MolFromSmiles(line):
                matches.append(line)
    if not matches:
        for s in text.split(","):
            s = s.strip().strip('`').strip('"').strip("'")
            if s and Chem.MolFromSmiles(s):
                matches.append(s)
    return [m.strip() for m in matches]


def main():
    ap = argparse.ArgumentParser(description="Predict molecular properties (HOMO, LUMO, DM)")
    ap.add_argument("--smiles", "-s", action="append", help="SMILES string (can repeat)")
    ap.add_argument("--input", "-i", help="Input file containing SMILES text")
    ap.add_argument("--properties", "-p", default="HOMO,LUMO,DM",
                    help="Comma-separated: HOMO, LUMO, DM (default: HOMO,LUMO,DM)")
    args = ap.parse_args()
    smiles_list = []
    if args.smiles:
        smiles_list = [s.strip() for s in args.smiles if s.strip()]
    if args.input:
        p = Path(args.input)
        if p.exists():
            smiles_list = _extract_smiles(p.read_text(encoding="utf-8"))
    if not smiles_list:
        print("错误：未从输入中提取到有效 SMILES。请使用 --smiles 或 --input。", file=sys.stderr)
        sys.exit(1)
    prop_list = [x.strip().upper() for x in args.properties.split(",")]
    HOMO = "HOMO" in prop_list
    LUMO = "LUMO" in prop_list
    DM = "DM" in prop_list
    if not (HOMO or LUMO or DM):
        print("错误：请指定至少一种性质：HOMO, LUMO, DM。", file=sys.stderr)
        sys.exit(1)
    try:
        from lib.property_predictor.prop_predictor import Predictor
    except ImportError as e:
        print(f"错误：无法导入性质预测模块（lib.property_predictor）。请确认在 skill 目录下运行且 unimol_tools 等依赖已安装。\n{e}", file=sys.stderr)
        sys.exit(1)
    predictor = Predictor()
    results = predictor.prop_pred(smiles_list, generated=False, HOMO=HOMO, LUMO=LUMO, DM=DM)
    print("分子性质预测结果：\n")
    for i, smiles in enumerate(smiles_list):
        print(f"分子 {i+1}: {smiles}")
        if "HOMO" in results:
            v = results["HOMO"]
            val = v.get("raw_data", v) if isinstance(v, dict) else v
            if isinstance(val, dict):
                pred = val.get("predict_HOMO", val.get("HOMO", "N/A"))
            elif hasattr(val, "__getitem__") and i < len(val):
                pred = val[i]
            else:
                pred = val
            print(f"  HOMO: {pred}")
        if "LUMO" in results:
            v = results["LUMO"]
            val = v.get("raw_data", v) if isinstance(v, dict) else v
            if isinstance(val, dict):
                pred = val.get("predict_LUMO", val.get("LUMO", "N/A"))
            elif hasattr(val, "__getitem__") and i < len(val):
                pred = val[i]
            else:
                pred = val
            print(f"  LUMO: {pred}")
        if "DM" in results:
            v = results["DM"]
            val = v.get("raw_data", v) if isinstance(v, dict) else v
            if isinstance(val, dict):
                pred = val.get("predict_DM", val.get("DM", "N/A"))
            elif hasattr(val, "__getitem__") and i < len(val):
                pred = val[i]
            else:
                pred = val
            print(f"  偶极矩 (DM): {pred}")
        print()


if __name__ == "__main__":
    main()
