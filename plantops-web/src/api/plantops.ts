import type {
  CreateSessionInput,
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

  constructor(status: number, message: string) {
    super(message);
    this.name = "PlantOpsApiError";
    this.status = status;
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
  }).catch((error: unknown) => {
    throw new Error(`Cannot reach PlantOps at ${API_BASE_URL} for ${init?.method ?? "GET"} ${path}. ` +
      `Check that dev:full is running. ${error instanceof Error ? error.message : "Connection failed."}`);
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
