from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Any
from uuid import uuid4

from .engine import ProductionLineSimulation
from .scenario import make_mvp_scenario
from .profiles import CLASSIC_PROFILE, ShiftProfile, action_log, make_seeded_shift, profile_snapshot


ALLOWED_SPEEDS = frozenset({1, 2, 4})
EMERGENCY_REPAIR_CALLOUT_COST = 350.0


class SessionNotFoundError(LookupError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Simulation session '{session_id}' was not found")


class SessionPausedError(RuntimeError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Simulation session '{session_id}' is paused")


@dataclass
class SimulationSession:
    session_id: str
    simulation: ProductionLineSimulation
    paused: bool = False
    speed: int = 1
    intervention_cost: float = 0.0
    preventive_maintenance_cost: float = 0.0
    profile: ShiftProfile = CLASSIC_PROFILE

    def __post_init__(self) -> None:
        if type(self.speed) is not int or self.speed not in ALLOWED_SPEEDS:
            raise ValueError("Speed must be one of: 1, 2, 4")


class SessionManager:
    """Thread-safe in-memory owner of stateful simulation sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, SimulationSession] = {}
        self._lock = RLock()

    def create_session(
        self,
        *,
        seed: int = 42,
        failures_enabled: bool = True,
        speed: int = 1,
        scenario_mode: str = "classic",
    ) -> dict[str, Any]:
        self._validate_speed(speed)
        if scenario_mode not in {"classic", "seeded"}:
            raise ValueError("Scenario mode must be classic or seeded")
        scenario = (
            make_mvp_scenario()
            if failures_enabled
            else make_mvp_scenario(cnc_failure_probability=0)
        )
        profile = CLASSIC_PROFILE
        if scenario_mode == "seeded":
            scenario, profile = make_seeded_shift(scenario, seed)
            if not failures_enabled:
                scenario = replace(scenario, stages=tuple(
                    replace(stage, failure_probability=0) for stage in scenario.stages
                ))
        session = SimulationSession(
            session_id=str(uuid4()),
            simulation=ProductionLineSimulation(scenario, seed=seed),
            speed=speed,
            profile=profile,
        )
        with self._lock:
            self._sessions[session.session_id] = session
            return self._snapshot(session)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return self._snapshot(self._require_session(session_id))

    def pause_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id)
            session.paused = True
            return self._snapshot(session)

    def resume_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id)
            session.paused = False
            return self._snapshot(session)

    def set_speed(self, session_id: str, speed: int) -> dict[str, Any]:
        self._validate_speed(speed)
        with self._lock:
            session = self._require_session(session_id)
            session.speed = speed
            return self._snapshot(session)

    def advance_session(self, session_id: str, minutes: float) -> dict[str, Any]:
        if minutes <= 0:
            raise ValueError("Advance duration must be greater than zero")
        with self._lock:
            session = self._require_session(session_id)
            if session.paused:
                raise SessionPausedError(session_id)
            session.simulation.advance_by(minutes)
            return self._snapshot(session)

    def expedite_repair(self, session_id: str, machine_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id)
            session.simulation.expedite_repair(machine_id)
            session.intervention_cost += EMERGENCY_REPAIR_CALLOUT_COST
            return self._snapshot(session)

    def start_preventive_maintenance(
        self,
        session_id: str,
        machine_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id)
            maintenance_cost = session.simulation.preventive_maintenance_cost(
                machine_id
            )
            session.simulation.start_preventive_maintenance(machine_id)
            session.preventive_maintenance_cost += maintenance_cost
            return self._snapshot(session)

    def reprioritize_order(
        self,
        session_id: str,
        order_id: str,
        priority: int,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id)
            session.simulation.reprioritize_order(order_id, priority)
            return self._snapshot(session)

    def place_purchase_order(
        self,
        session_id: str,
        supplier_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._require_session(session_id)
            session.simulation.place_purchase_order(supplier_id, quantity)
            return self._snapshot(session)

    def _require_session(self, session_id: str) -> SimulationSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFoundError(session_id) from None

    @staticmethod
    def _validate_speed(speed: int) -> None:
        if type(speed) is not int or speed not in ALLOWED_SPEEDS:
            raise ValueError("Speed must be one of: 1, 2, 4")

    @staticmethod
    def _snapshot(session: SimulationSession) -> dict[str, Any]:
        summary = session.simulation.summary()
        return {
            "session_id": session.session_id,
            "paused": session.paused,
            "speed": session.speed,
            "intervention_cost": session.intervention_cost,
            "preventive_maintenance_cost": session.preventive_maintenance_cost,
            "summary": summary,
            "scenario_profile": profile_snapshot(session.simulation, session.profile, summary),
            "action_log": action_log(session.simulation),
            "event_digest": session.simulation.digest(),
        }
