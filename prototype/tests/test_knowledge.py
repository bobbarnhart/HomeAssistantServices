from datetime import datetime

import pytest

import knowledge


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


def _plan(name, steps=None):
    return {"name": name, "steps": steps or []}


def _trigger(trigger_type, params, plan_name):
    return {"type": trigger_type, "params": params, "plan": plan_name}


# ---------------------------------------------------------------------------
# Entity state
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_load_configuration():
    plans    = [_plan("my_plan")]
    triggers = [_trigger("at_time", {"time": "20:30"}, "my_plan")]
    knowledge.load_configuration(plans, triggers)
    assert knowledge.get_plan("my_plan") is not None
    assert len(knowledge.get_triggers()) == 1


def test_get_plan_not_found():
    assert knowledge.get_plan("nonexistent") is None


def test_entities_in_area():
    knowledge.apply_state_change({"entity_id": "light.a", "state": "on", "attributes": {}, "area_id": "living_room"})
    knowledge.apply_state_change({"entity_id": "light.b", "state": "on", "attributes": {}, "area_id": "bedroom"})
    knowledge.apply_state_change({"entity_id": "light.c", "state": "on", "attributes": {}, "area_id": "living_room"})
    result = knowledge.entities_in_area("living_room")
    assert {e["entity_id"] for e in result} == {"light.a", "light.c"}


def test_entities_in_area_empty():
    assert knowledge.entities_in_area("nowhere") == []


# ---------------------------------------------------------------------------
# get_trigger_for_entity
# ---------------------------------------------------------------------------

def test_get_trigger_for_entity_found():
    trigger = _trigger("entity_state", {"entity_id": "button.doorbell"}, "doorbell_plan")
    knowledge.load_configuration([], [trigger])
    result = knowledge.get_trigger_for_entity("button.doorbell")
    assert result is not None
    assert result["plan"] == "doorbell_plan"


def test_get_trigger_for_entity_not_found():
    knowledge.load_configuration([], [])
    assert knowledge.get_trigger_for_entity("button.doorbell") is None


def test_get_trigger_for_entity_ignores_stateful():
    # A trigger with a "state" param is NOT a stateless button trigger
    trigger = _trigger("entity_state", {"entity_id": "binary_sensor.door", "state": "on"}, "door_plan")
    knowledge.load_configuration([], [trigger])
    assert knowledge.get_trigger_for_entity("binary_sensor.door") is None


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

def test_create_request_button():
    t = datetime(2026, 1, 1, 20, 30)
    req = knowledge.create_request("button.doorbell", "doorbell_plan", "entity_state", knowledge.REQUEST_NEW, t)
    assert req["entity_id"] == "button.doorbell"
    assert req["plan_name"] == "doorbell_plan"
    assert req["trigger_type"] == "entity_state"
    assert req["status"] == knowledge.REQUEST_NEW
    assert req["created_at"] == t


def test_create_request_time_trigger():
    t = datetime(2026, 1, 1, 20, 30)
    req = knowledge.create_request(None, "nighttime_plan", "at_time", knowledge.REQUEST_PENDING, t)
    assert req["entity_id"] is None
    assert req["plan_name"] == "nighttime_plan"


def test_update_request_status():
    req = knowledge.create_request("button.x", "plan_a", "entity_state", knowledge.REQUEST_NEW, datetime.now())
    knowledge.update_request_status(req["id"], knowledge.REQUEST_COMPLETED)
    assert knowledge._requests[0]["status"] == knowledge.REQUEST_COMPLETED


def test_get_last_request_found():
    t1 = datetime(2026, 1, 1, 20, 0)
    t2 = datetime(2026, 1, 1, 21, 0)
    knowledge.create_request("button.x", "plan_a", "entity_state", knowledge.REQUEST_NEW, t1)
    knowledge.create_request("button.x", "plan_a", "entity_state", knowledge.REQUEST_NEW, t2)
    result = knowledge.get_last_request("button.x")
    assert result["created_at"] == t2


def test_get_last_request_not_found():
    assert knowledge.get_last_request("button.missing") is None


def test_get_last_request_for_plan_found():
    t = datetime(2026, 1, 1, 20, 30)
    knowledge.create_request(None, "nighttime_plan", "at_time", knowledge.REQUEST_COMPLETED, t)
    result = knowledge.get_last_request_for_plan("nighttime_plan", "at_time")
    assert result is not None
    assert result["created_at"] == t


def test_get_last_request_for_plan_not_found():
    assert knowledge.get_last_request_for_plan("nonexistent", "at_time") is None


# ---------------------------------------------------------------------------
# Execution record
# ---------------------------------------------------------------------------

def test_record_execution():
    plan = [{"entity_id": "light.x", "service": "light/turn_on", "params": {}}]
    t = datetime(2026, 1, 1, 20, 30)
    knowledge.record_execution("my_plan", plan, t)
    history = knowledge._adaptation["execution_history"]
    assert len(history) == 1
    assert history[0]["plan_name"] == "my_plan"
    assert history[0]["plan"] == plan


def test_next_msg_id_increments():
    id1 = knowledge.next_msg_id()
    id2 = knowledge.next_msg_id()
    assert id2 == id1 + 1


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_clears_all_stores():
    knowledge.apply_state_change({"entity_id": "x", "state": "on", "attributes": {}, "area_id": None})
    knowledge.load_configuration([_plan("p")], [_trigger("at_time", {"time": "20:00"}, "p")])
    knowledge.create_request(None, "p", "at_time", knowledge.REQUEST_NEW, datetime(2026, 1, 1))
    knowledge.next_msg_id()
    knowledge._reset()
    assert knowledge.get_entity("x") is None
    assert knowledge.get_plan("p") is None
    assert knowledge.get_triggers() == []
    assert knowledge.get_last_request_for_plan("p", "at_time") is None
    assert knowledge.next_msg_id() == 1
