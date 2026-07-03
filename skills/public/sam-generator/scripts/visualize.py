#!/usr/bin/env python3
"""
Visualize molecules (SMILES) as 2D structure grid. Run via bash from skill.
Usage: python visualize.py --smiles "CCO" [--smiles "CCCO" ...] --output /mnt/user-data/outputs/grid.svg
   or: python visualize.py --input /path/to/text.txt --output /mnt/user-data/outputs/grid.svg
Input file may contain "SMILES: xxx" lines or one SMILES per line.
"""
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
if BACKEND_ROOT.exists():
    sys.path.insert(0, str(BACKEND_ROOT))
else:
    import os

    repo = os.environ.get("DEER_FLOW_REPO_ROOT")
    if repo:
        candidate = Path(repo) / "backend"
        if candidate.exists():
            sys.path.insert(0, str(candidate))

try:
    from rdkit import Chem
    from rdkit.Chem.Draw import MolsToGridImage
except ImportError:
    print("错误：需要安装 rdkit。请运行 pip install rdkit-pypi", file=sys.stderr)
    sys.exit(1)


def _extract_smiles_from_text(text: str) -> list[str]:
    cleaned = re.sub(r'!\[.*?\]\(data:image[^\n]+\)', '', text)
    cleaned = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+', '', cleaned, flags=re.MULTILINE)
    out = []
    for m in re.findall(r'SMILES:\s*`?([^\s\n`]+)`?', cleaned, re.IGNORECASE):
        out.append(m)
    for m in re.findall(r'\d+\.\s*(?:SMILES:\s*)?`?([A-Za-z0-9@+\-\[\]\(\)=#@\:\/\\\\]+)`?', cleaned, re.IGNORECASE):
        out.append(m)
    if not out:
        for line in cleaned.strip().split("\n"):
            line = line.strip()
            if line and len(line) > 3 and Chem.MolFromSmiles(line):
                out.append(line)
    seen = set()
    return [s for s in out if len(s) > 2 and s not in seen and not seen.add(s)]


def main():
    ap = argparse.ArgumentParser(description="Visualize SMILES as 2D molecular grid image")
    ap.add_argument("--smiles", "-s", action="append", help="SMILES string (can repeat)")
    ap.add_argument("--input", "-i", help="Input file: text with SMILES or one per line")
    ap.add_argument("--output", "-o", default="/mnt/user-data/outputs/molecular_grid.svg",
                    help="Output image path (default: /mnt/user-data/outputs/molecular_grid.svg)")
    args = ap.parse_args()
    smiles_list = []
    if args.smiles:
        smiles_list = [s.strip() for s in args.smiles if s.strip()]
    if args.input:
        path = Path(args.input)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            smiles_list = _extract_smiles_from_text(text) or [ln.strip() for ln in text.splitlines() if ln.strip() and Chem.MolFromSmiles(ln.strip())]
    if not smiles_list:
        print("错误：未提供有效 SMILES。请使用 --smiles 或 --input 指定。", file=sys.stderr)
        sys.exit(1)
    mols = []
    for s in smiles_list:
        m = Chem.MolFromSmiles(s)
        if m is not None:
            mols.append(m)
    if not mols:
        print("错误：未能从 SMILES 生成有效分子。", file=sys.stderr)
        sys.exit(1)
    out_path = Path(args.output)
    # 在 DeerFlow 沙箱中，/mnt/user-data/outputs 由中间件预先创建；
    # 如果当前环境下该目录不存在（例如直接在宿主机运行），给出清晰错误而不是尝试创建只读的 /mnt。
    if not out_path.parent.exists():
        print(
            f"错误：输出目录不存在: {out_path.parent}。"
            "请在 DeerFlow 沙箱环境中运行该脚本，或先创建对应的输出目录。",
            file=sys.stderr,
        )
        sys.exit(1)
    n = len(mols)
    mols_per_row = min(5, n)
    sub_size = (400, 400) if n == 1 else (200, 200)
    img = MolsToGridImage(mols, molsPerRow=mols_per_row, subImgSize=sub_size, useSVG=True)
    out_path.write_text(str(img), encoding="utf-8")
    print(f"已生成 {len(mols)} 个分子结构图，保存至: {out_path}")
    print(str(out_path))


if __name__ == "__main__":
    main()
