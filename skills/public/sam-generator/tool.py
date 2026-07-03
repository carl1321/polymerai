# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT
"""
SAM molecule tools: 通过 scripts 目录下的脚本执行，不直接 import lib 或 backend 工具。
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState

_ROOT = Path(__file__).resolve().parent
_SCRIPTS = _ROOT / "scripts"
# 供 scripts 内 visualize.py / predict.py 用：skill -> public -> skills -> repo
_REPO_ROOT = _ROOT.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_SHARED_VENV_CANDIDATES = [
    Path("/mnt/user-data/shared/.venv/bin/python"),
    _BACKEND_ROOT / ".deer-flow" / ".venv" / "bin" / "python",
]
_OUTPUTS_DIR = Path("/mnt/user-data/outputs")
_VISUALIZE_OUTPUT_FILE = _OUTPUTS_DIR / "molecular_structure.svg"


def _resolve_python_executable() -> str:
    """Resolve python executable with shared venv priority."""
    for candidate in _SHARED_VENV_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return os.environ.get("PYTHON", "python")


def _run_script(script_name: str, args: list[str]) -> tuple[str, str, int]:
    """在 skill 根目录下执行 scripts/<script_name>，返回 (stdout, stderr, returncode)。"""
    script_path = _SCRIPTS / script_name
    if not script_path.exists():
        return "", f"脚本不存在: {script_path}", 1
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(_ROOT), str(_BACKEND_ROOT), env.get("PYTHONPATH", "")])
    cmd = [_resolve_python_executable(), str(script_path)] + args
    r = subprocess.run(
        cmd,
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return r.stdout or "", r.stderr or "", r.returncode


def _resolve_thread_outputs_dir(runtime: ToolRuntime[ContextT, ThreadState] | None) -> Path:
    """Resolve current thread's host outputs dir when runtime is available."""
    if runtime is not None and runtime.state is not None:
        thread_data = runtime.state.get("thread_data") or {}
        outputs_path = thread_data.get("outputs_path")
        if outputs_path:
            return Path(outputs_path)
    return _OUTPUTS_DIR


@tool
def generate_sam_molecules(
    scaffold_condition: str,
    anchoring_group: str,
    gen_size: int = 10,
) -> str:
    """生成自组装单分子层（SAM）分子

    通过 scripts/generate.py 执行。仅生成 SMILES，不画图；后续用可视化工具画图。

    Args:
        scaffold_condition: 骨架 SMILES，多个用逗号分隔
        anchoring_group: 锚定基团 SMILES，如 O=P(O)(O)
        gen_size: 生成数量，默认 10

    Returns:
        生成的分子列表（纯文本，含 SMILES 与骨架信息）
    """
    stdout, stderr, code = _run_script(
        "generate.py",
        ["--scaffold", scaffold_condition, "--anchoring", anchoring_group, "--gen_size", str(gen_size)],
    )
    if code != 0:
        return f"生成失败 (exit {code}):\n{stderr.strip() or stdout}"
    return stdout.strip() or "无输出"


@tool
def visualize_sam_molecules(
    runtime: ToolRuntime[ContextT, ThreadState],
    smiles_text: str,
    width: int = 800,
    height: int = 600,
) -> str:
    """根据 SMILES 文本生成 2D 分子结构图（通过 scripts/visualize.py）

    参数:
        smiles_text: 包含 SMILES 的文本（如 generate_sam_molecules 的输出或逐行 SMILES）
        width, height: 占位，脚本内部控制尺寸
    """
    with tempfile.TemporaryDirectory(prefix="sam_vis_") as tmp:
        inp = Path(tmp) / "smiles.txt"
        inp.write_text(smiles_text, encoding="utf-8")
        out_svg = Path(tmp) / "grid.svg"
        stdout, stderr, code = _run_script(
            "visualize.py",
            ["--input", str(inp), "--output", str(out_svg)],
        )
        if code != 0:
            return f"可视化失败 (exit {code}):\n{stderr.strip() or stdout}"
        if out_svg.exists():
            outputs_dir = _resolve_thread_outputs_dir(runtime)
            outputs_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out_svg, outputs_dir / "molecular_structure.svg")
            return (
                "已生成分子结构图（SVG）文件：\n"
                f"- {_VISUALIZE_OUTPUT_FILE}\n"
                "请调用 present_files 呈现该文件。"
            )
        return stdout.strip() or "未生成输出文件"


@tool
def predict_sam_properties(smiles_text: str, properties: str = "HOMO,LUMO,DM") -> str:
    """预测分子性质（HOMO、LUMO、偶极矩），通过 scripts/predict.py

    参数:
        smiles_text: 包含 SMILES 的文本
        properties: 逗号分隔的性质，如 HOMO,LUMO,DM
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(smiles_text)
        inp = f.name
    try:
        stdout, stderr, code = _run_script(
            "predict.py",
            ["--input", inp, "--properties", properties],
        )
        if code != 0:
            return f"性质预测失败 (exit {code}):\n{stderr.strip() or stdout}"
        return stdout.strip() or "无输出"
    finally:
        try:
            os.unlink(inp)
        except OSError:
            pass
