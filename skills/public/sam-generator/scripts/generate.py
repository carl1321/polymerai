#!/usr/bin/env python3
"""
Generate SAM molecules from skill. Run via: python generate.py --scaffold "c1ccccc1" --anchoring "O=P(O)(O)" [--gen_size 10]
Or from sandbox: python /mnt/skills/public/sam-generator/scripts/generate.py --scaffold "c1ccccc1" --anchoring "O=P(O)(O)"
Uses skill-local lib (run_generate); no backend path required.
"""
from pathlib import Path
import argparse
import sys

# Skill root = parent of scripts/ (sam-generator dir), so "from lib import run_generate" works
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


def main():
    ap = argparse.ArgumentParser(description="Generate SAM molecules (scaffold + anchoring group)")
    ap.add_argument("--scaffold", "-s", required=True, help="Scaffold SMILES, comma-separated for multiple (e.g. c1ccccc1)")
    ap.add_argument("--anchoring", "-a", required=True, help="Anchoring group SMILES (e.g. O=P(O)(O))")
    ap.add_argument("--gen_size", "-n", type=int, default=10, help="Number of molecules to generate (default 10)")
    args = ap.parse_args()
    try:
        from lib import run_generate
    except ImportError as e:
        print("错误：无法导入 run_generate。请确保在 skill 目录下运行（含 lib 包）。")
        print(f"错误详情：{e}")
        sys.exit(1)
    molecules = run_generate(args.scaffold, args.anchoring, args.gen_size)
    if not molecules:
        print("未能生成有效的SAM分子。请检查骨架和锚定基团是否有效。")
        sys.exit(0)
    print(f"成功生成 {len(molecules)} 个SAM分子：")
    for i, mol in enumerate(molecules, 1):
        print(f"{i}. SMILES: {mol['smiles']}")
        print(f"   骨架条件: {mol['scaffold_condition']}")
        print(f"   实际骨架: {mol['scaffold_smiles']}")
        print()


if __name__ == "__main__":
    main()
