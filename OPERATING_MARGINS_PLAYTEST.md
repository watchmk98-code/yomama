# Operating margin playtest

Reproduce: `.venv/bin/python previews/playtest_operating_margins.py`.

161 matched scenarios / 322 runs. Each measured run covers 24 game minutes. Ordinary warm starts first earn stock through 12 minutes of production with walk-in sales held. Fifteen additional maturity checks fill the real shelves through 62–202 game minutes of ordinary production before measurement. No inventory is inserted.
Established towns have identical 1,000,000 YM capital, installed levels and quest-unlocked products. Fresh cases use the real zero-cash starter farm. Base is level 1 throughout; maximum is level 12 throughout; production-heavy is Production 4 / Customers 1, sales-heavy is 1 / 4. Nonmaximum storage is level 1.

Every paired tick retained identical gameplay state after excluding only the new invoice ledger, frozen selling terms and operating statement. Cash, production costs/carry, inventory, offers, reward amounts, timers, materials, quests, net receipts, affordability and net worth matched exactly. Each enabled run also reconciled gross invoices minus selling fees minus production spending to its cash change, and each product reconciled opening stock plus production minus sales to closing stock.

## Targets and measured ordinary sales

These are base-level targets with all output sold: game-rounded, industry-inspired reference margins, not empirical forecasts for individual real businesses or guaranteed ordinary-play results. A fixed product tariff is calibrated using the reference selling price and base production cost. Mature base production matching sales approaches the target; upgrades, buyer discounts and temporary spending on unsold stock still change the resulting margin.

| Business | Base-level target (all output sold) | Base, empty stock | Base, 12-minute warm stock | Base, mature full shelves | Maximum levels, warm stock |
|---|---|---|---|---|---|
| Greenfield Farm | 6% | 5.52% | 5.52% | 6.02% | 4.14% |
| Harbor Fish Stall | 8% | 6.62% | 6.88% | 8.04% | 2.67% |
| Copper Kettle Roastery | 15% | 13.06% | 13.13% | 15.05% | 7.61% |
| Tinker's Garage | 12% | 10.73% | 10.81% | 12.04% | 7.41% |
| Ironworks Shop | 16% | 13.92% | 14.02% | 16.06% | 8.38% |
| Rooftop Solar Co-op | 20% | 17.76% | 17.64% | 20.07% | 10.92% |
| Meridian Cannery | 11% | 9.53% | 9.53% | 11.05% | 5.27% |
| Bluecollar Machine Works | 16% | 13.96% | 14.05% | 16.06% | 8.48% |
| Windward Turbine Field | 21% | 18.53% | 18.41% | 21.08% | 11.01% |
| North Grid Plant | 18% | 15.87% | 15.77% | 18.07% | 9.38% |
| Signal Relay Station | 18% | 15.91% | 15.81% | 18.07% | 9.53% |
| Atlas Freight Terminal | 12% | 10.47% | 10.54% | 12.05% | 6.34% |
| Node-7 Data Hub | 22% | 19.42% | 19.30% | 22.09% | 11.57% |
| Helios Solar Array | 23% | 20.30% | 20.17% | 23.09% | 12.06% |
| Orbital Uplink Center | 20% | 17.66% | 17.55% | 20.08% | 10.54% |

After shelves have filled through real production, all fifteen base businesses remain within 0.09 percentage points of their reference target over the 24-minute measurement. Earlier margins are lower because production is also funding stock accumulation. Maximum upgrades retain their existing cost tradeoff; the targets are not forced onto those configurations.

## Normal orders and regular buyers

The policy visits the normal Market every 30 seconds, fulfills a ready offer (materials then net reward), or saves one reachable offer and waits. It uses real fulfill/commit/replace functions. Four eligible recurring buyers cover all three sectors in established towns. No prototype board is used in these simulations.

| Town | Matched scenarios | Net cash before → after | Completed orders | Materials | Regular shipments |
|---|---|---|---|---|---|
| 6 businesses | 12 | 207286 → 207286 | 284 → 284 | 617 → 617 | 192 → 192 |
| 15 businesses | 12 | 4013561 → 4013561 | 407 → 407 | 7329 → 7329 | 192 → 192 |

## Accounting scope and limits

This adds a modeled product supply/selling charge reimbursed through the customer invoice and paid immediately from the same proceeds. Gross sales and expenses both increase; money left for the player and the original choices do not change. It is an accounting-model change, not evidence of a new tradeoff or better real-world market simulation.
Statements remain on a cash basis. Production spending is charged when output is made, including unsold goods; no cost-of-goods-sold inventory accounting, fixed rent, financing, tax or depreciation model is introduced. Inventory and net worth keep their existing reference-retail valuation; that is not historical cost basis. The regular buyer still leaves 90% of the reference reward before production costs, while the reimbursed tariff makes its gross invoice discount smaller.
Whole-YM settlement uses an independent fractional carry per business and sale channel. Tariffs do not rise with upgrades or follow a higher manual reward. Saved invoice tariffs survive reloads and configuration changes; old receipts never receive invented retroactive fees. New unit tests separately cover normal and goal deliveries, prototype delayed delivery, replay prevention, source accounting, zero-cash sales, paused/full shelves and removed-business reconciliation.
The sample proves deterministic progression preservation for its tested paths. It does not prove every future rule interaction or that children understand the gross/net distinction; UI review remains necessary.

Full paired output: `.checks/economy-playtest/operating-margins.json`.
