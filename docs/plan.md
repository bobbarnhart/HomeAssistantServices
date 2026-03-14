# Plan

## Overview

This service works alongside a running Home Assistant instance on a Raspberry Pi. It uses the HA WebSocket API to consume entity state, evaluate user-defined automations, and publish actions back to HA.


---

## Requirements

### Operation

The service establishes a persistent connection to the local HA instance using a URL and token provided at runtime. On startup it fetches all known entities (smart bulbs, plugs, etc.) and keeps them up to date as state changes arrive. New entities that appear while the service is running are also captured.

The service publishes actions driven by user-configured automations. Each automation specifies which entities and/or areas it targets.

### Security

- No secrets or personal data in any committed file
- Connection credentials sourced from the environment at runtime, never hardcoded
- User automation configuration kept out of version control; a committed example file with placeholder values is provided instead
- Dependencies kept minimal — only include a dependency if it meaningfully reduces complexity or security risk

### Logging

All major events and errors are logged. Each component logs the events relevant to its responsibility. No secrets or raw entity state values are written to logs at normal verbosity. Higher verbosity (debug) may include entity identifiers and state values.

### Testing

Unit tests should be created for all individual modules showing the ability to validate individual behavior.

---

## Architectural Approach: Simplified MAPE-K

The service implements a simplified MAPE-K (Monitor, Analyze, Plan, Execute) loop with a shared Knowledge store. The intent is a self-adaptive system that responds to environment changes and generates plans accordingly. Each component has a single responsibility and a defined direction of data flow:

```
Home Assistant
      |
   [Monitor]  ──writes──▶  [Knowledge]
                                |
                           [Analysis]  ──replan trigger──▶  [Planning]
                                                                 |
                                                           [Execution]
                                                                 |
                                                      Home Assistant
```

| MAPE-K Role | Responsibility |
|---|---|
| **Knowledge** | Three stores: live entity state + loaded automation config + adaptation state (trigger/execution history) |
| **Monitor** | Consumes HA WebSocket events, updates ManagedSystemState |
| **Analysis** | Reads all stores, evaluates trigger descriptors, enforces cooldowns, fires replan signal |
| **Planning** | Given a triggered automation, resolves entities and generates an ordered action list |
| **Execution** | Sends the generated action list to HA via WebSocket, records execution in AdaptationState |

## Implementation Details  & Notes

* Triggers should be separate from plans. Plans are generated DAG's (or lists for initial prototype) of what should be done when designed statically. Triggers (button presses, times) should be configured separately from these such that additional triggers can be added later separate from plan implementation details. For a button press, it will contain the information corresponding to the named plan to execute, meaning that the config does not specify anything regarding the button details. A timer however, can be specified by the config that correspond to one or more plans to execute. Other conditions such as 'sunset' are valid plan triggers.

* A button press is considered a request that monitor consumes and writes to knowledge with a state of the request (not the button). As the request is handled (analyze sees the corresponding plan the button press wants to activate, recommends to plan to generate etc.) the request's status is updated.

* A time or condition trigger dependent on a time should be triggered via analyze recognizing the condition is met, generating the plan recommendation, and executing. To avoid thrashing/re-triggering, the analyze should record when the condition was last done, so that next attempts see that it was already triggered for the current day.

--------------- DO NOT EDIT ANYTHING ABOVE ----------------------

## Prototype Implementation

### Decomposition

The five MAPE-K roles plus two supporting concerns map to modules:

1. **`knowledge.py`** — Three datastores and their read/write helpers
2. **`monitor.py`** — WebSocket connection and event ingestion
3. **`analysis.py`** — Trigger evaluation, trigger type constants, dispatch, and cooldown enforcement
4. **`planning.py`** — Action list generation from automation config
5. **`execution.py`** — HA service call primitives, service/target constants
6. **`config.py`** — User-defined automation data (gitignored)
7. **`main.py`** — Entry point, wires the loop together

No circular dependencies: data flows strictly Knowledge → Analysis → Planning → Execution.

### Module Structure

```
homeassistant/
├── prototype/
│   ├── main.py              # Entry point — wires MAPE-K loop
│   ├── config.py            # Gitignored — user automation definitions (pure data)
│   ├── config_example.py    # Committed — placeholder config showing all options
│   ├── knowledge.py         # All three Knowledge stores + helpers
│   ├── monitor.py           # WebSocket connect, auth, event ingestion → writes to Knowledge
│   ├── analysis.py          # Trigger type constants + evaluation dispatch + cooldown
│   ├── planning.py          # Resolves entities, generates ordered action list
│   ├── execution.py         # Sends action list to HA via call_service
│   ├── tests/
│   │   ├── test_knowledge.py
│   │   ├── test_monitor.py
│   │   ├── test_analysis.py
│   │   ├── test_planning.py
│   │   └── test_execution.py
│   ├── Dockerfile
│   └── docker-compose.yml
└── .env.example             # Documents required env vars, never committed with values
```

`.gitignore` excludes `prototype/config.py`, tracks `prototype/config_example.py`.

### Data Structures

#### Constants

All identifiers are named constants — no raw strings outside their definition files:

```python
# analysis.py — trigger type constants
TRIGGER_AT_TIME      = "at_time"       # params: {"time": "HH:MM"}
TRIGGER_ON_SUNSET    = "on_sunset"     # params: {}
TRIGGER_ENTITY_STATE = "entity_state"  # params: {"entity_id": str, "state": str}

# execution.py — service and target constants
SERVICE_LIGHT_TURN_ON   = "light/turn_on"
SERVICE_LIGHT_TURN_OFF  = "light/turn_off"
SERVICE_SWITCH_TURN_ON  = "switch/turn_on"
SERVICE_SWITCH_TURN_OFF = "switch/turn_off"

TARGET_ENTITY = "entity"
TARGET_AREA   = "area"
```

#### Knowledge Stores

```python
# knowledge.py

# ManagedSystemState — live entity data, written by Monitor on every state_changed event
Entity = TypedDict("Entity", {
    "entity_id": str,
    "state":     str,
    "attributes": dict,
    "area_id":   str | None,
})
ManagedSystemState = dict[str, Entity]  # keyed by entity_id

# SystemConfiguration — loaded once at startup from config.py, never mutated at runtime
Automation = TypedDict("Automation", {
    "name":     str,
    "triggers": list,  # list[TriggerDescriptor]
    "steps":    list,  # list[ActionDescriptor]
})
SystemConfiguration = TypedDict("SystemConfiguration", {
    "automations": list,
})

# AdaptationState — transactional record of MAPE-K decisions; written by Analysis and Execution
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
    "trigger_history":   list,  # list[TriggerRecord]
    "execution_history": list,  # list[ExecutionRecord]
})
```

`AdaptationState` provides a stateful representation of decision-making across the service lifetime. It is not persisted across restarts.

#### Trigger Descriptors (Analysis)

Triggers are pure data dicts referencing a `TRIGGER_*` type constant. Analysis dispatches to built-in evaluation logic based on the type — no user-defined functions:

```python
TriggerDescriptor = TypedDict("TriggerDescriptor", {
    "type":   str,   # TRIGGER_* constant
    "params": dict,  # type-specific parameters
})

# Examples in config.py:
{"type": TRIGGER_AT_TIME,      "params": {"time": "20:30"}}
{"type": TRIGGER_ON_SUNSET,    "params": {}}
{"type": TRIGGER_ENTITY_STATE, "params": {"entity_id": "binary_sensor.baby_monitor", "state": "on"}}
```

Analysis maintains a dispatch table mapping each `TRIGGER_*` constant to its evaluation function and cooldown. Adding a new trigger type means adding one entry to this table in `analysis.py` — config stays data-only.

#### Action Descriptors and Plan (Planning / Execution)

```python
# Config — what to do and for whom (area targets resolved later by Planning)
ActionDescriptor = TypedDict("ActionDescriptor", {
    "target":      str,   # entity_id or area_id
    "target_type": str,   # TARGET_ENTITY | TARGET_AREA
    "service":     str,   # SERVICE_* constant
    "params":      dict,  # e.g. {"brightness_pct": 30}
})

# Planning output — concrete, fully-resolved steps (areas already expanded)
ActionStep = TypedDict("ActionStep", {
    "entity_id": str,
    "service":   str,
    "params":    dict,
})

# Sequential list; alias kept thin so it can be replaced with a DAG later
Plan = list  # list[ActionStep]
```

Data flow summary:
- `TriggerDescriptor` — lives in config, evaluated by Analysis
- `ActionDescriptor` — lives in config, consumed by Planning
- `ActionStep` — produced by Planning, consumed by Execution
- `Plan` — the handoff between Planning and Execution; pure data throughout

### Component Breakdown

#### Knowledge (`knowledge.py`)

Holds all three stores and controls write access:
- `ManagedSystemState` — written only by Monitor via `apply_state_change(entity)`
- `SystemConfiguration` — written once at startup by `main.py` via `load_configuration(automations)`; immutable at runtime
- `AdaptationState` — written by Analysis via `record_trigger(...)` and by Execution via `record_execution(...)`

Read helpers available to all modules: `get_entity(entity_id)`, `entities_in_area(area_id)`, `get_automations()`, `get_last_trigger(automation_name, trigger_type)`.

#### Monitor (`monitor.py`)

Owns the WebSocket connection to HA. Responsibilities:
- Authenticate using token from environment
- On startup: fetch all entities via `get_states` and populate `ManagedSystemState`
- Subscribe to `state_changed` events
- On each event: call `apply_state_change` on Knowledge, then invoke the `on_state_change(ws, entity)` callback

Auth handshake:
```
→ {"type": "auth", "access_token": "..."}
← {"type": "auth_ok"}
→ {"id": 1, "type": "subscribe_events", "event_type": "state_changed"}
```

Fully event-driven — no polling. Reconnects on drop with basic retry.

#### Analysis (`analysis.py`)

Evaluates trigger descriptors against all Knowledge stores. Responsibilities:
- For each automation, evaluate each `TriggerDescriptor` against `ManagedSystemState`
- Dispatch by `trigger["type"]` to the appropriate built-in handler:
  - `TRIGGER_AT_TIME` — compare current time against `params["time"]`
  - `TRIGGER_ON_SUNSET` — check `sun.sun` entity state in `ManagedSystemState`
  - `TRIGGER_ENTITY_STATE` — check target entity's state in `ManagedSystemState`
- **Before firing**, consult `AdaptationState` via `get_last_trigger` and compare against the per-trigger-type cooldown. Skip if within the cooldown window:
  - `TRIGGER_AT_TIME`: 3600s — prevents re-firing within the same hour
  - `TRIGGER_ON_SUNSET`: 3600s — prevents re-firing within an hour of the last sunset trigger
  - `TRIGGER_ENTITY_STATE`: 60s — debounces rapidly flapping entity state
- **After firing**, call `record_trigger(automation_name, trigger_type, now)` to update `AdaptationState`

New trigger types are added by registering a handler and cooldown in Analysis's dispatch table — `config.py` is never modified for this.

#### Planning (`planning.py`)

Generates a `Plan` from a triggered automation. Responsibilities:
- For each `ActionDescriptor` in `automation["steps"]`:
  - `TARGET_ENTITY`: emit one `ActionStep` directly
  - `TARGET_AREA`: call `entities_in_area`, emit one `ActionStep` per entity
- Return the complete `Plan`

Planning is pure — reads data, produces a `Plan`, sends nothing.

#### Execution (`execution.py`)

Sends a `Plan` to HA. Responsibilities:
- For each `ActionStep`, send a `call_service` WebSocket command using `entity_id`, `service`, and `params`
- After all steps are sent, call `record_execution(automation_name, plan, now)` to update `AdaptationState`

The only component that writes back to HA.

#### Configuration (`config.py`)

Gitignored, user-edited, plain Python. Entirely data — trigger descriptors, action descriptors, entity/area IDs. `config_example.py` is committed with placeholder entity IDs and all available constants documented.

#### Entry Point (`main.py`)

Wires the MAPE-K loop:
1. Configure logging via `logging.basicConfig`
2. Import `config.py`, call `load_configuration(AUTOMATIONS)` to populate `SystemConfiguration`
3. Connect Monitor → populate `ManagedSystemState`
4. Start event loop: Monitor emits → Analysis evaluates → Planning generates `Plan` → Execution sends

Single `asyncio` event loop. No threads, no polling.

### Automations Breakdown

| Automation | Trigger Descriptors | Key Steps |
|---|---|---|
| Prepare for Nighttime | `TRIGGER_AT_TIME` or `TRIGGER_ENTITY_STATE` | Warmer on, dim nursery lamps, recliner on, air filter on, white noise on, bedroom sconces to reading level |
| Nighttime Nursery Routine | `TRIGGER_AT_TIME` or `TRIGGER_ENTITY_STATE` | Lamps off, sconces off, white noise on |
| Nighttime House Routine | `TRIGGER_AT_TIME` or `TRIGGER_ENTITY_STATE` | Office/guest lights off, downstairs lights to dim |
| Monitor Exterior | `TRIGGER_ON_SUNSET` | Exterior lights on |

All trigger parameters and step targets are in `config.py` — nothing hardcoded in service modules.

### Testing

Framework: `pytest` with `pytest-asyncio` for async monitor tests. All tests use stub/mock data — no live HA connection required.

| Test file | What it covers |
|---|---|
| `test_knowledge.py` | Store read/write helpers: `apply_state_change`, `load_configuration`, `get_entity`, `entities_in_area`, `record_trigger`, `get_last_trigger`, `record_execution` |
| `test_monitor.py` | Auth handshake, initial state fetch, `state_changed` event processing, and reconnect behavior against a mock WebSocket |
| `test_analysis.py` | Each trigger handler in isolation, cooldown enforcement, and `evaluate_automations` dispatch across multiple automations |
| `test_planning.py` | `build_plan` with `TARGET_ENTITY` steps, `TARGET_AREA` expansion, and mixed steps |
| `test_execution.py` | `send_action` payload construction, `execute_plan` sequencing, and `record_execution` call after plan completes |

### Implementation Approach

- Language: Python
- Style: functional — avoid OOP unless absolutely necessary; use Protocols (interfaces) where applicable
- Data defined via TypedDicts with minimal encapsulation so new components can be added without major refactors
- Single top-level `config.py` for user automation definitions — no JSON or YAML configuration files

### Deployment

The prototype runs as a Docker container.

**Dockerfile** (`prototype/`):
- Base: `python:3.12-slim`
- Copies service source; `config.py` is not baked in — mounted at runtime

**docker-compose.yml** (`prototype/`):
```yaml
services:
  ha-automation:
    build: .
    env_file: ../.env
    volumes:
      - ./config.py:/app/config.py:ro
    restart: unless-stopped
    network_mode: host
```

User workflow: edit `config.py` → `docker compose restart`.

### Build Order

1. `knowledge.py` — all three stores and helpers, no dependencies
2. `monitor.py` — depends on knowledge
3. `execution.py` — defines `SERVICE_*` and `TARGET_*` constants; depends on knowledge (shared msg ID)
4. `analysis.py` — defines `TRIGGER_*` constants, dispatch table, cooldown table; depends on knowledge
5. `planning.py` — depends on knowledge + execution constants
6. `config_example.py` — committed skeleton
7. `main.py` — wires all MAPE-K components, configures logging
8. `tests/` — unit tests for all modules
9. `Dockerfile` + `docker-compose.yml`
10. `.gitignore`, `.env.example`
11. End-to-end test against live HA instance

### Task Breakdown

#### Phase 1: Foundation

- [x] **`knowledge.py`** — `ManagedSystemState` and `SystemConfiguration` TypedDicts; `apply_state_change`, `load_configuration`, `get_entity`, `entities_in_area`, `get_automations` helpers
- [x] **`knowledge.py` (AdaptationState)** — add `TriggerRecord`, `ExecutionRecord`, `AdaptationState` TypedDicts; `record_trigger`, `get_last_trigger`, `record_execution` helpers
- [x] **`monitor.py`** — WebSocket connect, auth handshake, `get_states` initial fetch, `state_changed` subscription, reconnect-on-drop with backoff; logs connect/auth/error events
- [x] **`execution.py`** — `SERVICE_*` and `TARGET_*` constants; `send_action` and `execute_plan` primitives; logs each action sent and any failures
- [x] **`execution.py` (AdaptationState)** — call `record_execution` after all steps in a plan are sent

#### Phase 2: Intelligence

- [x] **`analysis.py`** — `TRIGGER_*` constants; dispatch table; `evaluate_automations` iterates all automations and returns those whose triggers fired; logs trigger fires
- [x] **`analysis.py` (cooldown)** — add cooldown table per trigger type; consult `get_last_trigger` before firing; call `record_trigger` after firing; log skipped triggers
- [x] **`planning.py`** — `build_plan(automation)` resolves `TARGET_AREA` to individual entities, emits one `ActionStep` per entity, returns a `Plan`; logs plan generation and area expansion

#### Phase 3: Configuration & Wiring

- [x] **`config_example.py`** — committed skeleton demonstrating all `TRIGGER_*` and `SERVICE_*` constants with placeholder entity/area IDs and inline comments
- [x] **`main.py`** — reads env vars, calls `logging.basicConfig`, loads `config.py` via `load_configuration`, starts Monitor, runs asyncio event loop: Monitor → Analysis → Planning → Execution; logs startup and shutdown

#### Phase 4: Deployment

- [x] **`Dockerfile`** — `python:3.12-slim` base, copies service source (excludes `config.py`)
- [x] **`docker-compose.yml`** — `env_file: ../.env`, `config.py` bind-mounted read-only, `restart: unless-stopped`, `network_mode: host`
- [x] **`.gitignore`** — excludes `prototype/config.py`, `.env`
- [x] **`.env.example`** — documents `HA_URL` and `HA_TOKEN` with placeholder values

#### Phase 5: Unit Tests

- [x] **`test_knowledge.py`** — store helpers, AdaptationState read/write, area lookup
- [x] **`test_monitor.py`** — auth handshake, initial fetch, state_changed handling, reconnect logic (mock WebSocket)
- [x] **`test_analysis.py`** — each trigger handler, cooldown skip/fire, `evaluate_automations` across multiple automations
- [x] **`test_planning.py`** — `TARGET_ENTITY` passthrough, `TARGET_AREA` expansion, mixed steps
- [x] **`test_execution.py`** — `send_action` payload, `execute_plan` sequencing, `record_execution` called after plan

#### Phase 6: Validation

- [ ] End-to-end test against live HA instance: verify entity fetch, trigger evaluation, plan execution, cooldown enforcement, and reconnect behavior
