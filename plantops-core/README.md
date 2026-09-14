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
    "oee": 0.9131,
    "wip": 0,
    "raw_material_remaining": 238,
    "machine_metrics": {
      "cnc_01": {
        "state": "DOWN",
        "processed": 262,
        "failures": 10,
        "availability": 0.754
      }
    },
    "event_counts": {
      "MACHINE_FAILED": 10,
      "PROCESS_COMPLETED": 1041,
      "UNIT_SCRAPPED": 7
    }
  },
  "event_digest": "84f1db849486e5aa798eca697277bbf1fb83d2aea29714fc44afbd31f9081f88"
}
```

The API returns metrics for every machine and event type; they are shortened above for readability.

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

The tests cover deterministic replay, seed variation, production output, failures and repairs, blocking, starvation, quality metrics, API health, the simulation response contract, and deterministic API requests.

## Project structure

```text
plantops-core/
├── src/plantops_sim/
│   ├── api.py          # FastAPI application and request validation
│   ├── cli.py          # Command-line entry point
│   ├── engine.py       # Discrete-event simulation engine
│   ├── model.py        # Scenario, machine, buffer, and event models
│   └── scenario.py     # MVP production-line configuration
├── tests/
│   ├── test_api.py
│   └── test_simulation.py
└── pyproject.toml
```

---

<div align="center">

Built as the simulation foundation for the PlantOps factory experience.

</div>
