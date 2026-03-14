from datetime import datetime
from unittest.mock import patch

import pytest

import analysis
import knowledge


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


def _plan(name, steps=None):
    return {"name": name, "steps": steps or []}


def _trigger(trigger_type, params, plan_name):
    return {"type": trigger_type, "params": params, "plan": plan_name}


def _entity(entity_id, state, area_id=None):
    return {"entity_id": entity_id, "state": state, "attributes": {}, "area_id": area_id}


def _load(trigger_type, params, plan_name="test_plan"):
    knowledge.load_configuration(
        [_plan(plan_name)],
        [_trigger(trigger_type, params, plan_name)],
    )


# ---------------------------------------------------------------------------
# at_time
# ---------------------------------------------------------------------------

def test_at_time_fires():
    with patch("analysis.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 20, 30)
        _load(analysis.TRIGGER_AT_TIME, {"time": "20:30"})
        result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert len(result) == 1
    assert result[0]["plan"]["name"] == "test_plan"
    assert result[0]["request_id"] is not None


def test_at_time_no_fire_wrong_time():
    with patch("analysis.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 10, 0)
        _load(analysis.TRIGGER_AT_TIME, {"time": "20:30"})
        result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []


def test_at_time_dedup_same_day():
    with patch("analysis.datetime") as mock_dt:
        now = datetime(2026, 1, 1, 20, 30)
        mock_dt.now.return_value = now
        _load(analysis.TRIGGER_AT_TIME, {"time": "20:30"})
        # Already triggered today
        knowledge.create_request(None, "test_plan", analysis.TRIGGER_AT_TIME, knowledge.REQUEST_COMPLETED, now)
        result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []


def test_at_time_fires_on_new_day():
    with patch("analysis.datetime") as mock_dt:
        now = datetime(2026, 1, 2, 20, 30)
        mock_dt.now.return_value = now
        _load(analysis.TRIGGER_AT_TIME, {"time": "20:30"})
        # Yesterday's request — should not block today
        knowledge.create_request(None, "test_plan", analysis.TRIGGER_AT_TIME, knowledge.REQUEST_COMPLETED, datetime(2026, 1, 1, 20, 30))
        result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert len(result) == 1


# ---------------------------------------------------------------------------
# on_sunset
# ---------------------------------------------------------------------------

def test_on_sunset_fires():
    knowledge.apply_state_change(_entity("sun.sun", "below_horizon"))
    _load(analysis.TRIGGER_ON_SUNSET, {})
    result = analysis.evaluate_triggers(_entity("switch.x", "off"))
    assert len(result) == 1


def test_on_sunset_no_fire_above_horizon():
    knowledge.apply_state_change(_entity("sun.sun", "above_horizon"))
    _load(analysis.TRIGGER_ON_SUNSET, {})
    result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []


def test_on_sunset_no_fire_missing_sun():
    _load(analysis.TRIGGER_ON_SUNSET, {})
    result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []


def test_on_sunset_dedup_same_day():
    with patch("analysis.datetime") as mock_dt:
        now = datetime(2026, 1, 1, 19, 0)
        mock_dt.now.return_value = now
        knowledge.apply_state_change(_entity("sun.sun", "below_horizon"))
        _load(analysis.TRIGGER_ON_SUNSET, {})
        knowledge.create_request(None, "test_plan", analysis.TRIGGER_ON_SUNSET, knowledge.REQUEST_COMPLETED, now)
        result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []


# ---------------------------------------------------------------------------
# entity_state — stateful
# ---------------------------------------------------------------------------

def test_entity_state_fires():
    knowledge.apply_state_change(_entity("binary_sensor.door", "on"))
    _load(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "binary_sensor.door", "state": "on"})
    result = analysis.evaluate_triggers(_entity("binary_sensor.door", "on"))
    assert len(result) == 1


def test_entity_state_no_fire_wrong_state():
    knowledge.apply_state_change(_entity("binary_sensor.door", "off"))
    _load(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "binary_sensor.door", "state": "on"})
    result = analysis.evaluate_triggers(_entity("binary_sensor.door", "off"))
    assert result == []


def test_stateful_entity_fires_each_time():
    # Stateful entity triggers have no per-day dedup — fire on every match
    knowledge.apply_state_change(_entity("binary_sensor.door", "on"))
    _load(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "binary_sensor.door", "state": "on"})
    result1 = analysis.evaluate_triggers(_entity("binary_sensor.door", "on"))
    result2 = analysis.evaluate_triggers(_entity("binary_sensor.door", "on"))
    assert len(result1) == 1
    assert len(result2) == 1


# ---------------------------------------------------------------------------
# entity_state — button (stateless)
# ---------------------------------------------------------------------------

def test_button_trigger_fires_and_sets_pending():
    _load(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "button.doorbell"})
    req = knowledge.create_request(
        "button.doorbell", "test_plan", "entity_state", knowledge.REQUEST_NEW, datetime.now(),
    )
    result = analysis.evaluate_triggers(
        _entity("button.doorbell", "2026-03-11T10:00:00"), request_id=req["id"],
    )
    assert len(result) == 1
    assert result[0]["request_id"] == req["id"]
    assert knowledge.get_last_request("button.doorbell")["status"] == knowledge.REQUEST_PENDING


def test_button_no_fire_wrong_entity():
    _load(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "button.doorbell"})
    result = analysis.evaluate_triggers(_entity("switch.other", "on"))
    assert result == []


def test_button_no_fire_without_request_id():
    # request_id=None means monitor didn't create a request — should not fire
    _load(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "button.doorbell"})
    result = analysis.evaluate_triggers(
        _entity("button.doorbell", "2026-03-11T10:00:00"), request_id=None,
    )
    assert result == []


# ---------------------------------------------------------------------------
# Multiple triggers
# ---------------------------------------------------------------------------

def test_multiple_triggers_both_fire():
    knowledge.apply_state_change(_entity("sun.sun", "below_horizon"))
    knowledge.apply_state_change(_entity("binary_sensor.door", "on"))
    knowledge.load_configuration(
        [_plan("exterior"), _plan("door_alert")],
        [
            _trigger(analysis.TRIGGER_ON_SUNSET,    {},                                                   "exterior"),
            _trigger(analysis.TRIGGER_ENTITY_STATE, {"entity_id": "binary_sensor.door", "state": "on"},  "door_alert"),
        ],
    )
    result = analysis.evaluate_triggers(_entity("binary_sensor.door", "on"))
    names = [item["plan"]["name"] for item in result]
    assert "exterior" in names
    assert "door_alert" in names


def test_no_triggers_returns_empty():
    result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []


def test_unknown_plan_skips_gracefully():
    # Trigger references a plan that doesn't exist
    knowledge.load_configuration(
        [],
        [_trigger(analysis.TRIGGER_ON_SUNSET, {}, "nonexistent_plan")],
    )
    knowledge.apply_state_change(_entity("sun.sun", "below_horizon"))
    result = analysis.evaluate_triggers(_entity("switch.x", "on"))
    assert result == []
