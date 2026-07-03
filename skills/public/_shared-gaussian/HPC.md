# HPC 配置（vasp-skills + gaussian-skills 共享）

两个 skill 项目读同一个文件 `~/.hpc/profiles.yaml`，HPC 凭据只配一次。

## 一次性配置

```bash
mkdir -p ~/.hpc
cp _shared-gaussian/hpc-profiles.template.yaml ~/.hpc/profiles.yaml
chmod 600 ~/.hpc/profiles.yaml         # 文件含 SSH key 路径 / API 密钥
nano ~/.hpc/profiles.yaml
```

填入至少一个 profile（local / generic-slurm / scnet-h100 三种类型），把 `default_profile` 指到你最常用的那个。

## 项目级配置（可选）

每个 skill 项目的 `~/.<project>_skills/config.yaml` 只需要：

```yaml
profile: sugon-cancon          # 引用 ~/.hpc/profiles.yaml 里的 profile 名
# 项目专属设置（错误处理、POTCAR、默认基组等）
handlers:
  enabled: true
  max_errors: 5
potcar:
  backend: vasp-potcar
  functional: PBE
```

如果省略 `profile:`，使用 `~/.hpc/profiles.yaml` 里的 `default_profile`。

如果项目 config 里直接写了 `ssh:` / `scnet:` 字段，会**覆盖** profile 同名字段（用于临时调试，不推荐长期使用）。

## 多 HPC 切换

CLI 临时切换：

```bash
python vasp-relax/scripts/run.py POSCAR --executor ssh --profile scnet-h100
```

## 安全建议

- `chmod 600 ~/.hpc/profiles.yaml`
- API 密钥用 `${ENV_VAR}` 占位，shell 启动时 `export SCNET_AK=...`
- 不要 `git add` 自己填好的 profiles.yaml；模板已加入项目仓库

## 字段参考

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | local / ssh / scnet | 执行器类型 |
| `host`, `port`, `username`, `key_path` | ssh only | SSH 连接 |
| `base_url`, `cluster_id`, `access_key`, `secret_key` | scnet only | SCNet REST API |
| `work_root` | path | 远端工作目录根 |
| `scheduler` | slurm / pbs / lsf | 作业调度器 |
| `modules` | list[str] | `module load` 前置 |
| `resources` | dict | partition/nodes/ntasks_per_node/walltime/memory |
| `apps` | dict | 各应用命令（vasp_cmd / gaussian_cmd / ...） |

## 故障排查

- `ProfileNotFoundError`：检查 `profile:` 名拼写、`~/.hpc/profiles.yaml` 是否存在
- SSH 连不上：`ssh -i <key_path> <user>@<host>` 手动测一次，把 host key 加进 `~/.ssh/known_hosts`
- 环境变量未展开：确认 shell 里 `echo $SCNET_AK` 有值；不要在 yaml 里直接写裸密钥
