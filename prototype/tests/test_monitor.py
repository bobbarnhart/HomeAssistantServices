import json

import pytest

import knowledge
import monitor


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


class MockWebSocket:
    """Simulates a WebSocket by replaying a fixed sequence of messages."""

    def __init__(self, messages: list):
        self._messages = list(messages)
        self._pos = 0
        self.sent: list = []

    async def recv(self) -> str:
        if self._pos >= len(self._messages):
            raise RuntimeError("MockWebSocket: no more messages")
        msg = self._messages[self._pos]
        self._pos += 1
        return json.dumps(msg)

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if self._pos >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._pos]
        self._pos += 1
        return json.dumps(msg)


# ---------------------------------------------------------------------------
# _authenticate
# ---------------------------------------------------------------------------

async def test_authenticate_success(monkeypatch):
    monkeypatch.setenv("HA_TOKEN", "test-token")
    ws = MockWebSocket([
        {"type": "auth_required"},
        {"type": "auth_ok"},
    ])
    result = await monitor._authenticate(ws)
    assert result is True
    assert ws.sent[0] == {"type": "auth", "access_token": "test-token"}


async def test_authenticate_failure(monkeypatch):
    monkeypatch.setenv("HA_TOKEN", "bad-token")
    ws = MockWebSocket([
        {"type": "auth_required"},
        {"type": "auth_invalid", "message": "Token invalid"},
    ])
    result = await monitor._authenticate(ws)
    assert result is False


async def test_authenticate_unexpected_first_message(monkeypatch):
    monkeypatch.setenv("HA_TOKEN", "token")
    ws = MockWebSocket([{"type": "something_else"}])
    result = await monitor._authenticate(ws)
    assert result is False


# ---------------------------------------------------------------------------
# _fetch_initial_states
# ---------------------------------------------------------------------------

async def test_fetch_initial_states_populates_knowledge():
    # After reset, next_msg_id() returns 1 — matches the response id below
    ws = MockWebSocket([
        {"id": 1, "type": "result", "result": [
            {"entity_id": "light.test", "state": "on", "attributes": {}, "area_id": None},
        ]},
    ])
    await monitor._fetch_initial_states(ws)
    entity = knowledge.get_entity("light.test")
    assert entity is not None
    assert entity["state"] == "on"


async def test_fetch_initial_states_empty_result():
    ws = MockWebSocket([
        {"id": 1, "type": "result", "result": []},
    ])
    await monitor._fetch_initial_states(ws)
    assert knowledge.get_all_entities() == {}


async def test_fetch_initial_states_skips_mismatched_id():
    # First message has wrong id, second has correct id
    ws = MockWebSocket([
        {"id": 99, "type": "result", "result": [{"entity_id": "light.wrong", "state": "on", "attributes": {}, "area_id": None}]},
        {"id": 1,  "type": "result", "result": [{"entity_id": "light.correct", "state": "on", "attributes": {}, "area_id": None}]},
    ])
    await monitor._fetch_initial_states(ws)
    assert knowledge.get_entity("light.correct") is not None
    assert knowledge.get_entity("light.wrong") is None


# ---------------------------------------------------------------------------
# _event_loop
# ---------------------------------------------------------------------------

async def test_event_loop_updates_knowledge_on_state_change():
    received = []

    async def on_change(ws, entity):
        received.append(entity)

    sub_id = 2
    ws = MockWebSocket([
        {
            "type": "event",
            "id": sub_id,
            "event": {"data": {"new_state": {
                "entity_id": "light.bedroom",
                "state": "on",
                "attributes": {"brightness": 200},
                "area_id": "bedroom",
            }}},
        },
    ])
    await monitor._event_loop(ws, sub_id, on_change)
    assert len(received) == 1
    assert received[0]["entity_id"] == "light.bedroom"
    assert knowledge.get_entity("light.bedroom")["state"] == "on"


async def test_event_loop_ignores_wrong_sub_id():
    received = []

    async def on_change(ws, entity):
        received.append(entity)

    ws = MockWebSocket([
        {"type": "event", "id": 99, "event": {"data": {"new_state": {
            "entity_id": "light.x", "state": "on", "attributes": {}, "area_id": None,
        }}}},
    ])
    await monitor._event_loop(ws, 2, on_change)
    assert received == []


async def test_event_loop_ignores_missing_new_state():
    received = []

    async def on_change(ws, entity):
        received.append(entity)

    sub_id = 2
    ws = MockWebSocket([
        {"type": "event", "id": sub_id, "event": {"data": {"new_state": None}}},
    ])
    await monitor._event_loop(ws, sub_id, on_change)
    assert received == []
