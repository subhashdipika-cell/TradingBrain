TradingBrain logo
=================

Save the TradingBrain banner image here as:

    frontend/public/tradingbrain-logo.png

The homepage header (src/components/Brand.tsx) renders it as a clickable
banner that refreshes the dashboard. Until the file is present, a styled
"TradingBrain — Think · Validate · Execute · Learn" title is shown instead
(graceful fallback), so nothing breaks.

Any web image format works if you also update the src path in Brand.tsx
(e.g. tradingbrain-logo.jpg / .webp). PNG at the path above needs no code change.
