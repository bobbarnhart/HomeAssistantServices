import asyncio
import importlib
import logging

import analysis
import execution
import knowledge
import monitor
import planning

logger = logging.getLogger(__name__)


async def _main() -> None:
    try:
        cfg = importlib.import_module("config")
    except ModuleNotFoundError:
        logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        logger.error(
            "config.py not found — copy config_example.py to config.py and fill in your values"
        )
        return

    logging.basicConfig(
        level=getattr(logging, getattr(cfg, "LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    knowledge.load_configuration(cfg.PLANS, cfg.TRIGGERS)
    logger.info(
        "Service starting: %d plan(s), %d trigger(s) loaded",
        len(cfg.PLANS), len(cfg.TRIGGERS),
    )

    async def on_state_change(ws, entity: knowledge.Entity, request_id: str | None = None) -> None:
        fired = analysis.evaluate_triggers(entity, request_id)
        for item in fired:
            action_plan = planning.build_plan(item["plan"])
            await execution.execute_plan(ws, action_plan, item["plan"]["name"], item["request_id"])

    await monitor.run(on_state_change)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
