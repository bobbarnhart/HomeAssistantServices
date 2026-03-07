from datetime import datetime
from unittest.mock import patch

import pytest

import analysis
import knowledge


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


def _entity(entity_id, state, area_id=None):
    return {"entity_id": entity_id, "state": state, "attributes": {}, "area_id": area_id}


def _automation(name, trigger_type, trigger_params):
    return {"name": name, "triggers": [{"type": trigger_type, "params": trigger_params}], "steps": []}


# ---------------------------------------------------------------------------
# at_time
# ---------------------------------------------------------------------------

def test_at_time_fires():
    with patch("analysis.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 20, 30)
        knowledge.load_configuration([_automation("Test", analysis.TRIGGER_AT_TIME, {"time": "20:30"})])
        result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert len(result) == 1


def test_at_time_no_fire_wrong_time():
    with patch("analysis.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 10, 0)
        knowledge.load_configuration([_automation("Test", analysis.TRIGGER_AT_TIME, {"time": "20:30"})])
        result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert result == []


# ---------------------------------------------------------------------------
# on_sunset
# ---------------------------------------------------------------------------

def test_on_sunset_fires():
    knowledge.apply_state_change(_entity("sun.sun", "below_horizon"))
    knowledge.load_configuration([_automation("Test", analysis.TRIGGER_ON_SUNSET, {})])
    result = analysis.evaluate_automations(_entity("switch.x", "off"))
    assert len(result) == 1


def test_on_sunset_no_fire_above_horizon():
    knowledge.apply_state_change(_entity("sun.sun", "above_horizon"))
    knowledge.load_configuration([_automation("Test", analysis.TRIGGER_ON_SUNSET, {})])
    result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert result == []


def test_on_sunset_no_fire_missing_sun():
    knowledge.load_configuration([_automation("Test", analysis.TRIGGER_ON_SUNSET, {})])
    result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert result == []


# ---------------------------------------------------------------------------
# entity_state
# ---------------------------------------------------------------------------

def test_entity_state_fires():
    knowledge.apply_state_change(_entity("binary_sensor.door", "on"))
    knowledge.load_configuration([_automation("Test", analysis.TRIGGER_ENTITY_STATE,
                                              {"entity_id": "binary_sensor.door", "state": "on"})])
    result = analysis.evaluate_automations(_entity("binary_sensor.door", "on"))
    assert len(result) == 1


def test_entity_state_no_fire_wrong_state():
    knowledge.apply_state_change(_entity("binary_sensor.door", "off"))
    knowledge.load_configuration([_automation("Test", analysis.TRIGGER_ENTITY_STATE,
                                              {"entity_id": "binary_sensor.door", "state": "on"})])
    result = analysis.evaluate_automations(_entity("binary_sensor.door", "off"))
    assert result == []


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_prevents_refire():
    with patch("analysis.datetime") as mock_dt:
        now = datetime(2026, 1, 1, 20, 30)
        mock_dt.now.return_value = now
        knowledge.load_configuration([_automation("Test", analysis.TRIGGER_AT_TIME, {"time": "20:30"})])
        # Record trigger 10 seconds ago — well within the 3600s cooldown
        knowledge.record_trigger("Test", analysis.TRIGGER_AT_TIME, datetime(2026, 1, 1, 20, 29, 50))
        result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert result == []


def test_cooldown_allows_after_expiry():
    with patch("analysis.datetime") as mock_dt:
        now = datetime(2026, 1, 1, 22, 30)
        mock_dt.now.return_value = now
        knowledge.load_configuration([_automation("Test", analysis.TRIGGER_AT_TIME, {"time": "22:30"})])
        # Record trigger 2 hours ago — past the 3600s cooldown
        knowledge.record_trigger("Test", analysis.TRIGGER_AT_TIME, datetime(2026, 1, 1, 20, 30))
        result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert len(result) == 1


def test_entity_state_cooldown_60s():
    knowledge.apply_state_change(_entity("binary_sensor.door", "on"))
    knowledge.load_configuration([_automation("Test", analysis.TRIGGER_ENTITY_STATE,
                                              {"entity_id": "binary_sensor.door", "state": "on"})])
    # Record trigger 30 seconds ago — within 60s cooldown
    knowledge.record_trigger("Test", analysis.TRIGGER_ENTITY_STATE, datetime(2026, 1, 1, 20, 29, 30))
    with patch("analysis.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 20, 30, 0)
        result = analysis.evaluate_automations(_entity("binary_sensor.door", "on"))
    assert result == []


# ---------------------------------------------------------------------------
# record_trigger written after fire
# ---------------------------------------------------------------------------

def test_record_trigger_written_on_fire():
    with patch("analysis.datetime") as mock_dt:
        now = datetime(2026, 1, 1, 20, 30)
        mock_dt.now.return_value = now
        knowledge.load_configuration([_automation("Test", analysis.TRIGGER_AT_TIME, {"time": "20:30"})])
        analysis.evaluate_automations(_entity("switch.x", "on"))
    record = knowledge.get_last_trigger("Test", analysis.TRIGGER_AT_TIME)
    assert record is not None
    assert record["fired_at"] == now


# ---------------------------------------------------------------------------
# Multiple automations
# ---------------------------------------------------------------------------

def test_multiple_automations_both_fire():
    knowledge.apply_state_change(_entity("sun.sun", "below_horizon"))
    knowledge.apply_state_change(_entity("binary_sensor.door", "on"))
    knowledge.load_configuration([
        _automation("Sunset",   analysis.TRIGGER_ON_SUNSET,    {}),
        _automation("Door Open", analysis.TRIGGER_ENTITY_STATE, {"entity_id": "binary_sensor.door", "state": "on"}),
    ])
    result = analysis.evaluate_automations(_entity("binary_sensor.door", "on"))
    names = [a["name"] for a in result]
    assert "Sunset" in names
    assert "Door Open" in names


def test_no_automations_returns_empty():
    result = analysis.evaluate_automations(_entity("switch.x", "on"))
    assert result == []
