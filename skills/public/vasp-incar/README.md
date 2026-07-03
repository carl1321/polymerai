# vasp-incar

VASP INCAR + KPOINTS generation skill for Claude Code.

Reads a POSCAR and a calculation type, produces an INCAR + KPOINTS file with
automatic system detection (metal / semiconductor / insulator, Bravais lattice,
magnetic elements), runs a 30-rule conflict validator, and can explain any tag.

```bash
pip install -e .
vasp-incar generate band --poscar POSCAR --out ./band/
```

See `SKILL.md` for the full subcommand list and trigger keywords.

## Production deployment

Linux 服务器完整部署（含环境变量、HPC 配置、注册到 `~/.claude/skills/`）见 [`vasp-skills/README.md`](../vasp-skills/README.md#生产环境部署linux-服务器)。
