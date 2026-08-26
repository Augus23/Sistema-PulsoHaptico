import {
  MotorCalibrationDTO,
  PolicyCode,
  PolicyDetail,
  PolicySummary,
  SystemStatus,
} from "./types";

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const DEFAULT_TIMEOUT_MS = 5000;

async function request<T>(
  baseUrl: string,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!baseUrl) {
    throw new ApiError("No configuraste la dirección del servidor todavía.");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    if (!response.ok) {
      const body = await safeJson(response);
      throw new ApiError(
        (body && (body.detail || JSON.stringify(body))) ||
          `Error HTTP ${response.status}`,
      );
    }

    return (await response.json()) as T;
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new ApiError("El servidor no respondió a tiempo (timeout).");
    }
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      "No se pudo conectar al servidor. Revisá la IP en Ajustes y que el celular esté en la misma red Wi-Fi.",
    );
  } finally {
    clearTimeout(timeout);
  }
}

async function safeJson(response: Response): Promise<any | null> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function getPolicies(baseUrl: string): Promise<PolicySummary[]> {
  return request<PolicySummary[]>(baseUrl, "/api/policies/");
}

export function getPolicyDetail(
  baseUrl: string,
  code: PolicyCode,
): Promise<PolicyDetail> {
  return request<PolicyDetail>(baseUrl, `/api/policies/${code}/`);
}

export function updatePolicyMotors(
  baseUrl: string,
  code: PolicyCode,
  motors: Pick<MotorCalibrationDTO, "motor_index" | "intensity_percent">[],
): Promise<PolicyDetail> {
  return request<PolicyDetail>(baseUrl, `/api/policies/${code}/motors/`, {
    method: "PUT",
    body: JSON.stringify({ motors }),
  });
}

export function activatePolicy(
  baseUrl: string,
  code: PolicyCode,
): Promise<{ sent: PolicyCode }> {
  return request(baseUrl, `/api/policies/${code}/activate/`, {
    method: "POST",
  });
}

export function getStatus(baseUrl: string): Promise<SystemStatus> {
  return request<SystemStatus>(baseUrl, "/api/status/");
}

export function updateStatus(
  baseUrl: string,
  patch: Partial<Pick<SystemStatus, "global_intensity_percent" | "mode">>,
): Promise<SystemStatus> {
  return request<SystemStatus>(baseUrl, "/api/status/", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export function stopMotors(baseUrl: string): Promise<{ stopped: boolean }> {
  return request(baseUrl, "/api/stop/", { method: "POST" });
}
