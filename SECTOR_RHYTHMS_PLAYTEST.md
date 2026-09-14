# Sector rhythm playtest

Reproduce: `.venv/bin/python previews/playtest_sector_rhythms.py`.

192 matched scenarios (384 runs), 24.0 minutes each; warm starts first produce for 8.0 minutes with shop sales held.
Established scenarios have identical 1,000,000 YM starting capital, installed levels, quest-unlocked products, and actual empty shelves. No inventory is inserted. Fresh-opening cases start with the real zero-cash farm.
Base levels are Production 1 / Customers 1; production-heavy is 4 / 1; sales-heavy is 1 / 4. Storage stays at level 1. The only rule difference is `production.sectorRhythms`.

All runs passed exact cash and per-product stock conservation. Every matched pair retained identical displayed average sales and cost forecasts; actual receipts can differ through timing, full shelves, regular deliveries, and which offers are ready.

**Average production rates are protected; actual player outcomes are not identical.** Prototype manual-order timing can change the offer sequence and produce large cash/material differences. The seed comparison below checks whether the initial large differences repeat consistently.

Across 114 automatic-sales scenarios, the median change in actual net cash was 0.0 YM; range -657 to 657 YM over the measurement window. 142 of 192 matched scenarios changed at least one recorded timing or outcome measure.

Automatic-sales paired percentage changes: median 0.00%, range -3.02% to 0.93%. These are actual net cash, including production expenses; they are not changes to quoted YM/min.

## Representative empty-stock patterns

| Business, base levels | Before, first 8 ticks | After, first 8 ticks | Net cash before → after |
|---|---|---|---|
| farm | [1, 2, 1, 3, 1, 2, 1, 3] | [1, 2, 1, 3, 1, 2, 1, 3] | 296 → 296 |
| garage | [1, 2, 1, 3, 1, 2, 1, 3] | [0, 2, 0, 4, 0, 2, 0, 6] | 940 → 916 |
| solar_coop | [1, 2, 1, 3, 1, 2, 1, 3] | [1, 1, 2, 1, 2, 2, 2, 1] | 1939 → 1952 |

## Prototype orders and recurring buyers

These manual-order policies use the separate `order_engine.py` prototype, not the normal Market order handler. They exercise real production, buyer reservations, inventory and cash changes. The scripted visitor checks every 30 seconds, refreshes at most five prototype offers, delivers one ready offer, or saves a reachable order. Regular buyers are selected from the actual eligible list; supplied stock always follows the real reservation rules. Both runs use the same seed. Different ready offers can lead to different later rewards, so this measures one policy path, not a guaranteed sector advantage.

| Scenario | Net cash before → after | Regular shipments | Orders completed | Materials | First 10 materials, minutes |
|---|---|---|---|---|---|
| town-1 / regulars_refresh | 499 → 499 | 20 → 20 | 7 → 7 | 2 → 2 | None → None |
| town-3 / regulars_refresh | 2062 → 2062 | 24 → 24 | 17 → 17 | 4 → 4 | None → None |
| town-6 / regulars_refresh | 7949 → 7642 | 30 → 30 | 26 → 20 | 1 → 21 | None → 15.75 |
| town-15 / regulars_refresh | 197022 → 158090 | 30 → 30 | 31 → 24 | 778 → 41 | 5.75 → 23.25 |
| fresh-opening / walkins | 296 → 296 | 0 → 0 | 0 → 0 | 0 → 0 | None → None |
| fresh-opening / regulars_refresh | 421 → 421 | 19 → 19 | 6 → 6 | 3 → 3 | None → None |
| town-6-goal / keep_for_material_goal | 8550 → 8088 | 30 → 30 | 31 → 32 | 24 → 15 | 21.25 → 10.25 |
| town-6-goal / pause_for_material_goal | 8080 → 7611 | 16 → 5 | 26 → 30 | 27 → 20 | 9.25 → 18.25 |

## Ten-seed prototype sensitivity check

Seeds: 7, 11, 19, 23, 31, 43, 53, 61, 71, 97. Each pair has identical installed levels, empty starting stock, capital and policy; only sector rhythms differ. Each policy runs for 24.0 game minutes.

| Town / policy | Aggregate cash before → after | Cash change | Median paired cash change | Aggregate orders | Aggregate materials | Paired cash range |
|---|---|---|---|---|---|---|
| 6 / regulars_refresh | 83584 → 80889 | -3.22% | -265 YM | 254 → 240 | 160 → 213 | -9.67% to +5.44% |
| 15 / regulars_refresh | 1738985 → 1601871 | -7.88% | -11252.5 YM | 282 → 251 | 4542 → 1959 | -20.98% to +4.75% |
| 6 / keep_for_material_goal | 82264 → 81805 | -0.56% | -122 YM | 272 → 269 | 190 → 199 | -8.29% to +12.88% |
| 6 / pause_for_material_goal | 84675 → 81964 | -3.20% | -183.5 YM | 314 → 305 | 256 → 248 | -10.85% to +11.27% |

| Town / policy | Median paired orders change | Median paired materials change | Seeds with less cash |
|---|---|---|---|
| 6 / regulars_refresh | -1 | +0 | 9/10 |
| 15 / regulars_refresh | -3 | -293 | 8/10 |
| 6 / keep_for_material_goal | -1 | +0 | 7/10 |
| 6 / pause_for_material_goal | -1 | -3 | 8/10 |

The largest prototype cash loss was 20.98% in the 15-business town (seed 43). The 15-business regulars-and-refresh policy lost 7.88% aggregate cash, 10.99% orders, and 56.87% materials. Eight of ten seeds earned less cash; this is not explained by only the first unlucky seed. It remains a prototype-policy balance concern rather than evidence that all normal Market play has the same penalty.

Material-goal completion times (before → after, minutes):

- keep_for_material_goal: median 7.75 → 10.25; successes 6/10 → 7/10. Medians include successful runs only.
- pause_for_material_goal: median 10.25 → 11.0; successes 9/10 → 10/10. Medians include successful runs only.

A separate ten-seed recurring-only check signs Copper Café (Food), Rally Crew and Builders Union (Industry), and Neighborhood Grid (Energy), covering all three sector rhythms without manual-order selection.
Aggregate shipments: 160 → 160; aggregate net cash: 64820 → 63920 YM.

## Normal Market order check

A separate check used the normal `production_economy.fulfill_order`, `commit_order`, and `replace_order` handlers, with no prototype board. This covered six and fifteen businesses over the same ten seeds, 24 minutes per run, base levels, empty stock, and identical 1,000,000 YM capital: 40 runs total. Four real regular buyers covered Food, Industry, and Energy.

Every 30 seconds, the policy fulfilled a ready offer, preferring materials then cash. Otherwise it saved one reachable offer and waited until completion. It only attempted replacement if all three offers were unreachable; no replacements were needed. Exact per-action cash/material/stock changes and full-run cash and per-product stock conservation passed in every run.

| Normal Market town | Aggregate cash before → after | Cash change | Median paired cash change | Completed orders | Materials | Regular shipments |
|---|---|---|---|---|---|---|
| 6 businesses | 72,071 → 70,326 | -2.42% | -74 YM | 81 → 76 (-6.17%) | 97 → 80 | 160 → 160 |
| 15 businesses | 1,592,345 → 1,607,642 | +0.96% | +153 YM | 155 → 147 (-5.16%) | 506 → 744 | 160 → 160 |

The normal policy completed about 5–6% fewer orders; it did not show the prototype's broad advanced-town cash/material loss. Regular shipments stayed identical. No production cash/storage blocks, waiting regular deliveries, or saved-order shelf rejections occurred. Actual earnings still varied considerably by seed: the six-business seed 71 lost 12.52% cash, while the fifteen-business seed 61 gained 7.47% after a later jackpot. These are timing and offer-path effects, so equal average forecasts do not promise equal manual earnings.

The normal check's scratch script and full results are `.checks/sector-rhythms/normal_orders.py` and `.checks/sector-rhythms/normal-orders.json`. It is separate from the reproduction command above.

## Longer window and alternative cadence

A separate one-hour, fifteen-business prototype comparison over the same ten seeds retained full Industry grouping. Aggregate cash changed from 5,189,539 to 5,019,590 (-3.27%); completed orders from 890 to 841 (-5.51%); materials from 16,237 to 9,864 (-39.25%). All runs passed conservation. The early cash penalty diminished, while order count and material sensitivity remained.

An in-memory counterfactual grouped only Industry goods with base cycles of at most two ticks, leaving the slowest goods ungrouped. Forty additional runs covered the same four ten-seed prototype policies and all passed conservation. In the fifteen-business policy, cash was 1,606,507 (-7.62% versus the original baseline), orders 255, and materials 2,150, compared with full-grouping cash 1,601,871 (-7.88%), 251 orders, and 1,959 materials. This scarcely improved the advanced-town cash difference, so it was not adopted. No counterfactual engine changes were written. Full counterfactual data is `.checks/economy-playtest/sector-rhythms-fast-only.json`.

## Interpretation

Food keeps its existing cadence. Industry releases goods in larger groups; it falls back to one affordable batch when cash or shelf headroom is tight, so an odd-capacity saved order can still finish. Energy adds one-time product startup delays, then preserves existing cycle lengths.
The deterministic cadence change can have large indirect effects on a player who continually selects and refreshes prototype orders. Ten seeds are a sensitivity sample, not proof that all policies, progression stages, or long-run earnings are balanced. Scripted play cannot establish whether children notice or enjoy the distinction. The separate normal-order check above covers one concrete policy; its lower completion counts still need playtesting. This is a first balance pass, not proof that every manual-order strategy retains its previous earnings.
Fractional cost carry can shift a whole YM across measurement boundaries; exact fixed-point costs are separately covered by the sector tests. The fresh-opening examples use the real zero-cash starter farm and, where applicable, prototype orders; they do not automate expansion purchases.

Full per-scenario output is in `.checks/economy-playtest/sector-rhythms.json`.
