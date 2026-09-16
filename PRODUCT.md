# Product

<!-- impeccable:product-schema 1 -->

All product facts below are inferred from the explicit implementation brief for the first PlantOps browser UI.

## Platform

web

## Stack

React, TypeScript, and Vite with plain CSS and inline SVG. The simulation remains a separate FastAPI service.

## Users

Industrial engineers supervising a single manufacturing line during an active shift, alternating between live factory inspection and office decisions.

## Product Purpose

PlantOps makes the existing deterministic factory simulation playable. Users start and pace a shift, inspect the production line, monitor delivery and inventory performance, and make operational interventions against authoritative backend state.

## Positioning

The interface is a direct control surface for a deterministic discrete-event factory model: every displayed machine, order, stock level, cost, and action result comes from the simulation session rather than local UI approximation.

## Operating Context

The primary workflow is a desktop production-control screen used throughout a simulated shift. The factory floor is the central workspace, supported by machine operations, customer orders, procurement status, alerts, and shift controls.

## Capabilities and Constraints

- Create, pause, resume, speed up, and incrementally advance in-memory simulation sessions.
- Inspect machine state, health, throughput, availability, failures, and maintenance.
- Monitor orders, OTIF, backlog, raw stock, finished goods, and purchase orders.
- Call emergency repair, start preventive maintenance, place purchase orders, and reprioritize eligible customer orders.
- Use the FastAPI service as the sole authority; the browser must not invent operational state.
- No frontend framework beyond React, no database, WebSockets, background workers, authentication, chart library, or external visual assets.

## Brand Commitments

- Product environment: `Artemis Manufacturing — Plant 01`.
- PlantOps should feel like a realistic industrial MES/SCADA and production-control interface: serious, dense, functional, and readable.
- The palette is restrained to charcoal, warm gray, steel blue, muted green, amber, and operational red.
- Avoid gradients, glass effects, neon, decorative SaaS layouts, excessive rounded cards, and emoji iconography.

## Evidence on Hand

- The authoritative FastAPI and simulation implementation is in `plantops-core/`.
- Backend unit and API tests document existing contracts in `plantops-core/tests/`.
- No external brand assets or production photography were provided; the factory representation must use CSS and inline SVG geometry.

## Product Principles

- The factory map is the workspace, not decoration.
- Backend truth always outranks optimistic local state.
- Operational exceptions must be visible and actionable without obscuring normal flow.
- Dense information should remain scannable through disciplined hierarchy and status language.
- Deterministic replay controls must stay explicit.
