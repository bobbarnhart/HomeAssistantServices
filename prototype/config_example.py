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

AUTOMATIONS = [
    {
        "name": "Prepare for Nighttime",
        "triggers": [
            # Fire at a specific wall-clock time (24-hour HH:MM)
            {"type": TRIGGER_AT_TIME,      "params": {"time": "20:30"}},
            # Fire when an entity reaches a specific state
            {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "input_boolean.nighttime_prep", "state": "on"}},
        ],
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
        "name": "Nighttime Nursery Routine",
        "triggers": [
            {"type": TRIGGER_AT_TIME,      "params": {"time": "21:00"}},
            {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "input_boolean.nighttime_nursery", "state": "on"}},
        ],
        "steps": [
            {"target": "light.nursery_lamp",   "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "light.crib_lamp",      "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "light.bedroom_sconce", "target_type": TARGET_ENTITY, "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "switch.white_noise",   "target_type": TARGET_ENTITY, "service": SERVICE_SWITCH_TURN_ON,  "params": {}},
        ],
    },
    {
        "name": "Nighttime House Routine",
        "triggers": [
            {"type": TRIGGER_AT_TIME,      "params": {"time": "22:00"}},
            {"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "input_boolean.nighttime_house", "state": "on"}},
        ],
        "steps": [
            {"target": "office",     "target_type": TARGET_AREA,   "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "guest_room", "target_type": TARGET_AREA,   "service": SERVICE_LIGHT_TURN_OFF,  "params": {}},
            {"target": "downstairs", "target_type": TARGET_AREA,   "service": SERVICE_LIGHT_TURN_ON,   "params": {"brightness_pct": 10}},
        ],
    },
    {
        "name": "Monitor Exterior",
        "triggers": [
            # Fire when sun.sun transitions to below_horizon (sunset)
            {"type": TRIGGER_ON_SUNSET, "params": {}},
        ],
        "steps": [
            {"target": "exterior", "target_type": TARGET_AREA, "service": SERVICE_LIGHT_TURN_ON, "params": {}},
        ],
    },
]
