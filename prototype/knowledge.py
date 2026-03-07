from datetime import datetime
from typing import TypedDict

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Entity = TypedDict("Entity", {
    "entity_id": str,
    "state":     str,
    "attributes": dict,
    "area_id":   str | None,
})

ManagedSystemState = dict[str, Entity]  # keyed by entity_id

TriggerDescriptor = TypedDict("TriggerDescriptor", {
    "type":   str,
    "params": dict,
})

ActionDescriptor = TypedDict("ActionDescriptor", {
    "target":      str,
    "target_type": str,
    "service":     str,
    "params":      dict,
})

Automation = TypedDict("Automation", {
    "name":     str,
    "triggers": list,
    "steps":    list,
})

SystemConfiguration = TypedDict("SystemConfiguration", {
    "automations": list,
})

ActionStep = TypedDict("ActionStep", {
    "entity_id": str,
    "service":   str,
    "params":    dict,
})

Plan = list  # list[ActionStep]

TriggerRecord = TypedDict("TriggerRecord", {
    "automation_name": str,
    "trigger_type":    str,
    "fired_at":        datetime,
})

ExecutionRecord = TypedDict("ExecutionRecord", {
    "automation_name": str,
    "plan":            Plan,
    "executed_at":     datetime,
})

AdaptationState = TypedDict("AdaptationState", {
    "trigger_history":   list,
    "execution_history": list,
})

# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

_state: ManagedSystemState = {}
_config: SystemConfiguration = {"automations": []}
_adaptation: AdaptationState = {"trigger_history": [], "execution_history": []}
_msg_counter: int = 0

# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def apply_state_change(entity: Entity) -> None:
    """Update live entity state. Called only by monitor."""
    _state[entity["entity_id"]] = entity


def load_configuration(automations: list) -> None:
    """Load automation config once at startup. Called only by main."""
    _config["automations"] = list(automations)


def record_trigger(automation_name: str, trigger_type: str, fired_at: datetime) -> None:
    """Record a trigger fire in AdaptationState. Called only by analysis."""
    _adaptation["trigger_history"].append({
        "automation_name": automation_name,
        "trigger_type":    trigger_type,
        "fired_at":        fired_at,
    })


def record_execution(automation_name: str, plan: Plan, executed_at: datetime) -> None:
    """Record a completed plan execution in AdaptationState. Called only by execution."""
    _adaptation["execution_history"].append({
        "automation_name": automation_name,
        "plan":            plan,
        "executed_at":     executed_at,
    })


def next_msg_id() -> int:
    """Return a unique, incrementing WebSocket message ID."""
    global _msg_counter
    _msg_counter += 1
    return _msg_counter

# ---------------------------------------------------------------------------
# Read helpers — available to all modules
# ---------------------------------------------------------------------------

def get_entity(entity_id: str) -> Entity | None:
    return _state.get(entity_id)


def entities_in_area(area_id: str) -> list[Entity]:
    return [e for e in _state.values() if e.get("area_id") == area_id]


def get_automations() -> list:
    return _config["automations"]


def get_last_trigger(automation_name: str, trigger_type: str) -> TriggerRecord | None:
    """Return the most recent TriggerRecord for the given automation+type, or None."""
    matches = [
        r for r in _adaptation["trigger_history"]
        if r["automation_name"] == automation_name and r["trigger_type"] == trigger_type
    ]
    return matches[-1] if matches else None


def get_all_entities() -> ManagedSystemState:
    return _state

# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def _reset() -> None:
    """Reset all stores to empty. Used by unit tests only."""
    global _msg_counter
    _state.clear()
    _config["automations"] = []
    _adaptation["trigger_history"].clear()
    _adaptation["execution_history"].clear()
    _msg_counter = 0
