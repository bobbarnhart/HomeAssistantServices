import pytest

import knowledge
import planning
from execution import SERVICE_LIGHT_TURN_ON, SERVICE_SWITCH_TURN_ON, TARGET_AREA, TARGET_ENTITY


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


def _plan(steps):
    return {"name": "Test", "steps": steps}


def test_build_plan_single_entity():
    plan = planning.build_plan(_plan([
        {"target": "light.lamp", "target_type": TARGET_ENTITY,
         "service": SERVICE_LIGHT_TURN_ON, "params": {"brightness_pct": 50}},
    ]))
    assert len(plan) == 1
    assert plan[0]["entity_id"] == "light.lamp"
    assert plan[0]["service"] == SERVICE_LIGHT_TURN_ON
    assert plan[0]["params"] == {"brightness_pct": 50}


def test_build_plan_area_expands_to_entities():
    knowledge.apply_state_change({"entity_id": "light.a", "state": "on", "attributes": {}, "area_id": "nursery"})
    knowledge.apply_state_change({"entity_id": "light.b", "state": "on", "attributes": {}, "area_id": "nursery"})
    plan = planning.build_plan(_plan([
        {"target": "nursery", "target_type": TARGET_AREA,
         "service": SERVICE_LIGHT_TURN_ON, "params": {}},
    ]))
    assert len(plan) == 2
    assert {s["entity_id"] for s in plan} == {"light.a", "light.b"}
    assert all(s["service"] == SERVICE_LIGHT_TURN_ON for s in plan)


def test_build_plan_area_with_no_entities_produces_empty():
    plan = planning.build_plan(_plan([
        {"target": "empty_room", "target_type": TARGET_AREA,
         "service": SERVICE_LIGHT_TURN_ON, "params": {}},
    ]))
    assert plan == []


def test_build_plan_mixed_entity_and_area():
    knowledge.apply_state_change({"entity_id": "light.area_light", "state": "on", "attributes": {}, "area_id": "office"})
    plan = planning.build_plan(_plan([
        {"target": "switch.fan",    "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON, "params": {}},
        {"target": "office",        "target_type": TARGET_AREA,   "service": SERVICE_LIGHT_TURN_ON,  "params": {}},
    ]))
    assert len(plan) == 2
    assert plan[0]["entity_id"] == "switch.fan"
    assert plan[1]["entity_id"] == "light.area_light"


def test_build_plan_preserves_params_per_step():
    plan = planning.build_plan(_plan([
        {"target": "light.a", "target_type": TARGET_ENTITY,
         "service": SERVICE_LIGHT_TURN_ON, "params": {"brightness_pct": 10}},
        {"target": "light.b", "target_type": TARGET_ENTITY,
         "service": SERVICE_LIGHT_TURN_ON, "params": {"brightness_pct": 80}},
    ]))
    assert plan[0]["params"] == {"brightness_pct": 10}
    assert plan[1]["params"] == {"brightness_pct": 80}


def test_build_plan_area_params_applied_to_all_entities():
    knowledge.apply_state_change({"entity_id": "light.a", "state": "on", "attributes": {}, "area_id": "living"})
    knowledge.apply_state_change({"entity_id": "light.b", "state": "on", "attributes": {}, "area_id": "living"})
    plan = planning.build_plan(_plan([
        {"target": "living", "target_type": TARGET_AREA,
         "service": SERVICE_LIGHT_TURN_ON, "params": {"brightness_pct": 5}},
    ]))
    assert all(s["params"] == {"brightness_pct": 5} for s in plan)
