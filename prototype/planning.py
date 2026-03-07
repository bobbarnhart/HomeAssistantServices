import logging

import knowledge
from execution import TARGET_AREA, TARGET_ENTITY

logger = logging.getLogger(__name__)


def build_plan(automation: knowledge.Automation) -> knowledge.Plan:
    """Resolve an automation's steps into a flat, concrete Plan.

    TARGET_ENTITY steps are emitted directly.
    TARGET_AREA steps are expanded to one ActionStep per entity in that area.
    """
    plan: knowledge.Plan = []

    for step in automation["steps"]:
        if step["target_type"] == TARGET_ENTITY:
            plan.append({
                "entity_id": step["target"],
                "service":   step["service"],
                "params":    step["params"],
            })
        elif step["target_type"] == TARGET_AREA:
            entities = knowledge.entities_in_area(step["target"])
            logger.debug(
                "Area expansion: area=%r resolved %d entities",
                step["target"], len(entities),
            )
            for entity in entities:
                plan.append({
                    "entity_id": entity["entity_id"],
                    "service":   step["service"],
                    "params":    step["params"],
                })

    logger.info(
        "Plan generated: automation=%r steps=%d",
        automation["name"], len(plan),
    )
    return plan
