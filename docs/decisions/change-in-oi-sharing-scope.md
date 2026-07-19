# Scope — Change-in-OI (ΔOI) for TradingBrain, shared from AlphaEdge

**Status:** scoped, not built (2026-07-19). Follow-up to the OI/Greeks audit that
produced the TB001 gamma dampener (`ea17fab`).

## The gap
TradingBrain reads OI as a **stateless snapshot**: `chain.max_oi_strike()` drives
short-strike placement (`credit_sellers._oi_short_index`), combined OI nudges the
iron-fly body (`tb001.core_layer._body_strike`), and the level engine uses the
walls. All correct — but none of it can distinguish:

> *"writers just piled into the 24,500 call in the last hour"*
> from *"that OI has been sitting there for three days."*

For a seller that difference is the whole point: a **freshly built** wall is a live
defense; a **stale or unwinding** wall is a fading one. No ΔOI exists anywhere in
the codebase (no `prev_oi`, no OI history, no spurts).

## Why sharing beats rebuilding — the decisive facts
1. **AlphaEdge already collects it.** `strategy-lab/dhan_options_collector.py`
   snapshots ATM±5 CE+PE every ~60s to
   `strategy-lab/data/options/{UNDER}_OPT_{date}.csv`, including `prev_oi`.
2. **Serving it costs ZERO Dhan quota.** The bridge's `GET/POST /dhan/oitrend`
   (`mt5-bridge/oi_metrics.py:build_oitrend`) reads those **CSVs only** — it never
   calls Dhan. Verified. This matters enormously: the option-chain endpoint is
   limited to ~1 req/3s **per account**, and the collector + bridge already
   collide on it intermittently. A second *collector* would make that worse; a
   second *consumer of the bridge* costs nothing.
3. **Both apps already share one Dhan account.** TradingBrain's
   `config.DHAN_CONFIG_PATH` defaults to
   `D:/AlphaEdge/strategy-lab/dhan_config.json` — cross-app sharing precedent
   already exists, and it's the same account whose rate limit we must protect.
4. **The payload is ready.** A live call returns 76 five-minute buckets × 14
   strikes, each with `ce`/`pe` arrays of `oi, ltp, iv, vol, delta` + `prevOi`.
   That is exactly the ΔOI history TradingBrain lacks.

## Design: consume raw, derive locally (NOT a port of oi.js)
AlphaEdge's rule is *"the bridge serves RAW bucketed series; `engines/oi.js` owns
all DERIVED math — one implementation, no Python port."* Porting `oi.js` would
break that and create two drifting implementations.

We avoid this by noting that **TradingBrain needs different derivations**.
`oi.js` computes a *buyer's directional* composite (smart-money bias, centroid
migration, divergence). A seller needs three narrow, different reads:

| Read | Question it answers | Consumer |
|---|---|---|
| `wall_freshness` | Was this wall built **today**, or is it legacy? | `_oi_short_index` |
| `wall_trend` | Is OI **building or unwinding** at my short strike? | entry gate + in-trade monitor |
| `two_sided_writing` | Are both sides writing (range) or unwinding (trend)? | regime / strategy routing |

So this is **not** duplicated logic — it is seller-specific derivation over a
shared raw feed. Small surface (~100 lines), no drift risk against `oi.js`.

```
AlphaEdge collector ──► CSVs ──► bridge /dhan/oitrend (raw series, no Dhan call)
                                          │
                    ┌─────────────────────┴─────────────────────┐
        AlphaEdge engines/oi.js (buyer)        TradingBrain oi_flow.py (seller)
        directional composite                  freshness / trend / two-sidedness
```

## Deliverables
- **A — `app/domains/market/oi_flow.py`** (new): HTTP client for
  `/dhan/oitrend` (localhost:5000, symbol map `NIFTY→NIFTY50`, `BANKNIFTY→BANKNIFTY`),
  60s in-process cache (ΔOI moves slowly; the collector only writes each ~60s),
  plus the three derivations above. Returns a small `OiFlow` dataclass.
  **Fails soft**: bridge down / stale / missing symbol ⇒ `None`, and every
  consumer keeps today's exact behaviour.
- **B — enrichment**: engine populates `context.metadata["oi_flow"]` each poll
  (guarded like the OI-wall block).
- **C — first consumer**: `_oi_short_index` prefers a **fresh** wall; when the
  chosen wall is unwinding, fall back to the fixed `min_steps` offset rather
  than trusting a fading defense. Journal the reason.
- **D — (later, evidence-gated)** in-trade monitor: OI building against a short
  strike ⇒ tighten/exit early. Only after A–C show value.

## Risks / open questions
- **Operational coupling:** TradingBrain would depend on AlphaEdge's bridge +
  collector running. Mitigated by fail-soft (A), but it means ΔOI is simply
  absent on days AlphaEdge isn't started. Document in the runbook; consider
  promoting the collector to a shared always-on service later.
- **Symbol/expiry alignment:** the bridge serves the **front** expiry; TB trades
  the front weekly, so they align — including on expiry day, where AlphaEdge now
  dual-collects and `build_oitrend` filters to the front chain. Verify for
  BANKNIFTY (different expiry cycle) before enabling it there.
- **Coverage:** collector runs market-hours only, and only ATM±5 strikes — walls
  outside that band are invisible. Widen `--range` if TB's shorts sit further out
  than 5 strikes.
- **Freshness definition** needs one honest calibration pass: "built today" via
  `oi vs prevOi` (prior-day close) vs "built in the last hour" via the intraday
  series. The latter is more useful and the series supports it; pick with data.
- **Don't overreach:** a wall that is stale is not automatically bad — it may be
  a long-standing, genuinely respected level. Freshness should *rank* walls, not
  veto them.

## Effort
A + B ≈ one focused session (client + cache + three derivations + fail-soft).
C is small. Do A–C, forward-test alongside the gamma dampener, then judge D.

Related: `D:/alphaedge/docs/cvd-orderflow-scope.md` (same shape: shared bridge,
derive locally), and the human-touch level engines shipped across all four apps.
