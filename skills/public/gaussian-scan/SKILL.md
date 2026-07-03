---
name: gaussian-scan
description: Gaussian potential-energy-surface scans along bonds, angles, or dihedrals using the ModRedundant coordinate protocol. Use when user wants a rigid/relaxed PES scan, torsional profile, bond dissociation curve, or 势能面扫描/PES/扭角扫描.
---

# gaussian-scan

## When to Use
User supplies a starting geometry and a scan coordinate definition (which atoms,
what range, how many steps).

## Workflow
`python scripts/run.py start.xyz --coord "B 1 2 S 10 0.1" --preset b3lyp-d3 --work-dir ./scan`

The scan coord string follows Gaussian ModRedundant syntax:
- `B i j` — bond between atoms i and j
- `A i j k` — angle
- `D i j k l` — dihedral
- append `S Nsteps StepSize` for relaxed scan

## Reference
- `references/scan.md`

<!-- HPC_CONFIG_BLOCK -->
## HPC 配置

本 skill 通过 `~/.hpc/profiles.yaml` 读取超算凭据（SSH key / SCNet API key 等）。
首次使用：

```bash
mkdir -p ~/.hpc
cp _shared-gaussian/hpc-profiles.template.yaml ~/.hpc/profiles.yaml
chmod 600 ~/.hpc/profiles.yaml      # 文件含密钥路径，限制权限
# 编辑填入至少一个 profile（local / generic-slurm / scnet-h100）
```

项目级配置 `~/.gaussian_skills/config.yaml` 只放 `profile: <name>` + 项目专属设置。
完整说明见 [`_shared-gaussian/HPC.md`](../_shared-gaussian/HPC.md)。
