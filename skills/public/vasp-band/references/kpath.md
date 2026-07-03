# vasp-band — k-path 约定

pymatgen 的 `HighSymmKpath` 默认用 **Setyawan-Curtarolo**（Comput. Mater. Sci. 49, 299 (2010)）的高对称点。该协议与 VASP 官方 band structure 示例一致。

- 对三斜 / 单斜体系会自动按 Bravais lattice 分叉选 k-path
- 与 Seekpath 相比：Setyawan-Curtarolo 对六方和三方体系的 Γ-K-M 路径选择略有差异；结果物理等价，标签可能不同

若用户明确要求 Seekpath，可以：
```bash
pip install seekpath
# 然后在 scripts/run.py 里换成 pymatgen.symmetry.bandstructure.SeekpathKpath
```

**line_density** 建议：
- 粗图示：10
- 论文图：20–30
- 金属 Fermi 面附近：≥30
