from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from .engine import ProductionLineSimulation
from .scenario import make_mvp_scenario
from .sessions import SessionManager, SessionNotFoundError, SessionPausedError


app = FastAPI(title="PlantOps API", version="0.1.0")
session_manager = SessionManager()


class SimulationRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    minutes: float = Field(default=480, gt=0, le=10080)
    failures_enabled: bool = True


class CreateSessionRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    failures_enabled: bool = True
    speed: Literal[1, 2, 4] = 1


class AdvanceSessionRequest(BaseModel):
    minutes: float = Field(gt=0)


class SessionSpeedRequest(BaseModel):
    speed: Literal[1, 2, 4]


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


@app.post("/sessions")
def create_session(request: CreateSessionRequest) -> dict[str, Any]:
    return session_manager.create_session(
        seed=request.seed,
        failures_enabled=request.failures_enabled,
        speed=request.speed,
    )


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    try:
        return session_manager.get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/advance")
def advance_session(session_id: str, request: AdvanceSessionRequest) -> dict[str, Any]:
    try:
        return session_manager.advance_session(session_id, request.minutes)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SessionPausedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/pause")
def pause_session(session_id: str) -> dict[str, Any]:
    try:
        return session_manager.pause_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/resume")
def resume_session(session_id: str) -> dict[str, Any]:
    try:
        return session_manager.resume_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.put("/sessions/{session_id}/speed")
def set_session_speed(session_id: str, request: SessionSpeedRequest) -> dict[str, Any]:
    try:
        return session_manager.set_speed(session_id, request.speed)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
