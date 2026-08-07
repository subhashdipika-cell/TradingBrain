import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BacktestRequest } from "../api/types";

interface Props {
  onRun: (payload: BacktestRequest) => void;
  loading: boolean;
}

const DEFAULTS: BacktestRequest = {
  symbol: "NIFTY",
  num_days: 30,
  bar_minutes: 5,
  starting_capital: 1_000_000,
  base_iv: 0.12,
  annual_vol: 0.13,
  seed: 42,
};

export function BacktestForm({ onRun, loading }: Props) {
  const [form, setForm] = useState<BacktestRequest>(DEFAULTS);
  const [symbols, setSymbols] = useState<string[]>(["NIFTY", "BANKNIFTY"]);

  useEffect(() => {
    api
      .symbols()
      .then((r) => setSymbols(r.symbols))
      .catch(() => undefined);
  }, []);

  const update = (key: keyof BacktestRequest, value: string) => {
    setForm((prev) => ({
      ...prev,
      [key]: key === "symbol" ? value : Number(value),
    }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onRun(form);
  };

  return (
    <form className="card form" onSubmit={submit}>
      <h2>Backtest parameters</h2>

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

      <button type="submit" disabled={loading}>
        {loading ? "Running…" : "Run backtest"}
      </button>
      <p className="hint">
        Theta harvesting profits when implied &gt; realized vol. Costs
        (brokerage, STT, exchange, GST, stamp) are always applied.
      </p>
    </form>
  );
}
