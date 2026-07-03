# vasp-analysis

VASP post-processing & visualization skill for Claude Code.

Reads a VASP work directory and produces publication-ready figures + a markdown
summary. Auto-detects calculation type. Backends: sumo, pyprocar, phonopy,
pymatgen.

```bash
pip install -e .
vasp-analysis auto --workdir ./my_vasp_run
```

See `SKILL.md` for the full subcommand list and trigger conditions.

## Production deployment

Linux 服务器完整部署（含环境变量、HPC 配置、注册到 `~/.claude/skills/`）见 [`vasp-skills/README.md`](../vasp-skills/README.md#生产环境部署linux-服务器)。
