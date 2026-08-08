# TradingBrain Walk-Forward Report — 2026-08-09

## Scope

This report evaluates the current fixed-rule option-selling strategy against
the collected AlphaEdge Dhan snapshots in:

`D:\alphaedge\strategy-lab\data\options`

All runs used ₹1,000,000 starting capital, real option premiums, Indian F&O
transaction costs, the current portfolio risk gate, and the current 1.5×
short-premium stop. No test window was used to tune parameters.

The evaluator uses chronological rolling windows. Nifty50 and BankNifty use
10 training sessions, 5 validation sessions, and 5 out-of-sample test
sessions, stepped by 5 sessions. FinNifty uses 6/3/3 stepped by 3 because it
has fewer files.

## Out-of-sample results

| Symbol | Files | Test folds profitable | Average test expectancy | Interpretation |
|---|---:|---:|---:|---|
| NIFTY50 | 34 | 0/3 | -₹889.83 | Not validated |
| BANKNIFTY | 34 | 1/3 | ₹499.82 | Not validated |
| FINNIFTY | 18 | 1/3 | ₹91.82 | Not validated |

### NIFTY50

- Fold 1 test: 1 trade, -₹2,669
- Fold 2 test: 0 trades
- Fold 3 test: 0 trades
- Test folds profitable: 0/3

### BANKNIFTY

- Fold 1 test: 0 trades
- Fold 2 test: 0 trades
- Fold 3 test: 1 trade, +₹1,499
- Test folds profitable: 1/3

### FINNIFTY

- Fold 1 test: 1 trade, +₹275
- Fold 2 test: 0 trades
- Fold 3 test: 0 trades
- Test folds profitable: 1/3

## Conclusion

The risk architecture is materially safer, but the strategy is not yet
validated as a profitable production system. The main evidence is the low
trade count and the lack of consistent positive out-of-sample folds. These
results should remain paper/forward-test only until a larger history produces
adequate trades per fold and consistent cost-adjusted expectancy.

The walk-forward runner is available at
`backend/app/application/walk_forward.py` and can be run with:

```powershell
$env:PYTHONPATH = "F:\Projects\TradingBrain\backend"
python -m app.application.walk_forward `
  --directory "D:\alphaedge\strategy-lab\data\options" `
  --symbol NIFTY50
```
