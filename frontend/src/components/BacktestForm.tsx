import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BacktestRequest } from "../api/types";

interface Props {
  onRun: (payload: BacktestRequest, realData: boolean) => void;
  loading: boolean;
}

const DEFAULTS: BacktestRequest = {
  symbol: "NIFTY",
  num_days: 30,
  bar_minutes: 5,
  starting_capital: 400_000,
  base_iv: 0.12,
  annual_vol: 0.13,
  seed: 42,
  strategy: "AUTO",
};

export function BacktestForm({ onRun, loading }: Props) {
  const [form, setForm] = useState<BacktestRequest>(DEFAULTS);
  const [symbols, setSymbols] = useState<string[]>(["NIFTY", "BANKNIFTY"]);
  const [strategies, setStrategies] = useState<{ name: string; description: string }[]>([
    { name: "AUTO", description: "Auto-select by market structure/regime" },
  ]);
  const [dhanAvailable, setDhanAvailable] = useState(false);
  const [realData, setRealData] = useState(false);

  useEffect(() => {
    api
      .symbols()
      .then((r) => {
        setSymbols(r.symbols);
        setDhanAvailable(r.dhan_data_available);
      })
      .catch(() => undefined);
    api
      .strategies()
      .then((r) => setStrategies(r.strategies))
      .catch(() => undefined);
  }, []);

  const update = (key: keyof BacktestRequest, value: string) => {
    setForm((prev) => ({
      ...prev,
      [key]: key === "symbol" || key === "strategy" ? value : Number(value),
    }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onRun(realData ? { ...form, symbol: "NIFTY50" } : form, realData);
  };

  return (
    <form className="card form" onSubmit={submit}>
      <h2>Backtest parameters</h2>

      <label>
        Strategy
        <select
          value={form.strategy}
          onChange={(e) => update("strategy", e.target.value)}
        >
          {strategies.map((s) => (
            <option key={s.name} value={s.name} title={s.description}>
              {s.name === "AUTO" ? "AUTO — by market structure" : `${s.name} · ${s.description}`}
            </option>
          ))}
        </select>
      </label>

      <label className={`toggle ${dhanAvailable ? "" : "disabled"}`}>
        <input
          type="checkbox"
          checked={realData}
          disabled={!dhanAvailable}
          onChange={(e) => setRealData(e.target.checked)}
        />
        Use real Dhan data{dhanAvailable ? "" : " (not configured)"}
      </label>

      {!realData && (
        <label>
          Symbol
          <select
            value={form.symbol}
            onChange={(e) => update("symbol", e.target.value)}
          >
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      )}

      {!realData && (
        <label>
          Sessions (days)
          <input
            type="number"
            min={1}
            max={120}
            value={form.num_days}
            onChange={(e) => update("num_days", e.target.value)}
          />
        </label>
      )}

      <label>
        Bar minutes
        <input
          type="number"
          min={1}
          max={60}
          value={form.bar_minutes}
          onChange={(e) => update("bar_minutes", e.target.value)}
        />
      </label>

      <label>
        Starting capital (₹)
        <input
          type="number"
          min={100000}
          step={50000}
          value={form.starting_capital}
          onChange={(e) => update("starting_capital", e.target.value)}
        />
      </label>

      {!realData && (
        <>
          <label>
            Implied vol (e.g. 0.12)
            <input
              type="number"
              step={0.01}
              min={0.01}
              value={form.base_iv}
              onChange={(e) => update("base_iv", e.target.value)}
            />
          </label>

          <label>
            Realized vol (e.g. 0.13)
            <input
              type="number"
              step={0.01}
              min={0.01}
              value={form.annual_vol}
              onChange={(e) => update("annual_vol", e.target.value)}
            />
          </label>

          <label>
            Seed
            <input
              type="number"
              value={form.seed}
              onChange={(e) => update("seed", e.target.value)}
            />
          </label>
        </>
      )}

      <button type="submit" disabled={loading}>
        {loading ? "Running…" : realData ? "Run on real data" : "Run backtest"}
      </button>
      <p className="hint">
        {realData
          ? "Replays your accumulated Dhan option-chain snapshots (real premiums + greeks) through TB001's hedged Iron Fly."
          : "Synthetic data: theta harvesting profits when implied > realized vol. Costs (brokerage, STT, exchange, GST, stamp) always applied."}
      </p>
    </form>
  );
}
