import logging
from datetime import datetime

import knowledge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trigger type constants
# ---------------------------------------------------------------------------

TRIGGER_AT_TIME      = "at_time"       # params: {"time": "HH:MM"}
TRIGGER_ON_SUNSET    = "on_sunset"     # params: {}
TRIGGER_ENTITY_STATE = "entity_state"  # params: {"entity_id": str, "state": str}

# ---------------------------------------------------------------------------
# Trigger evaluation handlers
# ---------------------------------------------------------------------------

def _eval_at_time(params: dict, entity: knowledge.Entity) -> bool:
    return datetime.now().strftime("%H:%M") == params.get("time", "")


def _eval_on_sunset(params: dict, entity: knowledge.Entity) -> bool:
    sun = knowledge.get_entity("sun.sun")
    return sun is not None and sun["state"] == "below_horizon"


def _eval_entity_state(params: dict, entity: knowledge.Entity) -> bool:
    target = knowledge.get_entity(params["entity_id"])
    if target is None:
        return False
    if "state" not in params:
        return True  # stateless entity (e.g. button) — presence is sufficient
    return target["state"] == params["state"]


# Dispatch table: trigger_type → (handler, cooldown_seconds)
# Add new trigger types here only — config.py is never modified for this.
_DISPATCH: dict = {
    TRIGGER_AT_TIME:      (_eval_at_time,      3600),
    TRIGGER_ON_SUNSET:    (_eval_on_sunset,    3600),
    TRIGGER_ENTITY_STATE: (_eval_entity_state,   5),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_automations(changed_entity: knowledge.Entity) -> list:
    """Return automations whose triggers have fired, respecting per-type cooldowns.

    Each automation is returned at most once even if multiple triggers match.
    """
    fired = []
    now = datetime.now()

    for automation in knowledge.get_automations():
        for trigger in automation["triggers"]:
            entry = _DISPATCH.get(trigger["type"])
            if entry is None:
                logger.warning("Unknown trigger type: %s", trigger["type"])
                continue

            handler, cooldown_secs = entry
            if not handler(trigger["params"], changed_entity):
                continue

            # Condition met — check cooldown before firing
            last = knowledge.get_last_trigger(automation["name"], trigger["type"])
            if last is not None:
                elapsed = (now - last["fired_at"]).total_seconds()
                if elapsed < cooldown_secs:
                    logger.info(
                        "Trigger skipped — cooldown active: automation=%r type=%s remaining=%.0fs",
                        automation["name"], trigger["type"], cooldown_secs - elapsed,
                    )
                    break

            logger.info(
                "Trigger fired: automation=%r type=%s",
                automation["name"], trigger["type"],
            )
            knowledge.record_trigger(automation["name"], trigger["type"], now)
            fired.append(automation)
            break  # first matching trigger per automation is sufficient

    if not fired:
        logger.debug("Evaluation pass complete: no triggers fired")

    return fired
