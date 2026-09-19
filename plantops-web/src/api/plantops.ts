import type {
  CreateSessionInput,
  EquipmentAction,
  PlaybackSpeed,
  SessionSnapshot,
} from "../types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (
  configuredBaseUrl || "http://127.0.0.1:8010"
).replace(/\/$/, "");

interface ErrorDetail {
  msg?: string;
}

interface ErrorPayload {
  detail?: string | ErrorDetail[];
}

export class PlantOpsApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string, readonly hasDetail = true) {
    super(message);
    this.name = "PlantOpsApiError";
    this.status = status;
  }
}

export class PlantOpsConnectionError extends Error {
  constructor(readonly path: string, readonly method: string) {
    super(`Cannot reach PlantOps at ${API_BASE_URL} for ${method} ${path}. Check that dev:full is running.`);
    this.name = "PlantOpsConnectionError";
  }
}

function errorMessage(payload: ErrorPayload | null, status: number): string {
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload?.detail)) {
    const messages = payload.detail
      .map((item) => item.msg)
      .filter((message): message is string => Boolean(message));
    if (messages.length) {
      return messages.join("; ");
    }
  }
  return `PlantOps API request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(15000),
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  }).catch(() => {
    throw new PlantOpsConnectionError(path, init?.method ?? "GET");
  });

  if (!response.ok) {
    let payload: ErrorPayload | null = null;
    try {
      payload = (await response.json()) as ErrorPayload;
    } catch {
      payload = null;
    }
    throw new PlantOpsApiError(
      response.status,
      errorMessage(payload, response.status),
      typeof payload?.detail === "string" || (Array.isArray(payload?.detail) && payload.detail.some(item => Boolean(item.msg))),
    );
  }

  return (await response.json()) as T;
}

function sessionPath(sessionId: string, suffix = ""): string {
  return `/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

export function createSession(
  input: CreateSessionInput,
): Promise<SessionSnapshot> {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getSession(sessionId: string): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId));
}

export function advanceSession(
  sessionId: string,
  minutes: number,
): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/advance"), {
    method: "POST",
    body: JSON.stringify({ minutes }),
  });
}

export function pauseSession(sessionId: string): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/pause"), { method: "POST" });
}

export function resumeSession(sessionId: string): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/resume"), { method: "POST" });
}

export function setSessionSpeed(
  sessionId: string,
  speed: PlaybackSpeed,
): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/speed"), {
    method: "PUT",
    body: JSON.stringify({ speed }),
  });
}

export function expediteRepair(
  sessionId: string,
  machineId: string,
): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/actions/expedite-repair"), {
    method: "POST",
    body: JSON.stringify({ machine_id: machineId }),
  });
}

export function prioritizeOrder(
  sessionId: string,
  orderId: string,
  priority: number,
): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/actions/prioritize-order"), {
    method: "POST",
    body: JSON.stringify({ order_id: orderId, priority }),
  });
}

export function placePurchaseOrder(
  sessionId: string,
  supplierId: string,
  quantity: number,
): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/actions/place-purchase-order"), {
    method: "POST",
    body: JSON.stringify({ supplier_id: supplierId, quantity }),
  });
}

export function startPreventiveMaintenance(
  sessionId: string,
  machineId: string,
): Promise<SessionSnapshot> {
  return request(
    sessionPath(sessionId, "/actions/start-preventive-maintenance"),
    {
      method: "POST",
      body: JSON.stringify({ machine_id: machineId }),
    },
  );
}

export function livingAction(sessionId: string, action: "authorize-overtime" | "activate-containment" | "expedite-purchase-order", purchaseOrderId?: string): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, `/actions/${action}`), {
    method: "POST", body: JSON.stringify(purchaseOrderId ? {purchase_order_id: purchaseOrderId} : {}),
  });
}


export function equipmentAction(sessionId: string, machineId: string, action: EquipmentAction): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, `/actions/${action}`), {
    method: "POST", body: JSON.stringify({machine_id: machineId}),
  });
}


export function resolveDecision(sessionId: string, eventId: string, choiceId: string): Promise<SessionSnapshot> {
  return request(sessionPath(sessionId, "/actions/resolve-decision"), {
    method: "POST", body: JSON.stringify({ event_id: eventId, choice_id: choiceId }),
  });
}
