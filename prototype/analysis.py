import logging
from datetime import datetime

import knowledge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trigger type constants
# ---------------------------------------------------------------------------

TRIGGER_AT_TIME      = "at_time"       # params: {"time": "HH:MM"}
TRIGGER_ON_SUNSET    = "on_sunset"     # params: {}
TRIGGER_ENTITY_STATE = "entity_state"  # params: {"entity_id": str} or {"entity_id": str, "state": str}

# ---------------------------------------------------------------------------
# Trigger evaluation handlers
# ---------------------------------------------------------------------------

def _eval_at_time(params: dict, entity: knowledge.Entity) -> bool:
    return datetime.now().strftime("%H:%M") == params.get("time", "")


def _eval_on_sunset(params: dict, entity: knowledge.Entity) -> bool:
    sun = knowledge.get_entity("sun.sun")
    return sun is not None and sun["state"] == "below_horizon"


def _eval_entity_state(params: dict, entity: knowledge.Entity) -> bool:
    if "state" not in params:
        # Stateless entity (button): fire only on the exact incoming event
        return entity["entity_id"] == params["entity_id"]
    target = knowledge.get_entity(params["entity_id"])
    if target is None:
        return False
    return target["state"] == params["state"]


# Dispatch table: trigger_type → handler
_DISPATCH: dict = {
    TRIGGER_AT_TIME:      _eval_at_time,
    TRIGGER_ON_SUNSET:    _eval_on_sunset,
    TRIGGER_ENTITY_STATE: _eval_entity_state,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_triggers(changed_entity: knowledge.Entity, request_id: str | None = None) -> list:
    """Return list of {"plan": PlanDescriptor, "request_id": str} for triggers that fired.

    Button triggers set the monitor-created request to PENDING.
    Time/condition triggers deduplicate per calendar day and create a PENDING request.
    Stateful entity triggers always fire and create a PENDING request.
    """
    fired = []
    now = datetime.now()
    today = now.date()

    for trigger in knowledge.get_triggers():
        handler = _DISPATCH.get(trigger["type"])
        if handler is None:
            logger.warning("Unknown trigger type: %s", trigger["type"])
            continue

        if not handler(trigger["params"], changed_entity):
            continue

        plan = knowledge.get_plan(trigger["plan"])
        if plan is None:
            logger.warning("Unknown plan: %r", trigger["plan"])
            continue

        is_button = trigger["type"] == TRIGGER_ENTITY_STATE and "state" not in trigger["params"]

        if is_button:
            # Request was created by monitor; set it to PENDING
            if request_id is None:
                logger.warning("Button trigger fired without request_id: plan=%r", trigger["plan"])
                continue
            knowledge.update_request_status(request_id, knowledge.REQUEST_PENDING)
            logger.info("Request PENDING: plan=%r id=%s", trigger["plan"], request_id)
            fired.append({"plan": plan, "request_id": request_id})
        else:
            # Time/condition triggers: deduplicate per calendar day
            if trigger["type"] in (TRIGGER_AT_TIME, TRIGGER_ON_SUNSET):
                last_req = knowledge.get_last_request_for_plan(trigger["plan"], trigger["type"])
                if last_req is not None and last_req["created_at"].date() == today:
                    logger.info(
                        "Trigger skipped — already fired today: plan=%r type=%s",
                        trigger["plan"], trigger["type"],
                    )
                    continue

            req = knowledge.create_request(
                None, trigger["plan"], trigger["type"], knowledge.REQUEST_PENDING, now,
            )
            logger.info(
                "Request PENDING: plan=%r type=%s id=%s",
                trigger["plan"], trigger["type"], req["id"],
            )
            fired.append({"plan": plan, "request_id": req["id"]})

    if not fired:
        logger.debug("Evaluation pass complete: no triggers fired")

    return fired
