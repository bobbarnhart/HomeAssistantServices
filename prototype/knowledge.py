import uuid
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

TriggerConfig = TypedDict("TriggerConfig", {
    "type":   str,   # TRIGGER_* constant
    "params": dict,  # type-specific parameters
    "plan":   str,   # name of the plan to execute
})

ActionDescriptor = TypedDict("ActionDescriptor", {
    "target":      str,
    "target_type": str,
    "service":     str,
    "params":      dict,
})

PlanDescriptor = TypedDict("PlanDescriptor", {
    "name":  str,
    "steps": list,  # list[ActionDescriptor]
})

SystemConfiguration = TypedDict("SystemConfiguration", {
    "plans":    list,  # list[PlanDescriptor]
    "triggers": list,  # list[TriggerConfig]
})

ActionStep = TypedDict("ActionStep", {
    "entity_id": str,
    "service":   str,
    "params":    dict,
})

Plan = list  # list[ActionStep]

# ---------------------------------------------------------------------------
# Request model (button / stateless trigger lifecycle)
# ---------------------------------------------------------------------------

BUTTON_COOLDOWN_SECS = 5

REQUEST_NEW       = "NEW"
REQUEST_PENDING   = "PENDING"
REQUEST_COMPLETED = "COMPLETED"
REQUEST_REJECTED  = "REJECTED"

Request = TypedDict("Request", {
    "id":           str,
    "entity_id":    str | None,   # set for button requests; None for time/condition triggers
    "plan_name":    str,
    "trigger_type": str,
    "status":       str,
    "created_at":   datetime,
})

ExecutionRecord = TypedDict("ExecutionRecord", {
    "plan_name":   str,
    "plan":        Plan,
    "executed_at": datetime,
})

AdaptationState = TypedDict("AdaptationState", {
    "execution_history": list,  # list[ExecutionRecord]
})

# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

_state: ManagedSystemState = {}
_config: SystemConfiguration = {"plans": [], "triggers": []}
_adaptation: AdaptationState = {"execution_history": []}
_requests: list = []
_msg_counter: int = 0

# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def apply_state_change(entity: Entity) -> None:
    """Update live entity state. Called only by monitor."""
    _state[entity["entity_id"]] = entity


def load_configuration(plans: list, triggers: list) -> None:
    """Load plan and trigger config once at startup. Called only by main."""
    _config["plans"] = list(plans)
    _config["triggers"] = list(triggers)


def record_execution(plan_name: str, plan: Plan, executed_at: datetime) -> None:
    """Record a completed plan execution in AdaptationState. Called only by execution."""
    _adaptation["execution_history"].append({
        "plan_name":   plan_name,
        "plan":        plan,
        "executed_at": executed_at,
    })


def create_request(entity_id: str | None, plan_name: str, trigger_type: str, status: str, created_at: datetime) -> Request:
    """Create and store a new request. Called by monitor and analysis."""
    req: Request = {
        "id":           str(uuid.uuid4()),
        "entity_id":    entity_id,
        "plan_name":    plan_name,
        "trigger_type": trigger_type,
        "status":       status,
        "created_at":   created_at,
    }
    _requests.append(req)
    return req


def update_request_status(request_id: str, status: str) -> None:
    """Update the status of an existing request. Called by analysis and execution."""
    for req in _requests:
        if req["id"] == request_id:
            req["status"] = status
            return


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


def get_plan(name: str) -> PlanDescriptor | None:
    """Return the PlanDescriptor with the given name, or None."""
    matches = [p for p in _config["plans"] if p["name"] == name]
    return matches[0] if matches else None


def get_triggers() -> list:
    return _config["triggers"]


def get_trigger_for_entity(entity_id: str) -> TriggerConfig | None:
    """Return the stateless trigger config matching entity_id, or None."""
    for trigger in _config["triggers"]:
        if (trigger["type"] == "entity_state"
                and trigger["params"].get("entity_id") == entity_id
                and "state" not in trigger["params"]):
            return trigger
    return None


def get_last_request(entity_id: str) -> Request | None:
    """Return the most recent Request for the given entity_id, or None."""
    matches = [r for r in _requests if r["entity_id"] == entity_id]
    return matches[-1] if matches else None


def get_last_request_for_plan(plan_name: str, trigger_type: str) -> Request | None:
    """Return the most recent Request for the given plan+trigger_type, or None."""
    matches = [
        r for r in _requests
        if r["plan_name"] == plan_name and r["trigger_type"] == trigger_type
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
    _config["plans"] = []
    _config["triggers"] = []
    _adaptation["execution_history"].clear()
    _requests.clear()
    _msg_counter = 0
