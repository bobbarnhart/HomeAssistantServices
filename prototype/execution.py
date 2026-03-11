import json
import logging
from datetime import datetime

import knowledge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service constants
# ---------------------------------------------------------------------------

SERVICE_LIGHT_TURN_ON   = "light/turn_on"
SERVICE_LIGHT_TURN_OFF  = "light/turn_off"
SERVICE_SWITCH_TURN_ON  = "switch/turn_on"
SERVICE_SWITCH_TURN_OFF = "switch/turn_off"

# ---------------------------------------------------------------------------
# Target type constants
# ---------------------------------------------------------------------------

TARGET_ENTITY = "entity"
TARGET_AREA   = "area"


async def send_action(ws, step: knowledge.ActionStep) -> None:
    """Send a single call_service command to HA. Fire-and-forget."""
    domain, service = step["service"].split("/", 1)
    payload = {
        "id":           knowledge.next_msg_id(),
        "type":         "call_service",
        "domain":       domain,
        "service":      service,
        "target":       {"entity_id": step["entity_id"]},
        "service_data": step["params"],
    }
    try:
        await ws.send(json.dumps(payload))
        logger.info("Action sent: %s → %s", step["service"], step["entity_id"])
    except Exception as exc:
        logger.error(
            "call_service failed: %s → %s: %s",
            step["service"], step["entity_id"], exc,
        )
        raise


async def execute_plan(ws, plan: knowledge.Plan, automation_name: str, request_id: str | None = None) -> None:
    """Send every action step in the plan sequentially, then record the execution."""
    for step in plan:
        await send_action(ws, step)
    knowledge.record_execution(automation_name, plan, datetime.now())
    if request_id is not None:
        knowledge.update_request_status(request_id, knowledge.REQUEST_COMPLETED)
