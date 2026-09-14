<div align="center">

# PlantOps Simulation Core

**A deterministic, discrete-event production line simulator with a lightweight FastAPI interface.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-6C63FF?style=flat-square)

</div>

PlantOps models the authoritative operational state of a small manufacturing line. It is intentionally headless and focused: the simulation engine handles production flow, machine state, failures, repairs, scrap, and performance metrics, while the API exposes repeatable simulation runs to other applications.

## Production line

```text
Raw material
     │
     ▼
   CNC ──► Buffer (18) ──► Wash ──► Buffer (14)
                                          │
                                          ▼
Finished ◄── Quality ◄── Buffer (12) ◄── Assembly
                 │
                 └──► Scrap
```

The MVP scenario includes:

- A four-stage **CNC → Wash → Assembly → Quality** line
- Finite work-in-progress buffers
- Machine blocking and starvation
- Seeded, deterministic random streams
- CNC failures and variable repair times
- Quality-stage scrap
- OEE, availability, performance, WIP, downtime, and production metrics
- A SHA-256 event digest for reproducibility checks
- Independent in-memory simulation sessions with pause, resume, and speed controls
- Customer orders, seeded urgent demand, delivery status, and OTIF performance
- FIFO finished-goods inventory with warehouse and backlog accounting

## WSL quick start

PlantOps requires Python 3.11 or newer. Open a WSL terminal, navigate to the repository, and run these commands from the `plantops-core` directory:

```bash
cd plantops-core
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

The shell prompt should now begin with `(.venv)`. Run `deactivate` when you want to leave the virtual environment.

### Run from the command line

```bash
python -m plantops_sim.cli --seed 42 --minutes 480
```

Disable CNC failures for a baseline run:

```bash
python -m plantops_sim.cli --seed 42 --minutes 480 --no-failures
```

The CLI prints the complete simulation summary followed by its deterministic event digest.

### Run the API

```bash
python -m uvicorn plantops_sim.api:app --reload
```

Keep that terminal running, then open Swagger UI in your browser:

<http://127.0.0.1:8000/docs>

Additional endpoints:

- ReDoc documentation: <http://127.0.0.1:8000/redoc>
- Health check: <http://127.0.0.1:8000/health>

## API reference

### `GET /health`

Returns the service status.

```json
{
  "status": "ok",
  "service": "plantops-simulation"
}
```

### `POST /simulate`

Runs the MVP production scenario and returns its summary and event digest.

| Field | Type | Default | Constraints | Description |
| --- | --- | ---: | --- | --- |
| `seed` | integer | `42` | Minimum `0` | Seed for deterministic random streams |
| `minutes` | number | `480` | Greater than `0`, maximum `10080` | Simulation duration in minutes |
| `failures_enabled` | boolean | `true` | — | Enables or disables CNC failures |

Example request:

```bash
curl -X POST http://127.0.0.1:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "seed": 42,
    "minutes": 480,
    "failures_enabled": true
  }'
```

Example response (abridged):

```json
{
  "summary": {
    "seed": 42,
    "simulated_minutes": 480,
    "good_production": 255,
    "scrap": 7,
    "quality": 0.9733,
    "oee": 0.9089,
    "wip": 0,
    "raw_material_remaining": 238,
    "finished_goods_available": 0,
    "finished_goods_allocated": 255,
    "finished_goods_total": 255,
    "machine_metrics": {
      "cnc_01": {
        "state": "DOWN",
        "processed": 262,
        "failures": 10,
        "availability": 0.7368
      }
    },
    "event_counts": {
      "MACHINE_FAILED": 10,
      "ORDER_DUE": 4,
      "ORDER_LATE": 3,
      "PROCESS_COMPLETED": 1041,
      "UNIT_SCRAPPED": 7
    },
    "order_summary": {
      "orders_total": 4,
      "orders_released": 4,
      "orders_due": 4,
      "orders_completed": 3,
      "orders_late": 3,
      "units_ordered": 308,
      "units_delivered": 255,
      "units_on_time": 196,
      "units_late": 59,
      "backlog_units": 53,
      "backlog_orders": 1,
      "otif": 0.25,
      "orders": []
    }
  },
  "event_digest": "a0b13826abaddf740ff0f86b5b517b4c58343d2166046230de820e760234615a"
}
```

The API returns metrics for every machine and event type; they are shortened above for readability. The digest is deterministic for the same scenario, seed, duration, and engine version.

## Customer orders and OTIF

The MVP line produces one product family, so customer orders are fulfilled automatically from finished-goods inventory. Every non-scrapped unit leaving Quality first enters the warehouse. The allocator then assigns available units to active, incomplete orders; stock remains available when no order is ready and can fulfill a later normal or urgent order immediately upon release.

Allocation never removes a unit from finished-production accounting: `good_production` remains the total number of good units made. Warehouse units are consumed in deterministic FIFO order, and each unit can be assigned to at most one order.

Orders carry a quantity, release minute, due minute, and priority. The allocator uses this stable sequence:

1. Earliest due minute
2. Higher priority when due minutes match
3. Order ID as the final deterministic tiebreaker

Three normal orders are available at minute zero. One urgent order arrives later in the shift; its arrival minute and quantity come from a dedicated `orders:urgent` random stream derived from the simulation seed. Its deadline is 70 minutes after arrival. The same seed therefore reproduces the same urgent order without changing the random streams used for machine cycles, failures, repairs, or scrap.

The engine records `FINISHED_GOODS_RECEIVED` when Quality sends a unit to the warehouse and `ORDER_UNIT_ALLOCATED` when stock is assigned to an order. It also records `ORDER_RELEASED`, `URGENT_ORDER_RECEIVED`, and `ORDER_DUE`. An incomplete order records `ORDER_LATE` exactly once when its deadline is reached.

Delivery timing uses the **allocation time**, not the manufacturing time. A unit made at minute 20 but assigned at minute 70 is on time only when minute 70 is at or before the order's deadline.

### Warehouse and backlog accounting

- `finished_goods_available`: warehouse units not yet assigned to an order
- `finished_goods_allocated`: warehouse units already assigned to orders
- `finished_goods_total`: every good unit represented by finished-goods accounting
- `backlog_units`: unfulfilled units across released, incomplete orders
- `backlog_orders`: released orders that still have an unfulfilled quantity

The engine continuously enforces:

```text
finished_goods_total = finished_goods_available + finished_goods_allocated
finished_goods_total = good_production
```

Supplier replenishment and raw-material purchasing are intentionally deferred to a later phase. This phase models only finished-goods storage and customer-order allocation.

### OTIF definition

OTIF measures orders delivered **on time and in full**:

```text
OTIF = orders fully completed by their deadline / orders whose due time has passed
```

Orders that are not due yet are excluded from both sides. When no order has become due, `otif` is `null` instead of an artificial zero or perfect score.

Each item in `order_summary.orders` includes:

- `id`, `quantity`, and `priority`
- `release_minute` and `due_minute`
- `fulfilled_quantity` and `remaining_quantity`
- Current status: `PENDING`, `ACTIVE`, `LATE`, `COMPLETED_ON_TIME`, or `COMPLETED_LATE`

## Stateful simulation sessions

Sessions let a client create a factory once and advance the same simulation over multiple requests. Machine state, buffers, queued events, random streams, the event log, and the simulation clock remain intact between advances.

Sessions and player actions are an in-memory MVP. They are lost when the API process restarts, and no external persistence or background processing is performed.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/sessions` | Create a session |
| `GET` | `/sessions/{session_id}` | Read its current state |
| `POST` | `/sessions/{session_id}/advance` | Advance simulated time |
| `POST` | `/sessions/{session_id}/pause` | Pause the session |
| `POST` | `/sessions/{session_id}/resume` | Resume the session |
| `PUT` | `/sessions/{session_id}/speed` | Set playback speed to `1`, `2`, or `4` |
| `POST` | `/sessions/{session_id}/actions/expedite-repair` | Immediately repair a DOWN machine |
| `POST` | `/sessions/{session_id}/actions/prioritize-order` | Change an active order's priority |

### Create a session

```bash
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "seed": 42,
    "failures_enabled": true,
    "speed": 1
  }'
```

The response contains a UUID, session controls, the initial simulation summary, and an event digest:

```json
{
  "session_id": "f53c318f-2d00-47c6-b20a-80695b31009e",
  "paused": false,
  "speed": 1,
  "intervention_cost": 0.0,
  "summary": {
    "seed": 42,
    "simulated_minutes": 0,
    "finished_goods_available": 0,
    "finished_goods_allocated": 0,
    "finished_goods_total": 0,
    "order_summary": {
      "orders_total": 4,
      "orders_released": 3,
      "orders_due": 0,
      "backlog_units": 260,
      "backlog_orders": 3,
      "otif": null
    }
  },
  "event_digest": "<sha256>"
}
```

The summary is abridged above; API responses include the complete simulation metrics.

### Inspect and advance

Replace `{session_id}` with the UUID returned when the session was created.

```bash
curl http://127.0.0.1:8000/sessions/{session_id}

curl -X POST http://127.0.0.1:8000/sessions/{session_id}/advance \
  -H "Content-Type: application/json" \
  -d '{"minutes": 15}'
```

The `minutes` value is an explicit amount of simulated time. The stored speed is playback metadata for clients and future schedulers; it does not multiply this value.

### Pause, resume, and change speed

```bash
curl -X POST http://127.0.0.1:8000/sessions/{session_id}/pause
curl -X POST http://127.0.0.1:8000/sessions/{session_id}/resume

curl -X PUT http://127.0.0.1:8000/sessions/{session_id}/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 4}'
```

Advancing a paused session returns HTTP `409`. Unknown session IDs return `404`, while invalid request bodies and unsupported speeds return `422`.

### Expedite a repair

An emergency maintenance call-out immediately repairs a machine that is currently `DOWN` after an unplanned failure. The ordinary scheduled repair is cancelled, downtime stops accumulating at the current simulation time, and the session's cumulative intervention cost increases by **350.00**.

Use the machine's display identifier, such as `CNC-01`:

```bash
curl -X POST \
  http://127.0.0.1:8000/sessions/{session_id}/actions/expedite-repair \
  -H "Content-Type: application/json" \
  -d '{"machine_id": "CNC-01"}'
```

The action is allowed while a session is paused; pausing blocks only time advancement. An unknown session or machine returns HTTP `404`, a known machine that is not `DOWN` returns `409`, and an invalid request body returns `422`. Failed actions do not change the simulation or add cost.

### Prioritize a customer order

A player can change the priority of a released, incomplete order to an integer from `0` through `100`; a higher number means a higher priority. Pending orders and completed orders cannot be reprioritized. The action is allowed while the session is paused and does not add intervention cost.

```bash
curl -X POST \
  http://127.0.0.1:8000/sessions/{session_id}/actions/prioritize-order \
  -H "Content-Type: application/json" \
  -d '{"order_id": "ORDER-002", "priority": 100}'
```

Priority affects future warehouse allocations only. Finished goods already allocated to an order are never reassigned. Each new allocation continues to rank eligible orders by:

1. Earliest due minute
2. Higher current priority when due minutes match
3. Order ID as the final deterministic tie-breaker

Raising one order's priority can therefore delay another order with the same due minute. Unknown sessions or orders return HTTP `404`, ineligible orders return `409`, and invalid request bodies or priorities outside `0`–`100` return `422`. Repeating the current priority is a successful no-op and creates no additional audit event.

## Deterministic by design

Each source of randomness uses a stable, named pseudo-random stream derived from the selected seed. Running the same scenario with the same seed and duration produces the same summary and event digest. This makes PlantOps useful for regression tests, scenario comparisons, and reproducible experiments.

```python
from plantops_sim import ProductionLineSimulation, make_mvp_scenario

scenario = make_mvp_scenario(cnc_failure_probability=0)
simulation = ProductionLineSimulation(scenario, seed=42)

summary = simulation.run(until_minutes=480)
event_digest = simulation.digest()
```

## Testing

Run the complete test suite from the `plantops-core` directory:

```bash
python -m unittest discover -s tests -v
```

The tests cover deterministic replay, seeded urgent orders, FIFO warehouse allocation, backlog and inventory invariants, allocation priority and timing, deadlines, OTIF, incremental advancement, event cancellation, expedited repairs, intervention costs, production output, machine behavior, API health, input validation, and the complete session lifecycle.

## Project structure

```text
plantops-core/
├── src/plantops_sim/
│   ├── api.py          # FastAPI application and request validation
│   ├── cli.py          # Command-line entry point
│   ├── engine.py       # Discrete-event simulation engine
│   ├── model.py        # Scenario, machine, buffer, and event models
│   ├── scenario.py     # MVP production-line configuration
│   └── sessions.py     # In-memory stateful session manager
├── tests/
│   ├── test_api.py
│   ├── test_orders.py
│   └── test_simulation.py
└── pyproject.toml
```

---

<div align="center">

Built as the simulation foundation for the PlantOps factory experience.

</div>
