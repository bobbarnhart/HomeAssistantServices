# config_example.py — committed skeleton showing every available option.
#
# Copy this file to config.py (gitignored) and replace the placeholder
# entity_id / area_id strings with your real Home Assistant values.
#
# Entity IDs: HA Settings → Devices & Services → Entities
# Area IDs:   HA Settings → Areas & Zones

# Logging level for the service.
# DEBUG shows all entity state changes and individual entities loaded at startup.
# INFO  shows trigger fires, actions sent, and connection events.
LOG_LEVEL = "INFO"

from analysis import TRIGGER_AT_TIME, TRIGGER_ENTITY_STATE, TRIGGER_ON_SUNSET
from execution import (
    SERVICE_LIGHT_TURN_OFF,
    SERVICE_LIGHT_TURN_ON,
    SERVICE_SWITCH_TURN_OFF,
    SERVICE_SWITCH_TURN_ON,
    TARGET_AREA,
    TARGET_ENTITY,
)

# ---------------------------------------------------------------------------
# Plans — named, ordered sequences of actions. No trigger logic here.
# ---------------------------------------------------------------------------

PLANS = [
    {
        "name": "prepare_for_nighttime",
        "steps": [
            # TARGET_ENTITY — address a single device by its entity_id
            {"target": "switch.wipe_warmer",   "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON,  "params": {}},
            {"target": "switch.recliner",      "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON,  "params": {}},
            {"target": "switch.air_filter",    "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON,  "params": {}},
            {"target": "switch.white_noise",   "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON,  "params": {}},
            {"target": "light.nursery_lamp",   "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_ON,   "params": {"brightness_pct": 30}},
            {"target": "light.bedroom_sconce", "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_ON,   "params": {"brightness_pct": 60}},
            # TARGET_AREA — address every entity in the named area
            {"target": "nursery",              "target_type": TARGET_AREA,   "service": SERVICE_LIGHT_TURN_ON,   "params": {"brightness_pct": 10}},
        ],
    },
    {
        "name": "nighttime_nursery_routine",
        "steps": [
            {"target": "light.nursery_lamp",   "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "light.crib_lamp",      "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "light.bedroom_sconce", "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "switch.white_noise",   "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON,  "params": {}},
        ],
    },
    {
        "name": "nighttime_house_routine",
        "steps": [
            {"target": "office",     "target_type": TARGET_AREA, "service": SERVICE_LIGHT_TURN_OFF, "params": {}},
            {"target": "guest_room", "target_type": TARGET_AREA, "service": SERVICE_LIGHT_TURN_OFF, "params": {}},
            {"target": "downstairs", "target_type": TARGET_AREA, "service": SERVICE_LIGHT_TURN_ON,  "params": {"brightness_pct": 10}},
        ],
    },
    {
        "name": "monitor_exterior",
        "steps": [
            {"target": "exterior", "target_type": TARGET_AREA, "service": SERVICE_LIGHT_TURN_ON, "params": {}},
        ],
    },
]

# ---------------------------------------------------------------------------
# Triggers — what causes each plan to run. References plans by name.
# ---------------------------------------------------------------------------

TRIGGERS = [
    # Time-based triggers (fire once per calendar day at the specified time)
    {"type": TRIGGER_AT_TIME, "params": {"time": "20:30"}, "plan": "prepare_for_nighttime"},
    {"type": TRIGGER_AT_TIME, "params": {"time": "21:00"}, "plan": "nighttime_nursery_routine"},
    {"type": TRIGGER_AT_TIME, "params": {"time": "22:00"}, "plan": "nighttime_house_routine"},

    # Condition-based triggers (fire once per calendar day when condition is met)
    {"type": TRIGGER_ON_SUNSET, "params": {}, "plan": "monitor_exterior"},

    # Stateful entity triggers (fire each time the entity reaches the specified state)
    {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "input_boolean.nighttime_prep",    "state": "on"}, "plan": "prepare_for_nighttime"},
    {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "input_boolean.nighttime_nursery", "state": "on"}, "plan": "nighttime_nursery_routine"},
    {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "input_boolean.nighttime_house",   "state": "on"}, "plan": "nighttime_house_routine"},

    # Button triggers (stateless — omit "state"; monitor handles cooldown)
    # {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "button.your_button"}, "plan": "your_plan"},
]
