from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .engine import ProductionLineSimulation
from .scenario import make_mvp_scenario


app = FastAPI(title="PlantOps API", version="0.1.0")


class SimulationRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    minutes: float = Field(default=480, gt=0, le=10080)
    failures_enabled: bool = True


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "plantops-simulation",
    }


@app.post("/simulate")
def simulate(request: SimulationRequest) -> dict[str, Any]:
    if request.failures_enabled:
        scenario = make_mvp_scenario()
    else:
        scenario = make_mvp_scenario(cnc_failure_probability=0)

    simulation = ProductionLineSimulation(scenario, seed=request.seed)
    summary = simulation.run(until_minutes=request.minutes)
    return {
        "summary": summary,
        "event_digest": simulation.digest(),
    }
