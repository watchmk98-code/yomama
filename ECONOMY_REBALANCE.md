# Economy working brief

The user approved realistic operating-margin targets for normally managed
businesses, preserving upgrade affordability and progression speed. Keep the
existing readable Build/Market design and all fifteen businesses.

## Keep

- Independent production: no automatic consumption of another product.
- Food's frequent batches, Industry's paired batches with affordability/shelf
  fallback, and Energy's one-time staggered starts.
- Regular buyers receive first claim on goods and lower take-home payments.
- Manual orders consume real stock; their rewards, materials, reservations,
  and timed-preview delivery schedules must retain their economic value.
- Existing cash, construction grants, upgrades, quests, saved orders,
  reference stock valuations, and recovery through free starter tomatoes.

## Authorized implementation

Introduce a fixed supply-and-selling expense for each finished product. The
customer's gross invoice includes that expense; it is paid from sale proceeds
at settlement. Gross receipts and the expense are recorded together. The
player keeps the existing take-home payment, so no new working-capital wallet
or automatic debt is needed. Production expenses remain payable when goods
are made. This changes the modeled invoice/cost structure, not order rewards
or spendable-cash progression.

The displayed statement remains explicitly **cash based**: customer receipts
minus production cash expenses and customer selling expenses. It is not a
claim to GAAP operating or net profit. Unsold stock remains an asset valued at
the existing recoverable reference value, not at the inflated gross invoice.
Targets describe mature base-level operation where production matches sales
at the reference shop payout: all output is sold, with no ongoing stock buildup.
Stock accumulation, upgrades, buyer discounts and batch timing can move the
cash margin away from that reference. One-off order/clearance invoices and fees
are recorded separately from the recurring customer statement.

Targets are rounded game design choices inspired by January 2026 US industry
operating margins, not claims about individual small businesses:

| Business | Target |
|---|---:|
| Farm | 6% |
| Fish Stall | 8% |
| Roastery | 15% |
| Garage | 12% |
| Ironworks | 16% |
| Solar Co-op | 20% |
| Cannery | 11% |
| Machine Works | 16% |
| Turbine Field | 21% |
| Grid Plant | 18% |
| Relay Station | 18% |
| Freight Terminal | 12% |
| Data Hub | 22% |
| Solar Array | 23% |
| Uplink Center | 20% |

Reference: [NYU Stern, margins by US industry, January 2026](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/margin.html).
Examples include agriculture 5.45%, food processing 10.63%, restaurant/dining
15.79%, machinery 15.86%, power 21.47%, and telecom services 20.47% pretax
unadjusted operating margins. Retail, repair, logistics, and mixed technology
businesses use illustrative targets rather than an exact listed-company match.

## Required verification

Compare enabled and disabled rules on identical actions/ticks, including fresh
cash-poor play, every business, regular buyers, normal and prototype orders,
max upgrades, paused/full shelves, migration, and reload. Cash, stock, costs
paid at production, materials, rewards, timers, and purchase affordability
must match. Gross receipts minus selling fees must reconcile to take-home
cash; no past receipts may be invented on migration. Run the complete Python
suite, JavaScript syntax checks, and desktop/mobile UI checks.

Changes stay local until published. Live deployment requires a push and
Manual Deploy. This design supports migration in place without resetting a
class; existing explicit opt-outs remain on their saved rules.

## Verified locally

The complete Python suite passes: 709 tests. The operating-margin playtest
covers 161 paired scenarios / 322 runs with identical gameplay economics;
mature base-level margins stay within 0.09 percentage points of their targets.
JavaScript syntax checks pass. Actual backend UI checks pass for all fifteen
businesses at 1800×1050 desktop, 390×844 portrait and 844×390 landscape,
including all finance values, target tooltips, both guides and Market payout
comparisons, with no clipped metrics or page errors.

Local preview: http://127.0.0.1:3023/buildings.html (temporary town).
See `OPERATING_MARGINS_PLAYTEST.md` for accounting scope and playtest limits.

## Normal local game activated

The regular server at http://127.0.0.1:3000/buildings.html now runs the current
engine. Five existing local rule snapshots predated `businessDesign`; those
snapshots were explicitly upgraded to the current rules after settling elapsed
play under the previous running engine. The empty class uses current defaults
on its first join. Database backups are retained privately under `.checks/`.

All ten existing towns migrated without resetting cash, buildings, levels,
inventory, materials, construction, or existing order promises. Authenticated
normal-game API checks confirmed enabled margin statements for every saved
town, matching finance totals and current Build assets. The login wall still
rejects unsigned visitors. The full 709-test suite and JavaScript checks pass.

This activation changed only the local database and running local server.
Live classes remain unmodified. Live snapshots that predate business costs
also need an explicit rule update or reset after publishing and Manual Deploy;
a server restart alone does not replace those saved rules.
