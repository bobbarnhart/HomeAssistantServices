import asyncio
import json
import logging
import os
from typing import Awaitable, Callable

import websockets

import knowledge

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 5  # seconds between reconnect attempts

OnStateChange = Callable[[object, knowledge.Entity], Awaitable[None]]


async def _authenticate(ws) -> bool:
    msg = json.loads(await ws.recv())
    if msg.get("type") != "auth_required":
        logger.error("Expected auth_required, got: %s", msg.get("type"))
        return False

    await ws.send(json.dumps({"type": "auth", "access_token": os.environ["HA_TOKEN"]}))
    msg = json.loads(await ws.recv())

    if msg.get("type") != "auth_ok":
        logger.error("Authentication failed: %s", msg.get("message", "unknown"))
        return False

    logger.info("Authenticated with Home Assistant")
    return True


async def _fetch_initial_states(ws) -> None:
    msg_id = knowledge.next_msg_id()
    await ws.send(json.dumps({"id": msg_id, "type": "get_states"}))

    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("id") != msg_id or msg.get("type") != "result":
            continue
        entities = msg.get("result") or []
        for raw_entity in entities:
            entity: knowledge.Entity = {
                "entity_id": raw_entity["entity_id"],
                "state":     raw_entity["state"],
                "attributes": raw_entity.get("attributes", {}),
                "area_id":   (
                    raw_entity.get("area_id")
                    or raw_entity.get("attributes", {}).get("area_id")
                ),
            }
            knowledge.apply_state_change(entity)
            logger.debug("  loaded: %s = %s (area=%s)", entity["entity_id"], entity["state"], entity["area_id"])
        logger.info("Initial entity fetch complete: %d entities loaded", len(entities))
        return


async def _subscribe_state_changed(ws) -> int:
    msg_id = knowledge.next_msg_id()
    await ws.send(json.dumps({
        "id":         msg_id,
        "type":       "subscribe_events",
        "event_type": "state_changed",
    }))
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("id") == msg_id and msg.get("type") == "result":
            return msg_id


async def _event_loop(ws, sub_id: int, on_state_change: OnStateChange) -> None:
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") != "event" or msg.get("id") != sub_id:
            continue
        event_data = msg.get("event", {}).get("data", {})
        new_state = event_data.get("new_state")
        if not new_state:
            continue

        entity: knowledge.Entity = {
            "entity_id": new_state["entity_id"],
            "state":     new_state["state"],
            "attributes": new_state.get("attributes", {}),
            "area_id":   (
                new_state.get("area_id")
                or new_state.get("attributes", {}).get("area_id")
            ),
        }
        logger.debug("state_changed: %s → %s", entity["entity_id"], entity["state"])
        knowledge.apply_state_change(entity)
        await on_state_change(ws, entity)


async def run(on_state_change: OnStateChange) -> None:
    """Connect to HA, authenticate, seed state, and run the event loop.

    Reconnects automatically on connection drops. Raises on auth failure.
    The on_state_change callback receives (ws, entity) so downstream
    components can write back to HA on the same connection.
    """
    url = os.environ["HA_URL"]
    while True:
        try:
            logger.info("Connecting to Home Assistant at %s", url)
            async with websockets.connect(url) as ws:
                if not await _authenticate(ws):
                    raise RuntimeError("Authentication failed — check HA_TOKEN")
                await _fetch_initial_states(ws)
                sub_id = await _subscribe_state_changed(ws)
                await _event_loop(ws, sub_id, on_state_change)
        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("Connection dropped (%s), reconnecting in %ds", exc, _RECONNECT_DELAY)
            await asyncio.sleep(_RECONNECT_DELAY)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("Unexpected error: %s", exc, exc_info=True)
            raise
