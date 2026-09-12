# Production economy: accounting and progression check

This is a deterministic balance simulation and an engineering validation, not proof of fun or retention. It uses fresh saves; it never opens the user's database.

## Reproduce

```sh
.venv/bin/python -m pytest tests/test_production_economy.py -q
python3 tests/sim_production.py --days 7 --output previews/production-balance.json
```

The engine tests can also run without pytest: `python3 tests/test_production_economy.py`.

- Engine test result: **19 passed**.
- Configuration SHA256: `d323c4e863edd4259e3ad1b30e066f80babd80cad998a9dc426c4d8c42402337`
- Engine SHA256: `c8b1f100032afc99f705ce4f7f6f5f506bcebe9a9dd11521278c3cb9fb56735a`
- Full numeric snapshots and unlock times: [production-balance.json](production-balance.json).

## Verified economic properties

- Cash and goods remain nonnegative integers. A 2,000-action randomized sequence exercises production, upgrades, expansion, reserve, processing, delivery, replacement and bulk sales.
- Recipes require every input before consuming anything. Production cannot generate finished goods repeatedly from one batch of ingredients.
- Sales obey fractional customer demand, including rates above one unit per tick after upgrades. Forecasts deduct goods consumed by downstream businesses; forecasts never issue money.
- Reserving goods stops retail. Pausing processing releases the input buffer and keeps raw production running. Discounted bulk sales exclude protected inputs.
- Insufficient delivery stock changes nothing. A fulfilled or replaced order ID cannot be used again to obtain a reward.
- Each product has warehouse space, so faster tomatoes cannot permanently prevent honey from being replenished. Idle work cannot accumulate an unlimited instant-production burst.
- JSON reloads and irregular replay chunks produce identical state, including the offline cap. Successful construction never makes additional automatic purchases.
- Legacy monetary stock is credited once, ownership and paid construction are retained, and a previously earned trading licence survives migration.
- A focused delivery slot can rotate through every eligible product, including the seven-business case that previously repeated only three choices.

The API test suite separately verifies authentication, transactional concurrency, cap persistence across requests and classmate polling, migration snapshots and actual endpoint behavior. The original v3 engine oracle and golden tests remain intact.

## Attendance and decisions

All four bots spend ten minutes in the first session. Later sessions last five minutes every two hours; the casual bot visits every twelve hours. They act only during those sessions. All complete already-filled deliveries; none receives free stock, injected cash, a time boost or manual bulk sales.

- **Upgrades:** buys the affordable upgrade with the largest forecast improvement in total town sales per YM, then expands if no useful affordable upgrade remains.
- **Expansion:** saves for the earliest available business; buys useful upgrades while construction is running.
- **Deliveries:** reserves businesses supplying missing goods for its middle delivery, completes available deliveries, and otherwise follows the upgrade heuristic.
- **Casual:** uses the expansion rule with fewer visits.

These are explicit heuristics, not globally optimal strategies. Decisions use the engine's ingredient-aware flow forecast; reported cash comes from actual simulation transactions. Book worth means cash plus stored goods at retail value plus historical investment, not a liquidation quote.

## Results

| Strategy | Day 1 buildings | Day 3 buildings | Day 3 cash YM | Day 7 buildings | Day 7 cash YM | Day 7 book worth YM | Day 7 materials |
|---|---:|---:|---:|---:|---:|---:|---:|
| upgrades | 5 | 8 | 1,029,319 | 10 | 546,442 | 23,000,626 | 0 |
| expansion | 7 | 9 | 1,149,892 | 11 | 4,152,050 | 16,048,809 | 0 |
| deliveries | 4 | 7 | 292,813 | 9 | 970,165 | 16,185,063 | 280 |
| casual | 4 | 8 | 1,358,341 | 10 | 6,822,391 | 13,035,783 | 0 |

A fresh unreserved business makes its first automatic sale after **30 seconds**. The upgrade bot buys its first upgrade after **150 seconds**. The saving and casual bots finish their second business at **8 minutes 45 seconds**. The delivery bot receives its first delivery income at 90 seconds and finishes the second business at 7 minutes; its deliberately reserved farm delays ordinary customer sales.

Every tested strategy remains solvent and expands. The expansion bot owns more businesses; the upgrade bot accumulates more book worth. The casual bot continues making substantial progress with two visits a day. Those outcomes demonstrate viable progression under these policies, not a proof that no dominant policy exists.

## Tuning conclusions and playtest limits

1. Preserving fractional sales credit fixed a real throughput bug: the original draft silently reduced 65% demand to 50% and capped fast businesses at one sale per tick.
2. Reserving warehouse room per product fixed a real delivery stall: replenishing a consumed slow product could otherwise be blocked forever by faster products.
3. Expansion material requirements now rise with progression. The delivery bot holds 280 materials on Day 7; its next two buildings require 115 and 150. These savings have a near-term purpose. Players can still pay a roughly 15% cash premium instead of collecting missing materials.
4. The upgrade bot buys repeatedly during its first ten-minute visit and only starts its second business at the next visit. Saving for expansion is a meaningful alternative. Playtesting must confirm that players understand this choice and do not mistake it for a broken timer.
5. The delivery bot completes 900 orders in the week. This is a deliberately intensive control policy, not a recommended daily task count. Observe whether optional deliveries feel rewarding or become repetitive; ordinary sales must continue supporting progress without constant order management.
6. Simulations cannot assess comprehension, enjoyment, attachment to buildings, session fatigue or the desire to return. Test the first ten minutes and a real next-day return with players before claiming those outcomes.
