# YoMama production economy

> The default configuration enables connected business quests, conglomerate group projects and scarce Prestige focus costs. See [SYSTEM_ROLES.md](SYSTEM_ROLES.md) for the current gameplay and migration contract; older snapshots retain their previous rules.

The current game runs `production_economy.py` with `config/economy.v4.json`.
`economy.py`, `config/economy.v3.json`, the supplied JavaScript reference, and
its golden tests remain the original economic context. The previous engine's
notes are preserved in [engine/ECONOMY_V3.md](engine/ECONOMY_V3.md).

## Player loop

Produce actual goods, serve automatic customers, choose deliveries, and invest
in production, customer capacity, storage, or another business. Existing building
names and artwork are retained. All fifteen buildings operate under the new
rules. Every unlocked product is made independently: production never takes
ingredients from town stock, including goods made by the same business. Orders
request unlocked products from owned businesses; no supplier chain is required.

- All money and product quantities are whole integers. Work uses fixed-point
  counters, so fractional rates survive saving and replay without free goods.
- Production runs every 15 seconds. Each completed batch adds goods and pays
  that business's production cost. Cash, product unlocks and shelf space still
  limit output. Each resulting item can be sold or delivered once.
- Automatic customers buy at fixed unit prices, up to their per-product demand.
  Demand that cannot be served is not banked for unlimited future sales.
- Production, customers, and storage have independent levels and costs. Their
  effects are additive to their own base rate, with rising upgrade prices.
  Increasing production alone cannot raise customer demand.
- Storage is divided among a building's products. A full product shelf pauses
  that product until space is available; it cannot crowd out all other goods.
- There are no automatic ingredient buffers or separate Processing controls.
  The business pause stops all of its production and production costs.
- Save for this order reserves only the requested quantities, including incoming
  production after regular buyers receive first claim. Retail and surplus
  clearance respect those reservations.
  Overlapping commitments must fit the product shelf; release or replace an order
  to free its goods. A separate manual sales pause remains in Warehouse.
- Clear stock explicitly sells surplus at 60% of reference shop payout. It preserves
  regular-buyer and committed-order quantities and never generates a second inventory copy.
- Three optional deliveries have stable IDs and no expiry penalties. Fulfillment
  checks every required quantity before consuming anything, then pays the listed
  cash and materials exactly once. Replacing an order is free and immediately repeatable. It releases that order's
  reservations but pays no reward. Rapid clicks are serialized with current IDs.
- Each material saves 15 YM on construction. Material requirements cover about
  15% of a building's base price at that fixed rate. Missing materials can still
  be paid for in cash. New supply orders pay 110% retail value plus materials
  worth about 25% of their goods; quick cash pays 125%, regulars pay 115%.
- Construction and upgrades never trigger automatic spending. Existing
  businesses keep producing after expansion.

The first three businesses use familiar goods: the farm makes eggs and honey,
the roastery makes coffee and pastries, and the fish stall makes its own fish
products. Later businesses add food, industry, and energy products using the
supplied art set. Manual crafting is planned separately; the existing optional
practice workshops and explicit equipment crafting remain distinct actions.

Sector rhythms change when completed goods arrive while preserving average
production rates. Food keeps its small, frequent batches. Industry normally
waits twice as long for twice the output and production cost; it can complete
a smaller batch when cash or shelf space cannot support the larger one.
Energy/Tech products start at staggered times, with one initial wait of up to
two active game ticks (currently 30 game seconds). That wait pauses with the
business or class, survives reloads and does not grant work.
Production still advances in 15-second ticks. Existing saves retain accumulated
work and initialize missing start delays once; no class reset is needed.
The `production.sectorRhythms` setting enables these rhythms and may be disabled
for baseline simulations. This is a production timing change, not a speed bonus.

## Time and income

A town earns through at most 12 hours following its owner's last activity.
Another student's requests do not renew that allowance. Returning advances the
clock past skipped production, so repeated requests cannot claim it again.
Paid construction continues on the class clock, including across the production
cap. A teacher pause stops the class clock.

The main Sales, Costs and Profit figures show the last 60 game seconds, with
potential per-minute figures below. The operating statement records gross
walk-in and regular-buyer payments, production cash costs (including unsold
stock), and supplies/selling charges paid from those customer payments. Profit
margin is that operating cash profit divided by gross customer sales. Its
reference target assumes base levels and all output sold at the shop payout,
with production matching sales; it is not a guaranteed or clamped outcome. Manual-order and
clearance payments and their selling charges stay outside this customer statement.
Upfront purchases are also separate. Each business's forecast uses only its own
products and costs, without cross-business ingredient transfers.

Cash remains the spendable balance. Order and regular-buyer cards quote the
take-home payment after selling charges; production costs are paid separately.
Their percentage comparisons use the normal shop payout on the same take-home
basis. Stock and net-worth values retain their recoverable value. The overnight
report shows take-home customer cash and actual units produced.

## Saves and transaction boundaries

`game_api.py` owns SQLite persistence and transactions. The browser sends actions
and renders authoritative quantities, costs, requirements, and receipts. Actions
use the existing per-class lock and SQLite write transaction.

The first request for an old class records its original configuration, player
state and metadata in a `v4_migration` ledger entry. Cash and book value remain;
old stored monetary pools and already-delivered contract value become cash.
This does not invent product quantities or grant unearned contract rewards.
Owned buildings and paid construction/queues remain. Old upgrade levels map into
the new capped levels; old book value remains. An already-open licence stays
open. New rules start at migration time rather than replaying past class years.

Migration runs once. Current v4 classes keep their configuration snapshot even
when the default file changes. A SQLite backup of the local save is made before
local rollout; the test suite only uses temporary databases.

Independent production applies when existing v4 saves load, even if their saved
configuration contains old input recipes. Cash, stock, product unlocks, work
progress and existing orders remain. The obsolete Processing switch no longer
blocks output. No class reset is needed; publishing needs Manual Deploy.

## Current actions

All routes are under `/api/game/econ` and use the existing player token.

| POST route | Body besides token |
|---|---|
| `/upgrade` | `slot`, `kind`: `production`, `sales`, or `storage` |
| `/reserve` | `slot`, `reserve`: boolean |
| `/processing` | Legacy route; rejects toggles and directs players to the business Pause control |
| `/orders/fulfill` | `offerIndex`, `orderId` |
| `/orders/replace` | `offerIndex`, `orderId` |
| `/orders/commit` | `offerIndex`, `orderId`, `committed`: boolean |
| `/focus` | `slot`, `focus`: available specialty ID |
| `/sell` | `slot` |
| `/expand` | `tier` |

Login, state, quiz, licence, classroom controls, and Part 2 trading retain their
routes. The original `/level` and `/auto` aliases remain compatible with
production/customer upgrades. Old contract acceptance cannot silently act on a
new delivery. Price-event publishing is unavailable for the fixed-price model.

The licence now requires three businesses, production level three, a customer
upgrade, either three deliveries or 100 goods sold to ordinary customers, and the short economic quiz. The quiz questions match
the actual rules; the previous questions are preserved in `config/quiz.v3.json`.

## Validation and pacing

```sh
.venv/bin/python -m pytest tests -q
node --check econ.js
node --check teacher-econ.js
python3 tests/sim_production.py --days 7 --output previews/production-balance.json
```

The engine tests verify conservation, bounded customer sales, independent production,
storage fairness, saved work, optional orders, supplier-independent eligibility,
offline replay, and migration. API tests verify actual SQLite rollback,
concurrent fulfillment, stale IDs, cap renewal, teacher pause, late joins,
reset metadata, and licence enforcement. The original v3 oracle is still tested
separately, including through a pinned legacy API fixture.

Strategy simulations compare actual cash, deliveries, upgrades, and building
unlocks under transparent attendance schedules. They are balance diagnostics,
not evidence of player enjoyment or retention. The design uses established
production, delivery, and idle-management patterns; human playtests are still
needed to validate the particular combination and tune longer-term pacing.

Breakfast Club is an optional, one-time event in `breakfast_event.py`, opened
from Build. `POST /api/game/econ/event/breakfast` accepts start, make, cancel,
deliver, and upgrade intentions through the normal authenticated transaction.
It stores its progress in the player's economy JSON, uses the paused class
clock, and never spends town cash or inventory. Supplies refill to 12 per
ingredient; cooking requires inputs and has one active plus one queued batch.
Queued batches consume ingredients only when they start. Started batches keep
their original output if an upgrade is bought while they cook. Closing does
not reset the event, and offline replay only completes work already queued.
Four deliveries and a 100-event-coin upgrade lead to five town materials and a permanent recipe improvement once;
event coins have no exchange into town cash. Replay/reward farming is disabled.

## Meaningful progression (rules revision 2)

Upgrade buttons show capacity estimates, including product specialties. The
green production gain assumes all added output sells; it is not a cash promise
while demand is limited, shelves are empty or orders are being held. Storage
shows added spaces. A production upgrade can help deliveries without helping
retail.

At production level 3, the farm can specialize as a bakery supplier: eggs and
honey gain 25 percentage points of base production speed and tomatoes lose 25.
The roastery can favor coffee or pastries: the selected product gains
50 base speed points and the other loses 25. Mixed production remains available;
switching is free. These products are made independently without consuming inputs.

The Breakfast Regulars order grants a permanent 20% roastery customer-capacity
bonus after three deliveries, capped once. It can be earned before opening the
roastery. Its goods change from farm products to eligible roastery products
when that business is owned. The separate Breakfast Club cooking event grants
five materials and +25 base speed points to its chosen roastery recipe upon
completion. No useless final coins are awarded; event coins are cleared when
the kitchen closes. Existing completed kitchens gain the corresponding recipe
perk without repeating the material payment.

Farm and roastery artwork changes at upgrade levels 3 and 6 (highest production,
customer or storage level). Four new static sprites live in
`assets/buildings/upgrades/`; base-level animation strips remain intact.

The current licence page no longer offers the ineffective Keep/invest slider.
The visible trading desk uses a separate practice portfolio. The v4 `/keep`
endpoint rejects allocation requests; legacy v3 behavior is retained.

Older v4 saves keep money, inventories, buildings, materials and current offer
IDs. Existing offers honor their listed reward until completed or replaced;
new offers use the new reward rules. Existing whole-business holds are retained
and can be released in Warehouse. Reservation/focus/reputation fields default
safely when missing. The material saving is now fixed at 15 YM per unit, including
previously earned materials. A pre-change SQLite backup is in `backups/`.

## Free order rolls

Every new offer rolls Standard (40%), Small (15%), Bulk (10%), Large (25%),
Rare (8%) or Jackpot (2%). Small asks for half the normal quantity of one
product at the normal order price. Bulk asks for three times the normal quantity
of one product at 90% of the normal order price, trading lower payment per item
for a larger sale. Whole-unit rounding and shelf limits still apply.
Higher tiers request up to 3/4/5 distinct eligible goods and 1.5×/2×/2.5× base
quantities, capped to each product shelf. Their cash premium is 1.3×/1.75×/2.5×
the ordinary order's percentage of reference shop payout. The card shows the actual
shop-payout multiplier and total take-home payout. Existing offers keep their reward until
delivered or replaced; saved replacement cooldowns are ignored.

Rerolls do not spend or award cash, goods, materials or reputation. Fulfillment
still consumes every requested item and pays once. Independent deterministic
rolls use the saved player seed and order serial, so reloads preserve the sequence.
See [roll rules and verification](previews/order-rolls.md).
