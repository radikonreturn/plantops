<div align="center">

# PlantOps Simulation Core

**A deterministic, discrete-event production line simulator with a lightweight FastAPI interface.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-6C63FF?style=flat-square)

</div>

PlantOps models the authoritative operational state of a small manufacturing line. The core is authoritative: the simulation engine handles production flow, machine state, failures, repairs, scrap, and performance metrics, while the API exposes repeatable simulation runs to other applications.

The repository now includes the first playable operator console in `plantops-web/`. It is a deliberately dense MES/SCADA-style browser surface: the factory floor is the main view, while orders, purchasing, repairs, and preventive maintenance remain backed by the authoritative in-memory session API.

## Playable web console

Start both the FastAPI backend and Vite operator console together from WSL:

```bash
cd plantops-web
npm install
npm run dev:full
```

First create the backend `.venv` and install `.[test]` using the WSL setup below. Node.js 20 or newer is recommended. The combined command prefixes output as `API` and `WEB`, and stops the other process when either process exits. It sets `VITE_API_BASE_URL=http://127.0.0.1:8010` explicitly, reserving the developer's Coolify port for Coolify. Vite binds port 5173 strictly so an occupied port produces a clear startup failure. The existing `npm run dev` command remains Vite-only. To run the backend separately:

```bash
cd plantops-core && source .venv/bin/activate && uvicorn plantops_sim.api:app --reload --host 127.0.0.1 --port 8010
```

Then open the browser console at <http://127.0.0.1:5173>. The API's interactive Swagger documentation remains at <http://127.0.0.1:8010/docs>.

The API allows browser requests from `http://localhost:5173` and `http://127.0.0.1:5173` for local development.

The frontend defaults to `http://127.0.0.1:8010`; copy `plantops-web/.env.example` to `plantops-web/.env` to override `VITE_API_BASE_URL` for frontend-only development. On first load it creates a seeded shift with seed 42 and pauses it so the engineer explicitly starts the shift. Playback advances one simulated minute per second at 1×, two at 2×, and four at 4×, then pauses at the 480-minute shift boundary (540 when overtime was authorized). Requests are serialized; uncertain action responses stop playback and reconcile the server snapshot without automatically repeating chargeable decisions.

Vite polls source changes because mounted Windows workspaces can miss native file events and otherwise serve stale modules. The strict frontend port remains 5173; API port 8000 is reserved for Coolify.

### Seeded engineering shifts

The browser opts into `POST /sessions` with `"scenario_mode": "seeded"`. Omitting the field keeps the classic MVP scenario, preserving existing clients, CLI runs, `/simulate`, and reference event digests. Every session snapshot additionally contains `scenario_profile` and `action_log`.

Profile version 2 uses isolated `scenario-profile:v2` and `scenario-conditions:v2` random streams. Eight handovers configure actual station health, cycle capacity, carried-in WIP, raw stock, order pressure, supplier terms, or final-inspection rejection risk: CNC wear, laser material jam, wash filter restriction, assembly fixture constraint, test calibration pressure, quality containment, material shortage, and competing rush orders. No purchase orders are placed automatically. All orders remain one product family; no fictitious changeovers or multi-product BOM are implied.

For example, replay seed **42** opens CNC wear risk (18 cut blanks before CNC); **0** opens Laser material jam (heavy raw stock); **1** opens Wash filter restriction (18 machined units before wash). Seeds **11**, **7**, **9**, **2**, and **8** demonstrate assembly, test, quality, material, and dispatch concerns respectively. Seeded v2 intentionally changes v1 seed mappings; classic reference digests remain unchanged. New Shift advances to the next seed by default. Expand **Advanced / deterministic replay** in the New Shift dialog to enter any specific seed. A successful New Shift automatically opens **Office / Inbox** and updates the URL hash. Repeat the same decisions at the same simulated times to reproduce the shift.

The seeded automotive bracket route is **receiving → laser/cutting → CNC → wash → assembly → functional test/CMM → final quality → finished goods/dispatch**. Classic retains its four stages. Five finite inter-stage buffers carry uniquely identified units. Building geometry is stable across seeds; pallet counts, congestion, machine highlights, conveyor state and dispatch/receiving pressure change with authoritative state.

| Asset | Preventive action | Duration | Cost |
| --- | --- | --- | --- |
| Laser / Cutting | Lens and nozzle service | 12 min | 140 |
| CNC Machining | Spindle and tool service | 20 min | 250 |
| Wash Cell | Filter and bath service | 15 min | 120 |
| Assembly Cell | Fixture service | 10 min | 100 |
| Test / CMM | Calibration service | 18 min | 180 |
| Final Quality | None; automatic lot inspection | — | — |

PM uses the existing engine: only idle, starved or blocked equipment may start; completion restores health and reduces wear-related failure risk. It does not change cycle capacity or lot rejection risk. Equipment faults are modeled as per-unit interruption risks with machine-specific repair durations, not detailed mechanical physics. The failures-disabled option zeroes failure probability for every seeded machine. The quality containment profile sets actual final-inspection rejection probability to 14%; observed scrap remains a separate outcome.

`scenario_profile` contains a versioned ID, title, manager briefing, initial conditions, primary problem zone, machine role/fault mode/status, effective failure risk, PM availability/duration/cost, input/output buffer IDs, supplier terms, live alerts, capacity context, and `scene`. Scene zones contain actual unit counts, capacity, pallet counts and congestion; routes become active only while the associated machine runs, and expose waiting quantity and output-buffer blocking. Capacity identifies the configured bottleneck assets. Receiving exposes inbound units and uncovered demand; dispatch exposes allocation and at-risk order counts. Finished-goods scene stock means **unallocated** goods, while legacy `buffer_levels.finished` remains total good production. Carry-in WIP uses unique IDs ahead of future supplier receipts and is not counted as production until it passes Quality during this shift.

The order board's “At risk” flag and forecast minute are optimistic due-date/queue/cycle-time estimates, not delivery promises. It excludes breakdown, scrap and receipt delays. Material-coverage alerts compare remaining demand against stock, in-process units and committed inbound material before scrap allowance. Current alerts and visual state are read-only projections: inspecting them never changes events, random streams or digests.

### Engineering workspaces

The permanent left rail opens eight useful views in the same session:

| Workspace | Live content and decisions |
| --- | --- |
| Plant View | Top-down floor plan, real pallets/WIP/routes, contextual asset dialog and order board |
| Office / Inbox | Manager handover and tasks derived from current alerts |
| Production Plan | Demand versus output, ideal capacity, queues and order priority decisions |
| Orders | Fulfillment, deadlines, risk, OTIF and priority input (0–100) |
| Maintenance | Health, failure risk, downtime, emergency repairs and preventive plans |
| Quality | Actual inspection, scrap, latent customer escapes and bounded containment activation |
| Inventory | Storage, inbound material, supplier terms and purchase-order entry |
| Reports | Interim/shift-end metrics, separate cost ledgers, open risks and actual engine action log |

Priorities affect future allocations only and only break ties between identical due times. Procurement, priority changes and maintenance remain usable while paused. Quality containment is available only on quality-containment profiles; manual inventory reconciliation remains deferred. There is no persistence beyond the in-memory API process, authentication, multiplayer or background simulation worker.

Build the browser application with:

```bash
cd plantops-web
npm run build
```

## PlantOps V3 — Living Shift Operations

The eight profile definitions and fixed building geometry are retained. Seeded sessions now own a `LivingShift` in `plantops-core/src/plantops_sim/living.py`. Classic `/simulate`, CLI, and sessions omitting `scenario_mode` keep their original simulation summary and reference event digest. The browser continues to request `scenario_mode: "seeded"`.

### Live events and lifecycle

Exactly three events are scheduled at shift creation using the isolated **`shift-events:v1`** RNG stream: minutes 45–85, 160–200 and 275–315. The primary profile selects the first event family; the other two are sampled without replacement. The schedule is inspectable at handover. Events have stable IDs, minute, effect-window end, kind, title, detail, severity, zone, workspace owner, affected IDs, lifecycle state and actual closing minute.

| Event | Real engine consequence | Lifecycle |
| --- | --- | --- |
| Equipment condition warning | Removes 18 health points from the target equipment, increasing wear-based failure exposure | Active until actual service restores health, or expired at shift close |
| Operator shortage | New cycles on the target station take 40% longer for 60 minutes; in-flight cycles retain their duration | Expires when the staffing window ends |
| Transport disruption | Each open PO, and each PO placed during the 60-minute window, gains 25 transit minutes once | Resolves after the window and all affected receipts arrive; expires without affected POs or at close |
| Customer escalation | An unfinished released order gains 15 priority points, capped at 100; earliest-due allocation still applies | Resolves when that order completes, otherwise expires at close; expires immediately if no order is eligible |
| Quality notice | Only in quality-containment profiles: latent defect risk for units passing normal inspection rises from 6% to 12% for 60 minutes | Expires with the exposure window |

Scheduled events activate only when simulated time reaches them. Starts, receipt delays, escalations, resolutions and expirations enter the event audit log. `closed_minute` records lifecycle closure; `end_minute` is the temporary effect window, not a promise that a persistent condition has cleared. Expiration does not undo lost health, changed priority or committed transit delays. No event is created during rendering or snapshot reads. The rail timeline combines scheduled/active events, actual order due times, expected receipts and recorded decisions.

### Bounded decisions

All three new commands require a seeded, still-open shift and work while paused. They return the full updated session snapshot. Unknown sessions/POs return **404**; unavailable, duplicate or closed-shift actions return **409**; missing, malformed or extra request fields return **422**. Failed actions consume no RNG, create no audit record and charge no cost.

| POST `/sessions/{id}/actions/…` | JSON body | Modeled trade-off |
| --- | --- | --- |
| `expedite-purchase-order` | `{"purchase_order_id":"PO-000001"}` | Once per open PO: halves remaining scheduled transit time for **120** cost. Cancels the old receipt event. Original promise remains unchanged; later transport disruption can still delay receipt. Received POs cannot be expedited. |
| `authorize-overtime` | `{}` | Once before shift close: extends 480 to **540 minutes**, committing **600** labor cost. At completion times in **[480, 540)**, effective per-unit failure probability is multiplied by **1.2**, capped at 1. Zero base failure risk stays zero. Normal-shift probabilities and customer due times do not change. |
| `activate-containment` | `{}` | Once, on a quality-containment profile only: each subsequently started final-inspection cycle adds **0.6 minutes** and **2** cost and isolates modeled latent defects as scrap. Source rejection probability remains 14%. Already-started inspections and already-released output are not retroactively contained. |

Containment adds an explicit latent-defect model on the independent **`quality:latent:v1`** stream. Among units passing ordinary final inspection, 6% (12% during a notice) carry a latent defect. Intensified inspection detects all such modeled latent defects; this is an explicit simplified detection assumption, not a cure for source defects. Without containment they enter finished goods. `customer_escapes` counts suspect unit IDs actually allocated to orders; `suspect_finished_units` counts those still unallocated. Captured latent defects are included in scrap. Extra inspection workload and cost are committed when an inspection starts, including an unfinished inspection at shift close.

For compatibility, `good_production` and `quality` retain their **inspection-release** meanings and may include latent defects. Delivery OTIF measures quantity and deadline only and is not retroactively reduced by escapes; reports show escapes separately and flag them as quality exposure. The model does not include recalls, rework, warranty costs, defect root causes or financial revenue. Equipment rejection bars report observed attribution only.

Seeded advancement is capped at the authorized shift end. Production does not start a new cycle at close, and subsequent interventions are rejected. Existing classic advancement semantics remain unchanged. All currency figures use the existing simulation cost units, with no implied currency or economic optimization score.

### Snapshot and reporting contract

- Seeded snapshots and `summary` expose `shift_events`, `overtime`, and `quality_containment`. Classic summaries omit those extensions.
- Seeded `supply_summary.purchase_orders` additionally exposes `expedited`, `expedite_cost`, `expected_receipt_minute` and `supplier_late`. Expected arrival is the currently scheduled deterministic receipt; actual arrival stays null until receipt. Procurement cost excludes expediting.
- Session `cost_breakdown` exposes `emergency_repair`, `preventive_maintenance`, `procurement`, `expediting`, `overtime`, `inspection` and their `total`, without double counting.
- `timeline` projects event notices, commitments and decisions. `maintenance_history` projects actual failures, repairs and PM starts/completions. Both are read-only audit views.
- `scenario_profile.decision_cards` has at most three concerns, measurable trade-offs, workspace, status and `decision_logged`. Automated customer escalation does not count as a player decision.
- `scenario_profile.scene.order_forecasts` reports an optimistic remaining-load estimate in actual allocation order; the due-window diagram uses real releases, deadlines and the shift clock. It does not reserve machine capacity or predict stochastic failure, scrap, pipeline or supply delays.
- `scenario_profile.shift_review` is provisional until the authorized close, then reports observed delivery, inspection yield, escapes, downtime, costs and event history alongside the actual player log. It does not infer counterfactual causality.

The map, handover text, forecasts, queue/pallet symbols and management prose **display** engine data; they cannot change it. Overtime exposure, cycle slowdowns, health losses, receipt changes, inspection workload, defects, order priorities, inventory and costs are **simulated**. Layout, station silhouettes and walls remain fixed across seeds. There is no Settings workspace or external narrative engine.

### Replay and verification

Same seed plus the same ordered commands at the same simulated times reproduces the event sequence, summary, digest, decision board, timeline and review (session UUID is intentionally excluded). Snapshot reads do not create RNG streams or consume them. The historical classic digest regression remains pinned. Profile v2 initial-condition mappings remain stable; V3 seeded outcomes intentionally add the live-event and latent-quality model.

From the repository root:

```bash
cd plantops-core
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
cd ../plantops-web
npm install
npm run build
npm run dev:full
```

Use **http://127.0.0.1:5173**, with API health at **http://127.0.0.1:8010/health** and docs at **http://127.0.0.1:8010/docs**. **Port 8000 is reserved for another local service.** If 5173 is occupied, the combined startup fails clearly; use or stop the existing PlantOps server before starting another. Do not change the port silently.

V3 verification covers deterministic event variation and replay, snapshot/RNG immutability, classic compatibility, overtime boundaries and extra production, PO receipt cancellation and one-time charging, containment capture/escapes/workload, atomic invalid operations, API validation, decision/report reconciliation, TypeScript compilation and the absence of frontend `Math.random`. Session persistence, detailed labor rosters, root-cause defect categories and causal decision attribution remain outside this milestone.

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
- Player-initiated steel-blank purchasing with deterministic supplier receipts
- Machine health, wear-driven failure risk, and preventive maintenance

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
python -m uvicorn plantops_sim.api:app --reload --host 127.0.0.1 --port 8010
```

Keep that terminal running, then open Swagger UI in your browser:

<http://127.0.0.1:8010/docs>

Additional endpoints:

- ReDoc documentation: <http://127.0.0.1:8010/redoc>
- Health check: <http://127.0.0.1:8010/health>

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
curl -X POST http://127.0.0.1:8010/simulate \
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
    "good_production": 193,
    "scrap": 7,
    "quality": 0.965,
    "oee": 0.8649,
    "wip": 0,
    "raw_material_remaining": 0,
    "finished_goods_available": 0,
    "finished_goods_allocated": 193,
    "finished_goods_total": 193,
    "machine_metrics": {
      "cnc_01": {
        "state": "STARVED",
        "processed": 200,
        "failures": 16,
        "health": 40.0,
        "maintenance_count": 0,
        "planned_maintenance_minutes": 0.0,
        "unplanned_downtime_minutes": 198.519,
        "availability": 0.5864
      }
    },
    "event_counts": {
      "MACHINE_FAILED": 16,
      "ORDER_DUE": 4,
      "ORDER_LATE": 3,
      "PROCESS_COMPLETED": 793,
      "UNIT_SCRAPPED": 7
    },
    "order_summary": {
      "orders_total": 4,
      "orders_released": 4,
      "orders_due": 4,
      "orders_completed": 2,
      "orders_late": 3,
      "units_ordered": 308,
      "units_delivered": 193,
      "units_on_time": 110,
      "units_late": 83,
      "backlog_units": 115,
      "backlog_orders": 2,
      "otif": 0.25,
      "orders": []
    },
    "supply_summary": {
      "raw_material_on_hand": 0,
      "purchase_orders_total": 0,
      "purchase_orders_open": 0,
      "purchase_orders_received": 0,
      "purchase_orders_late": 0,
      "inbound_units": 0,
      "received_units": 0,
      "procurement_committed_cost": 0,
      "purchase_orders": []
    }
  },
  "event_digest": "cde9c5acdf5c013482eaa43f8a0ca8e41452246dcbeb675971c0bd88f944030a"
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

## Supplier purchasing and raw-material replenishment

The classic MVP begins with **200 raw steel blanks**. This is intentionally below the 260 units of normal demand plus the seeded urgent order, so the line will eventually starve unless the player purchases more material. PlantOps never creates purchase orders automatically.

The scenario has one supplier:

| Supplier | Lead time | Late-delivery risk | Maximum extra delay | Unit cost |
| --- | ---: | ---: | ---: | ---: |
| `STEEL-01` — Anatolia Steel Blanks | 60–90 minutes | 20% | 45 minutes | 18.50 |

Normal lead time, the late-delivery decision, and extra delay use dedicated supplier RNG streams derived from the simulation seed. They do not consume randomness from machine cycles, failures, repairs, Quality scrap, or urgent demand. The same seed and purchasing action sequence therefore reproduces the same receipts.

Placing a purchase order commits its full cost but does not immediately increase raw stock. An open order exposes its promised receipt minute while `actual_receipt_minute` remains `null`. If delivery is delayed, the actual minute and `RECEIVED_LATE` status become visible only when material arrives; the engine records `PURCHASE_ORDER_LATE` once at that time. Every receipt records `MATERIAL_RECEIVED`, creates brand-new raw-unit IDs, and lets a starved CNC restart.

`supply_summary` contains:

- `raw_material_on_hand`, which always equals legacy `raw_material_remaining`
- Total, open, received, and late purchase-order counts
- `inbound_units` for open orders and `received_units` for completed receipts
- `procurement_committed_cost`, separate from emergency-repair `intervention_cost`
- An API-safe `purchase_orders` list with quantity, supplier, placed minute, promised and actual receipt minutes, costs, and status

Supplier material quality and multi-material bills of materials are later phases. This MVP replenishes only the single raw unit consumed by CNC.

## Machine health and preventive maintenance

Every machine starts at 100 health. Health falls deterministically after each processed unit and never drops below zero. CNC-01 currently loses 0.3 health per unit and has a wear multiplier of 2.0; the other stages use harmless zero-wear defaults.

Wear raises the existing seeded failure probability without introducing another random draw:

```text
effective failure probability
  = base probability × (1 + wear multiplier × (100 - health) / 100)
```

The result is capped at 1.0. A zero base probability therefore remains zero at every health level, so `failures_enabled=false` still guarantees no failures.

CNC-01 is the only preventive-maintenance-enabled machine in the current MVP. Its maintenance takes 20 simulated minutes and costs 250.00. It may begin while the machine is `IDLE`, `STARVED`, or `BLOCKED`, including while its session is paused. During maintenance its state is `PLANNED_MAINTENANCE`, it cannot process units, and the engine records start and completion events. Completion restores health to 100, increments `maintenance_count`, and returns the machine to service. Wash, Assembly, and Quality reject the action because no preventive-maintenance duration is configured for them yet.

Machine metrics keep planned maintenance separate from failure downtime:

- `health`: current health from 0 through 100
- `maintenance_count`: completed preventive-maintenance actions
- `planned_maintenance_minutes`: elapsed planned-maintenance time
- `unplanned_downtime_minutes`: downtime caused by failures; legacy `down_minutes` remains the same value

OEE availability uses standard planned-production-time treatment:

```text
planned production time = elapsed time - planned maintenance time
availability = (planned production time - unplanned downtime) / planned production time
```

When planned production time is zero, availability is safely reported as `0.0`. Preventive maintenance trades predictable short-term production loss and a fixed cost for restored health and lower future breakdown risk; waiting preserves output now but exposes the line to increasingly frequent, unpredictable failures.

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
| `POST` | `/sessions/{session_id}/actions/place-purchase-order` | Order raw material from a supplier |
| `POST` | `/sessions/{session_id}/actions/start-preventive-maintenance` | Start planned maintenance on an eligible machine |

### Create a session

```bash
curl -X POST http://127.0.0.1:8010/sessions \
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
  "preventive_maintenance_cost": 0.0,
  "summary": {
    "seed": 42,
    "simulated_minutes": 0,
    "finished_goods_available": 0,
    "finished_goods_allocated": 0,
    "finished_goods_total": 0,
    "supply_summary": {
      "raw_material_on_hand": 200,
      "purchase_orders_total": 0,
      "inbound_units": 0,
      "received_units": 0,
      "procurement_committed_cost": 0,
      "purchase_orders": []
    },
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
curl http://127.0.0.1:8010/sessions/{session_id}

curl -X POST http://127.0.0.1:8010/sessions/{session_id}/advance \
  -H "Content-Type: application/json" \
  -d '{"minutes": 15}'
```

The `minutes` value is an explicit amount of simulated time. The stored speed is playback metadata for clients and future schedulers; it does not multiply this value.

### Pause, resume, and change speed

```bash
curl -X POST http://127.0.0.1:8010/sessions/{session_id}/pause
curl -X POST http://127.0.0.1:8010/sessions/{session_id}/resume

curl -X PUT http://127.0.0.1:8010/sessions/{session_id}/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 4}'
```

Advancing a paused session returns HTTP `409`. Unknown session IDs return `404`, while invalid request bodies and unsupported speeds return `422`.

### Expedite a repair

An emergency maintenance call-out immediately repairs a machine that is currently `DOWN` after an unplanned failure. The ordinary scheduled repair is cancelled, downtime stops accumulating at the current simulation time, and the session's cumulative intervention cost increases by **350.00**.

Use the machine's display identifier, such as `CNC-01`:

```bash
curl -X POST \
  http://127.0.0.1:8010/sessions/{session_id}/actions/expedite-repair \
  -H "Content-Type: application/json" \
  -d '{"machine_id": "CNC-01"}'
```

The action is allowed while a session is paused; pausing blocks only time advancement. An unknown session or machine returns HTTP `404`, a known machine that is not `DOWN` returns `409`, and an invalid request body returns `422`. Failed actions do not change the simulation or add cost.

### Prioritize a customer order

A player can change the priority of a released, incomplete order to an integer from `0` through `100`; a higher number means a higher priority. Pending orders and completed orders cannot be reprioritized. The action is allowed while the session is paused and does not add intervention cost.

```bash
curl -X POST \
  http://127.0.0.1:8010/sessions/{session_id}/actions/prioritize-order \
  -H "Content-Type: application/json" \
  -d '{"order_id": "ORDER-002", "priority": 100}'
```

Priority affects future warehouse allocations only. Finished goods already allocated to an order are never reassigned. Each new allocation continues to rank eligible orders by:

1. Earliest due minute
2. Higher current priority when due minutes match
3. Order ID as the final deterministic tie-breaker

Raising one order's priority can therefore delay another order with the same due minute. Unknown sessions or orders return HTTP `404`, ineligible orders return `409`, and invalid request bodies or priorities outside `0`–`100` return `422`. Repeating the current priority is a successful no-op and creates no additional audit event.

### Place a purchase order

Purchase between 1 and 1,000 raw units from the MVP supplier. This planning action is allowed while the session is paused and does not change emergency-repair `intervention_cost`.

```bash
curl -X POST \
  http://127.0.0.1:8010/sessions/{session_id}/actions/place-purchase-order \
  -H "Content-Type: application/json" \
  -d '{"supplier_id": "STEEL-01", "quantity": 100}'
```

The returned session snapshot immediately shows the order as `OPEN`, its promised receipt minute, 100 `inbound_units`, and 1,850.00 of committed procurement cost. Raw stock changes only when simulation time reaches the deterministic actual receipt. Unknown sessions or suppliers return HTTP `404`; invalid bodies or quantities return `422`.

### Start preventive maintenance

Start the configured maintenance plan for an eligible machine:

```bash
curl -X POST \
  http://127.0.0.1:8010/sessions/{session_id}/actions/start-preventive-maintenance \
  -H "Content-Type: application/json" \
  -d '{"machine_id": "CNC-01"}'
```

The action is allowed while the session is paused. CNC-01 immediately enters `PLANNED_MAINTENANCE`, and the session's separate `preventive_maintenance_cost` increases by 250.00 exactly once. `intervention_cost` remains reserved for emergency repair call-outs.

Unknown sessions or machines return HTTP `404`. A machine that is `RUNNING`, `DOWN`, or already in planned maintenance returns `409`; malformed bodies return `422`. Failed starts do not change machine state, the event digest, or either cost ledger.

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

The tests cover deterministic replay, machine health and wear, preventive maintenance, OEE downtime treatment, seeded urgent orders, FIFO warehouse allocation, backlog and inventory invariants, allocation priority and timing, supplier lead times, purchasing, material receipts, starvation recovery, deadlines, OTIF, incremental advancement, event cancellation, expedited repairs, intervention costs, production output, machine behavior, API health, input validation, and the complete session lifecycle.

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
│   ├── test_maintenance.py
│   ├── test_orders.py
│   ├── test_simulation.py
│   └── test_supply.py
└── pyproject.toml
```

---

<div align="center">

Built as the simulation foundation for the PlantOps factory experience.

</div>
