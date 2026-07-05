import { useState } from "react";

/**
 * Clickable TradingBrain logo banner that acts as a refresh button:
 * clicking it reloads the dashboard (re-checks backend health, re-fetches
 * results). Falls back to a styled title if the logo image is absent.
 */
export function Brand() {
  const [broken, setBroken] = useState(false);

  const refresh = () => window.location.reload();

  return (
    <button
      className="brand"
      onClick={refresh}
      title="Click to refresh"
      aria-label="Refresh TradingBrain dashboard"
    >
      {broken ? (
        <span className="brand-fallback">
          <strong>
            Trading<span className="brand-accent">Brain</span>
          </strong>
          <small>Think · Validate · Execute · Learn</small>
        </span>
      ) : (
        <img
          src="/tradingbrain-logo.png"
          alt="TradingBrain — Think · Validate · Execute · Learn"
          className="brand-logo"
          onError={() => setBroken(true)}
        />
      )}
      <span className="brand-refresh">⟳ Refresh</span>
    </button>
  );
}
