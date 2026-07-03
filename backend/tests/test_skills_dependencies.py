from pathlib import Path

from deerflow.skills.dependencies import ensure_custom_skill_dependencies


def _write_skill(skill_dir: Path, name: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n",
        encoding="utf-8",
    )


def test_auto_install_custom_skill_requirements_uses_hash_cache(tmp_path: Path, monkeypatch):
    skills_root = tmp_path / "skills"
    custom_skill_dir = skills_root / "custom" / "xrd-agent"
    _write_skill(custom_skill_dir, "xrd-agent")
    req = custom_skill_dir / "requirements.txt"
    req.write_text("requests==2.32.3\n", encoding="utf-8")

    installed: list[str] = []

    shared_python = tmp_path / ".deer-flow" / ".venv" / "bin" / "python"
    shared_python.parent.mkdir(parents=True, exist_ok=True)
    shared_python.write_text("", encoding="utf-8")

    monkeypatch.setattr("deerflow.skills.dependencies._ensure_shared_venv", lambda: shared_python)

    def _fake_install(requirements_file: Path, python_bin: Path) -> None:
        installed.append(f"{requirements_file}|{python_bin}")

    monkeypatch.setattr("deerflow.skills.dependencies._install_requirements_file", _fake_install)

    ensure_custom_skill_dependencies(skills_root)
    ensure_custom_skill_dependencies(skills_root)

    assert installed == [f"{req}|{shared_python}"]

    req.write_text("requests==2.32.4\n", encoding="utf-8")
    ensure_custom_skill_dependencies(skills_root)
    assert installed == [f"{req}|{shared_python}", f"{req}|{shared_python}"]


def test_auto_install_skips_directories_without_skill_md(tmp_path: Path, monkeypatch):
    skills_root = tmp_path / "skills"
    only_req_dir = skills_root / "custom" / "misc"
    only_req_dir.mkdir(parents=True, exist_ok=True)
    (only_req_dir / "requirements.txt").write_text("numpy==2.2.0\n", encoding="utf-8")

    installed: list[str] = []

    shared_python = tmp_path / ".deer-flow" / ".venv" / "bin" / "python"
    shared_python.parent.mkdir(parents=True, exist_ok=True)
    shared_python.write_text("", encoding="utf-8")
    monkeypatch.setattr("deerflow.skills.dependencies._ensure_shared_venv", lambda: shared_python)

    def _fake_install(requirements_file: Path, python_bin: Path) -> None:
        installed.append(f"{requirements_file}|{python_bin}")

    monkeypatch.setattr("deerflow.skills.dependencies._install_requirements_file", _fake_install)
    ensure_custom_skill_dependencies(skills_root)

    assert installed == []
