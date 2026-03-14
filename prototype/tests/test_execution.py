import json

import pytest

import execution
import knowledge


@pytest.fixture(autouse=True)
def reset():
    knowledge._reset()


class MockWebSocket:
    def __init__(self):
        self.sent: list = []

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))


class FailingWebSocket:
    async def send(self, data: str) -> None:
        raise ConnectionError("connection closed")


# ---------------------------------------------------------------------------
# send_action
# ---------------------------------------------------------------------------

async def test_send_action_correct_payload():
    ws = MockWebSocket()
    step = {"entity_id": "light.lamp", "service": "light/turn_on", "params": {"brightness_pct": 50}}
    await execution.send_action(ws, step)
    assert len(ws.sent) == 1
    msg = ws.sent[0]
    assert msg["type"] == "call_service"
    assert msg["domain"] == "light"
    assert msg["service"] == "turn_on"
    assert msg["target"]["entity_id"] == "light.lamp"
    assert msg["service_data"] == {"brightness_pct": 50}


async def test_send_action_includes_msg_id():
    ws = MockWebSocket()
    step = {"entity_id": "switch.x", "service": "switch/turn_on", "params": {}}
    await execution.send_action(ws, step)
    assert isinstance(ws.sent[0]["id"], int)


async def test_send_action_raises_on_failure():
    step = {"entity_id": "light.x", "service": "light/turn_on", "params": {}}
    with pytest.raises(ConnectionError):
        await execution.send_action(FailingWebSocket(), step)


# ---------------------------------------------------------------------------
# execute_plan
# ---------------------------------------------------------------------------

async def test_execute_plan_sends_all_steps_in_order():
    ws = MockWebSocket()
    plan = [
        {"entity_id": "light.a", "service": "light/turn_on",  "params": {}},
        {"entity_id": "light.b", "service": "light/turn_off", "params": {}},
    ]
    await execution.execute_plan(ws, plan, "Test Auto")
    assert len(ws.sent) == 2
    assert ws.sent[0]["target"]["entity_id"] == "light.a"
    assert ws.sent[1]["target"]["entity_id"] == "light.b"


async def test_execute_plan_records_execution():
    ws = MockWebSocket()
    plan = [{"entity_id": "switch.x", "service": "switch/turn_on", "params": {}}]
    await execution.execute_plan(ws, plan, "My Auto")
    history = knowledge._adaptation["execution_history"]
    assert len(history) == 1
    assert history[0]["automation_name"] == "My Auto"
    assert history[0]["plan"] == plan
    assert history[0]["executed_at"] is not None


async def test_execute_plan_empty_plan_still_records():
    ws = MockWebSocket()
    await execution.execute_plan(ws, [], "Empty Auto")
    assert len(ws.sent) == 0
    history = knowledge._adaptation["execution_history"]
    assert len(history) == 1
    assert history[0]["automation_name"] == "Empty Auto"


