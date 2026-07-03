from deerflow.agents.memory import enabled as enabled_module


def test_memory_toggle_defaults_to_false_when_db_value_missing(monkeypatch):
    monkeypatch.setattr(enabled_module, "_read_memory_enabled_from_db", lambda **_: None)
    enabled_module.clear_memory_enabled_cache()

    assert enabled_module.is_memory_enabled_for_agent(
        agent_id="11111111-1111-1111-1111-111111111111",
        agent_name="agent-a",
    ) is False


def test_memory_toggle_uses_db_true_value(monkeypatch):
    monkeypatch.setattr(enabled_module, "_read_memory_enabled_from_db", lambda **_: True)
    enabled_module.clear_memory_enabled_cache()

    assert enabled_module.is_memory_enabled_for_agent(
        agent_id="11111111-1111-1111-1111-111111111111",
        agent_name="agent-a",
    ) is True
