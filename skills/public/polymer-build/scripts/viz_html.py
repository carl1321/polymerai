#!/usr/bin/env python3
"""Interactive 3D HTML (3Dmol.js CDN) for polymer / packed PDB — copy to outputs for present_file."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from common import default_outputs_dir, load_manifest


def build_page(pdb_text: str, title: str) -> str:
    pdb_js = json.dumps(pdb_text)
    esc_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{esc_title}</title>
  <script src="https://3dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; }}
    #viewport {{ width: 100vw; height: 100vh; }}
    #caption {{
      position: absolute; top: 8px; left: 12px; background: rgba(255,255,255,0.85);
      padding: 6px 10px; border-radius: 6px; font-size: 13px;
    }}
  </style>
</head>
<body>
  <div id="caption">{esc_title}</div>
  <div id="viewport"></div>
  <script>
    const pdb = {pdb_js};
    const viewer = $3Dmol.createViewer("viewport", {{ backgroundColor: "white" }});
    viewer.addModel(pdb, "pdb");
    viewer.setStyle({{}}, {{ stick: {{ radius: 0.15 }}, sphere: {{ scale: 0.25 }} }});
    viewer.zoomTo();
    viewer.render();
  </script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="polymer-build: 3Dmol HTML visualization")
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--pdb", type=Path, default=None, help="Default: packed.pdb from manifest")
    ap.add_argument("--title", type=str, default="PolymerBuild — packed system")
    args = ap.parse_args()
    work_dir: Path = args.work_dir

    man = load_manifest(work_dir)
    pdb_path = args.pdb
    if pdb_path is None:
        pdb_path = Path(man.get("step04_packed_pdb", work_dir / "packed.pdb"))
    if not pdb_path.is_file():
        pdb_path = work_dir / "polymer_chain.pdb"
    if not pdb_path.is_file():
        print(f"viz_html: no PDB found (try step04 first): {pdb_path}", file=sys.stderr)
        return 2

    pdb_text = pdb_path.read_text(encoding="utf-8", errors="replace")
    page = build_page(pdb_text, args.title)

    outs = default_outputs_dir(work_dir)
    out_html = outs / "polymer_build_3d.html"
    out_html.write_text(page, encoding="utf-8")
    chain_html = outs / "polymer_build_chain_only.html"
    chain_pdb = work_dir / "polymer_chain.pdb"
    if chain_pdb.is_file():
        chain_html.write_text(build_page(chain_pdb.read_text(encoding="utf-8", errors="replace"), "PolymerBuild — single chain"), encoding="utf-8")

    print(f"wrote {out_html}")
    if chain_pdb.is_file():
        print(f"wrote {chain_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
