from datetime import datetime

import pytest

import knowledge


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


def test_apply_state_change_adds_entity():
    entity = {"entity_id": "light.test", "state": "on", "attributes": {}, "area_id": None}
    knowledge.apply_state_change(entity)
    assert knowledge.get_entity("light.test") == entity


def test_apply_state_change_updates_entity():
    e1 = {"entity_id": "light.test", "state": "on",  "attributes": {}, "area_id": None}
    e2 = {"entity_id": "light.test", "state": "off", "attributes": {}, "area_id": None}
    knowledge.apply_state_change(e1)
    knowledge.apply_state_change(e2)
    assert knowledge.get_entity("light.test")["state"] == "off"


def test_get_entity_missing_returns_none():
    assert knowledge.get_entity("light.missing") is None


def test_load_configuration():
    automations = [{"name": "Test", "triggers": [], "steps": []}]
    knowledge.load_configuration(automations)
    assert knowledge.get_automations() == automations


def test_entities_in_area():
    knowledge.apply_state_change({"entity_id": "light.a", "state": "on", "attributes": {}, "area_id": "living_room"})
    knowledge.apply_state_change({"entity_id": "light.b", "state": "on", "attributes": {}, "area_id": "bedroom"})
    knowledge.apply_state_change({"entity_id": "light.c", "state": "on", "attributes": {}, "area_id": "living_room"})
    result = knowledge.entities_in_area("living_room")
    assert {e["entity_id"] for e in result} == {"light.a", "light.c"}


def test_entities_in_area_empty():
    assert knowledge.entities_in_area("nowhere") == []


def test_record_trigger_and_get_last():
    t = datetime(2026, 1, 1, 20, 30)
    knowledge.record_trigger("My Auto", "at_time", t)
    record = knowledge.get_last_trigger("My Auto", "at_time")
    assert record is not None
    assert record["fired_at"] == t


def test_get_last_trigger_returns_most_recent():
    t1 = datetime(2026, 1, 1, 20, 30)
    t2 = datetime(2026, 1, 1, 21, 30)
    knowledge.record_trigger("My Auto", "at_time", t1)
    knowledge.record_trigger("My Auto", "at_time", t2)
    assert knowledge.get_last_trigger("My Auto", "at_time")["fired_at"] == t2


def test_get_last_trigger_none_when_missing():
    assert knowledge.get_last_trigger("Nonexistent", "at_time") is None


def test_get_last_trigger_isolates_by_type():
    t = datetime(2026, 1, 1, 20, 0)
    knowledge.record_trigger("My Auto", "at_time", t)
    assert knowledge.get_last_trigger("My Auto", "entity_state") is None


def test_record_execution():
    plan = [{"entity_id": "light.x", "service": "light/turn_on", "params": {}}]
    t = datetime(2026, 1, 1, 20, 30)
    knowledge.record_execution("My Auto", plan, t)
    history = knowledge._adaptation["execution_history"]
    assert len(history) == 1
    assert history[0]["automation_name"] == "My Auto"
    assert history[0]["plan"] == plan


def test_next_msg_id_increments():
    id1 = knowledge.next_msg_id()
    id2 = knowledge.next_msg_id()
    assert id2 == id1 + 1


def test_reset_clears_all_stores():
    knowledge.apply_state_change({"entity_id": "x", "state": "on", "attributes": {}, "area_id": None})
    knowledge.load_configuration([{"name": "A", "triggers": [], "steps": []}])
    knowledge.record_trigger("A", "at_time", datetime(2026, 1, 1))
    knowledge.next_msg_id()
    knowledge._reset()
    assert knowledge.get_entity("x") is None
    assert knowledge.get_automations() == []
    assert knowledge.get_last_trigger("A", "at_time") is None
    assert knowledge.next_msg_id() == 1
