import type {
  BacktestRequest,
  BacktestResponse,
  DailyReport,
  ExportResult,
  ForwardTestRequest,
  ForwardTestStartResponse,
  ForwardTestStatus,
  HealthResponse,
  ResultRecord,
  ResultSummary,
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

  symbols(): Promise<{ symbols: string[]; dhan_data_available: boolean }> {
    return request<{ symbols: string[]; dhan_data_available: boolean }>(
      "/backtest/symbols",
    );
  },

  runBacktest(
    payload: BacktestRequest,
    realData = false,
  ): Promise<BacktestResponse> {
    const path = realData ? "/backtest/dhan" : "/backtest/run";
    return request<BacktestResponse>(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listResults(): Promise<{ results: ResultSummary[] }> {
    return request<{ results: ResultSummary[] }>("/results");
  },

  getResult(id: string): Promise<ResultRecord> {
    return request<ResultRecord>(`/results/${id}`);
  },

  runForwardTest(payload: ForwardTestRequest): Promise<ForwardTestStartResponse> {
    return request<ForwardTestStartResponse>("/forward-test/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  forwardTestStatus(): Promise<ForwardTestStatus> {
    return request<ForwardTestStatus>("/forward-test/status");
  },

  dailyReport(date?: string): Promise<DailyReport> {
    return request<DailyReport>(`/reports/daily${date ? `?date=${date}` : ""}`);
  },

  exportDaily(date?: string): Promise<ExportResult> {
    return request<ExportResult>(
      `/reports/daily/export${date ? `?date=${date}` : ""}`,
      { method: "POST" },
    );
  },

  exportMonthly(month?: string): Promise<ExportResult> {
    return request<ExportResult>(
      `/reports/monthly/export${month ? `?month=${month}` : ""}`,
      { method: "POST" },
    );
  },
};
