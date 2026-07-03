from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deerflow.skills.types import Skill
from extensions.auth.dependencies import CurrentUser, get_current_user_optional

agents_router_module = importlib.import_module("extensions.agents_db.router")


class _FakeConn:
    def close(self) -> None:
        return None


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[list[object]] = []

    def invoke(self, messages: list[object]):
        self.calls.append(messages)
        content = self._responses.pop(0)
        return SimpleNamespace(content=content)


def _make_skill(tmp_path: Path, name: str, description: str, body: str) -> Skill:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return Skill(
        name=name,
        description=description,
        license=None,
        skill_dir=skill_dir,
        skill_file=skill_file,
        relative_path=Path(name),
        category="public",
        enabled=True,
    )


def _make_user() -> CurrentUser:
    return CurrentUser(
        {
            "id": str(uuid4()),
            "username": "tester",
            "email": "tester@example.com",
            "organization_id": str(uuid4()),
            "department_id": None,
        },
        roles=[],
        permissions=[],
    )


def test_generate_prompt_semantic_skill_and_guardrail(tmp_path, monkeypatch):
    skill_alpha = _make_skill(tmp_path, "alpha-skill", "Alpha for database ops", "Use structured output.")
    skill_beta = _make_skill(tmp_path, "beta-skill", "Beta for materials simulation", "Always cite source.")
    skills = [skill_alpha, skill_beta]

    fake_llm = _FakeLLM(
        responses=[
            json.dumps({"matches": [{"name": "beta-skill", "reason": "语义最匹配材料仿真"}]}, ensure_ascii=False),
            json.dumps({"supplement_prompt": "Always cite source.\n补充：输出时附上关键参数说明。"}, ensure_ascii=False),
            json.dumps({"conflict_free": True, "revised_prompt": "补充：输出时附上关键参数说明。"}, ensure_ascii=False),
        ]
    )

    monkeypatch.setattr(agents_router_module, "get_app_db_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        agents_router_module,
        "db_get_agent",
        lambda conn, agent_id, user_id, organization_id: {
            "id": str(agent_id),
            "name": "materials-helper",
            "description": "用于材料结构分析与结果说明",
        },
    )
    monkeypatch.setattr(agents_router_module, "load_skills", lambda enabled_only=False: skills)
    monkeypatch.setattr(agents_router_module, "get_llm_by_type", lambda *_args, **_kwargs: fake_llm)
    monkeypatch.setattr(agents_router_module, "get_llm_by_model_name", lambda *_args, **_kwargs: fake_llm)

    app = FastAPI()
    app.include_router(agents_router_module.router)
    app.dependency_overrides[get_current_user_optional] = _make_user

    agent_id = str(uuid4())
    with TestClient(app) as client:
        resp = client.post(f"/api/agents/{agent_id}/generate-prompt", json={})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["skill_names"] == ["beta-skill"]
    assert payload["matched_skills"][0]["name"] == "beta-skill"
    assert payload["supplement_prompt"] == "补充：输出时附上关键参数说明。"
    assert payload["guardrail_report"]["conflict_checked"] is True
    assert payload["guardrail_report"]["dedup_removed"] == 1

    # Verify semantic rerank input only contains skill metadata (name/description).
    rerank_messages = fake_llm.calls[0]
    rerank_payload = json.loads(rerank_messages[1].content)
    assert "skills" in rerank_payload
    assert set(rerank_payload["skills"][0].keys()) == {"name", "description"}

