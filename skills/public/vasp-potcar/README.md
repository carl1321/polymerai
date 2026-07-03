# vasp-potcar

VASP POTCAR generation skill for Claude Code.

Intelligent pseudopotential selection using multi-source verification (Materials Project, AFLOW, OQMD, pymatgen recommendations) with a local POTCAR library.

```bash
pip install -e .
vasp-potcar generate --poscar POSCAR --functional PBE --out POTCAR
```

See `SKILL.md` for the full subcommand list and trigger keywords.

## Production deployment

Linux 服务器完整部署（含 `VASP_PP_PATH` / `MP_API_KEY` 等环境变量、POTCAR 库目录布局、注册到 `~/.claude/skills/`）见 [`vasp-skills/README.md`](../vasp-skills/README.md#生产环境部署linux-服务器)。
