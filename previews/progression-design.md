# Meaningful progression: farm → roastery

**Follow-up:** The replacement cooldown described below has been removed.
Orders now have free, repeatable rarity rolls. See [current order rules](order-rolls.md).

The first playable revision makes spending easier to understand, removes delivery
administration, and gives the farm/roastery lasting differences. Shared economy
improvements apply to all fifteen businesses; specialties and new exterior art
currently focus on the farm and roastery.

## Established patterns and their application

- [Hay Day truck orders, official Supercell support](https://support.supercell.com/hay-day/en/articles/truck-orders-2.html)
  describes a choice of orders, cash/experience rewards, product-dependent extra
  rewards, and a replacement wait. Here the board distinguishes quick cash,
  construction supplies, and a lasting customer relationship. Replacing an order
  is free, with a 60-second delay before replacing that slot again. Orders never
  expire and ordinary sales remain a viable alternative.
- [Factorio's late-game design notes, Wube](https://www.factorio.com/blog/post/fff-129)
  identify repetitive management and short-lived investments as causes of
  stagnation, and discuss longer-lived infrastructure and automation. Here
  order-specific reservations automate stock handling, while the Breakfast
  Club recipe improvement and Breakfast Regulars customer bonus persist.
- Production capacity, ingredient bottlenecks, inventory allocation and the
  opportunity cost of using ingredients are the operating-business concepts.
  Upgrade forecasts measure the whole town's sustainable customer income,
  including downstream consumption. They do not mistake unsold production
  for revenue. Fixed-price goods keep this causal relationship readable.

These sources document established mechanics and design reasoning. They do not
establish that this particular implementation improves enjoyment or retention.

## What the player can decide

1. Upgrade customers for cash, production for available goods, storage for room,
   or save for expansion. The button states the estimated consequence. A negative
   effect can occur when extra processing diverts ingredients from better-served
   customers; it is shown rather than hidden.
2. Save only a delivery's requested goods from Market. Recipes, retail, clearance
   and other orders cannot spend the same committed stock. Excess keeps selling.
3. At production level 3, keep a mixed farm or favor bakery supplies. At the
   roastery, keep a mixed café or favor coffee/pastries. Each specialty has a
   production tradeoff and is freely reversible.
4. Supply Breakfast Regulars three times for +20% roastery customer capacity.
   This does not increase prices or bypass ingredient shortages.
5. Complete Breakfast Club to retain +25 percentage points of base production
   speed for the chosen roastery recipe, plus five materials. Final event coins
   have been removed because there is nothing left to purchase.

Materials consistently save 15 YM each, regardless of building price. New supply
orders award materials proportional to the goods' retail value. The licence
accepts 100 ordinary goods sold OR three deliveries. The ineffective allocation
slider is removed; the existing trading desk remains a separate practice portfolio.

## Building art

[View the six-stage comparison](progression-art.html). Four original PNG sprites
were generated with the built-in image_gen tool and copied to
`assets/buildings/upgrades/`. Prompts, including the black-background correction,
are preserved in that directory's `prompts.json`.

- Farm level 3: greenhouse and chicken coop.
- Farm level 6: expanded greenhouse, extra silo, loading area and apiary.
- Roastery level 3: pastry window, awning and outdoor café seating.
- Roastery level 6: attached bakehouse, oven and larger café frontage.

The highest production/customer/storage level selects art at levels 3 and 6.
Original level-1 animation strips remain untouched. The new variants are static
sprites on black, matching the game surface; no animation is advertised for them.

## Validation

- Complete Python suite: 68 passed, including the original v3 oracle/golden tests.
- New progression tests cover supply/customer forecasts, committed ingredients,
  overlapping orders, capacity rejection, release/replacement, cooldown saving,
  actual specialty output, regular-customer demand, permanent recipe speed,
  material value, the retail licence route and concurrent one-time fulfillment.
- Browser interaction checks cover commitment/release, reload persistence,
  specialties, cooldown feedback, all four art variants and removal of the slider.
- Eight viewport sizes, 72 panel views and 21 pagination steps pass the fit check.
- The original ready-order reaction and existing page-purpose checks are retained.

Run against an isolated preview:

```sh
python3 previews/day3_preview.py 3005
.venv/bin/python -m pytest tests -q
node tests/ui_progression.cjs http://127.0.0.1:3005
node tests/ui_viewport.cjs http://127.0.0.1:3005
node tests/ui_page_purposes.cjs http://127.0.0.1:3005
node tests/ui_order_reaction.cjs http://127.0.0.1:3005
python3 tests/sim_production.py --days 7 --output previews/progression-balance.json
```

## Seven-day balance check

The recorded run uses ten minutes initially, then five-minute visits every two
hours (every twelve hours for casual). The delivery strategy now uses bounded
order commitments. These bots neither choose specialties nor complete the
Breakfast Club event, and their policies are not optimal strategies.

| Strategy | Day 7 businesses | Cash YM | Materials | Completed deliveries |
|---|---:|---:|---:|---:|
| Upgrades | 10 | 546,576 | 0 | 4 |
| Expansion | 11 | 3,672,673 | 0 | 22 |
| Deliveries | 10 | 1,143,280 | 307 | 481 |
| Casual | 10 | 6,575,250 | 0 | 25 |

[Full results and source hashes](progression-balance.json). The earlier
`production-balance.md` records the pre-revision rules and is historical.
481 deliveries is an intensive bot workload, not a recommended player quota.

For the first human playtest, check whether players understand an upgrade before
buying it, can commit an order without leaving Market, notice the exterior change,
and can explain their specialty's tradeoff. On return the next day, check whether
the persistent breakfast rewards are remembered and useful. Keep those observations
separate from simulation evidence.

## Existing saves

The pre-change backup is under `backups/meaningful-progression-20260912-171016/`.
Money, goods, ownership, current offer IDs and earned materials are retained.
Existing offers honor their listed reward; replacement creates the new types.
Previously completed Breakfast Club events gain their chosen recipe perk without
receiving a second material reward. Older manually held businesses stay held until
released in Warehouse. The fixed material value replaces the old building-dependent
saving for both old and newly earned units.
