import { useMemo } from "react";
import type { EquityPoint } from "../api/types";
import { formatINR } from "../format";

interface Props {
  points: EquityPoint[];
  baseline: number;
}

// Lightweight dependency-free SVG equity curve.
export function EquityChart({ points, baseline }: Props) {
  const width = 720;
  const height = 280;
  const pad = 40;

  const { path, baselineY, min, max } = useMemo(() => {
    if (points.length === 0) {
      return { path: "", baselineY: height / 2, min: 0, max: 0 };
    }
    const values = points.map((p) => p.equity);
    const lo = Math.min(...values, baseline);
    const hi = Math.max(...values, baseline);
    const span = hi - lo || 1;

    const x = (i: number) =>
      pad + (i / Math.max(points.length - 1, 1)) * (width - 2 * pad);
    const y = (v: number) =>
      height - pad - ((v - lo) / span) * (height - 2 * pad);

    const d = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.equity)}`)
      .join(" ");

    return { path: d, baselineY: y(baseline), min: lo, max: hi };
  }, [points, baseline]);

  const last = points[points.length - 1];
  const up = last && last.equity >= baseline;

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <h2>Equity curve</h2>
        {last && (
          <span className={up ? "pos" : "neg"}>
            {formatINR(last.equity)}
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart"
        preserveAspectRatio="none"
      >
        <line
          x1={pad}
          x2={width - pad}
          y1={baselineY}
          y2={baselineY}
          className="chart-baseline"
        />
        <path d={path} className={up ? "chart-line pos-stroke" : "chart-line neg-stroke"} />
        <text x={pad} y={16} className="chart-tick">
          {formatINR(max)}
        </text>
        <text x={pad} y={height - 8} className="chart-tick">
          {formatINR(min)}
        </text>
      </svg>
    </div>
  );
}
