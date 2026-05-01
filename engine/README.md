# Paper Engine Scaffold

This step includes:
- `paper-engine.js` with standalone config, account/state, order draft, draft validation, ledger submission, cash reservation for pending buy orders, pending-order cancellation, buy/sell fills for long-only positions, manual mark-to-market updates, manual valuation snapshots, manual score snapshots based on the current score preview logic, official score status derived from recorded score snapshots, a reusable portfolio summary helper, an equity timeline helper, manual benchmark baseline/current tracking, a contest return summary helper, raw trade stats, position weights, raw discipline metrics, and a read-only score preview helper.
- `paper-engine-smoke.html` for a tiny manual browser smoke test.

This step does not include yet:
- shorting or partial fills
- leaderboard ranking or automated snapshot scheduling
- price fetching, admin logic, storage, or app/page integration

Pending BUY orders reserve cash, pending BUY orders can be filled, and canceling pending orders releases reserved cash.
Long-only SELL orders are supported, SELL fills realize PnL using the position avg cost, and remaining long positions keep their avg cost.
Positions can be marked to market manually, and unrealized PnL plus equity summary are now available.
Manual valuation snapshots are supported, and an equity timeline helper is available.
Manual benchmark baseline/current tracking is supported, and contest return summary is available.
Raw trade stats are available, and raw discipline metrics are available.
The score preview helper is read-only and preview-only.
Score snapshots can be recorded manually, and they are based on the current score preview logic.
Official score status can be derived from recorded score snapshots, including latest, best, and delta-from-previous values.
Leaderboard ranking is still intentionally not implemented yet.

This module is isolated and not wired into the main app yet.
