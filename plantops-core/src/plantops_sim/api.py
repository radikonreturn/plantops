from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .engine import (
    MAX_PURCHASE_QUANTITY,
    ShiftActionUnavailableError,
    UnknownPurchaseOrderError,
    InvalidPurchaseQuantityError,
    InvalidOrderPriorityError,
    MachineCannotStartPreventiveMaintenanceError,
    MachineNotDownError,
    OrderCannotBeReprioritizedError,
    PendingRepairEventError,
    PreventiveMaintenanceNotConfiguredError,
    ProductionLineSimulation,
    UnknownMachineError,
    UnknownOrderError,
    UnknownSupplierError,
)
from .scenario import make_mvp_scenario
from .sessions import SessionManager, SessionNotFoundError, SessionPausedError


app = FastAPI(title="PlantOps API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
session_manager = SessionManager()


class SimulationRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    minutes: float = Field(default=480, gt=0, le=10080)
    failures_enabled: bool = True


class CreateSessionRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    failures_enabled: bool = True
    speed: Literal[1, 2, 4] = 1
    scenario_mode: Literal["classic", "seeded"] = "classic"


class AdvanceSessionRequest(BaseModel):
    minutes: float = Field(gt=0)


class SessionSpeedRequest(BaseModel):
    speed: Literal[1, 2, 4]


class ExpediteRepairRequest(BaseModel):
    machine_id: str = Field(min_length=1)


class PrioritizeOrderRequest(BaseModel):
    order_id: str = Field(min_length=1)
    priority: int = Field(strict=True, ge=0, le=100)


class PlacePurchaseOrderRequest(BaseModel):
    supplier_id: str = Field(min_length=1)
    quantity: int = Field(strict=True, ge=1, le=MAX_PURCHASE_QUANTITY)


class StartPreventiveMaintenanceRequest(BaseModel):
    machine_id: str = Field(min_length=1)


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
        scenario_mode=request.scenario_mode,
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


@app.post("/sessions/{session_id}/actions/expedite-repair")
def expedite_repair(session_id: str, request: ExpediteRepairRequest) -> dict[str, Any]:
    try:
        return session_manager.expedite_repair(session_id, request.machine_id)
    except (SessionNotFoundError, UnknownMachineError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (MachineNotDownError, PendingRepairEventError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/actions/prioritize-order")
def prioritize_order(
    session_id: str,
    request: PrioritizeOrderRequest,
) -> dict[str, Any]:
    try:
        return session_manager.reprioritize_order(
            session_id,
            request.order_id,
            request.priority,
        )
    except (SessionNotFoundError, UnknownOrderError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrderCannotBeReprioritizedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidOrderPriorityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.post("/sessions/{session_id}/actions/place-purchase-order")
def place_purchase_order(
    session_id: str,
    request: PlacePurchaseOrderRequest,
) -> dict[str, Any]:
    try:
        return session_manager.place_purchase_order(
            session_id,
            request.supplier_id,
            request.quantity,
        )
    except (SessionNotFoundError, UnknownSupplierError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidPurchaseQuantityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.post("/sessions/{session_id}/actions/start-preventive-maintenance")
def start_preventive_maintenance(
    session_id: str,
    request: StartPreventiveMaintenanceRequest,
) -> dict[str, Any]:
    try:
        return session_manager.start_preventive_maintenance(
            session_id,
            request.machine_id,
        )
    except (SessionNotFoundError, UnknownMachineError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        MachineCannotStartPreventiveMaintenanceError,
        PreventiveMaintenanceNotConfiguredError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


class EmptyShiftActionRequest(BaseModel):
    model_config = {"extra": "forbid"}


class ExpeditePurchaseOrderRequest(EmptyShiftActionRequest):
    purchase_order_id: str = Field(strict=True, min_length=1)


@app.exception_handler(ShiftActionUnavailableError)
async def shift_conflict(_request: Any, exc: ShiftActionUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(UnknownPurchaseOrderError)
async def unknown_po(_request: Any, exc: UnknownPurchaseOrderError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def run_living_action(session_id: str, action: str, po_id: str = "") -> dict[str, Any]:
    try:
        return session_manager.living_action(session_id, action, po_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/actions/expedite-purchase-order")
def expedite_purchase_order(session_id: str, request: ExpeditePurchaseOrderRequest) -> dict[str, Any]:
    return run_living_action(session_id, "expedite", request.purchase_order_id)


@app.post("/sessions/{session_id}/actions/authorize-overtime")
def authorize_overtime(session_id: str, request: EmptyShiftActionRequest) -> dict[str, Any]:
    return run_living_action(session_id, "overtime")


@app.post("/sessions/{session_id}/actions/activate-containment")
def activate_containment(session_id: str, request: EmptyShiftActionRequest) -> dict[str, Any]:
    return run_living_action(session_id, "containment")


class EquipmentActionRequest(EmptyShiftActionRequest):
    machine_id: str = Field(strict=True, min_length=1)


@app.post("/sessions/{session_id}/actions/clean-lens")
def clean_lens(session_id: str, request: EquipmentActionRequest) -> dict[str, Any]:
    return run_equipment_action(session_id, request.machine_id, "clean-lens")


@app.post("/sessions/{session_id}/actions/service-wash")
def service_wash(session_id: str, request: EquipmentActionRequest) -> dict[str, Any]:
    return run_equipment_action(session_id, request.machine_id, "service-wash")


@app.post("/sessions/{session_id}/actions/assign-support")
def assign_support(session_id: str, request: EquipmentActionRequest) -> dict[str, Any]:
    return run_equipment_action(session_id, request.machine_id, "assign-support")


@app.post("/sessions/{session_id}/actions/recalibrate-tester")
def recalibrate_tester(session_id: str, request: EquipmentActionRequest) -> dict[str, Any]:
    return run_equipment_action(session_id, request.machine_id, "recalibrate-tester")


def run_equipment_action(session_id: str, machine_id: str, action: str) -> dict[str, Any]:
    try:
        return session_manager.equipment_action(session_id, machine_id, action)
    except (SessionNotFoundError, UnknownMachineError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
