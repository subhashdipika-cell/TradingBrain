import type {
  BacktestRequest,
  BacktestResponse,
  HealthResponse,
} from "./types";

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8200/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return (await response.json()) as T;
}

export const api = {
  baseUrl: BASE_URL,

  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  symbols(): Promise<{ symbols: string[] }> {
    return request<{ symbols: string[] }>("/backtest/symbols");
  },

  runBacktest(payload: BacktestRequest): Promise<BacktestResponse> {
    return request<BacktestResponse>("/backtest/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
