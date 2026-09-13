# Free, repeatable order rolls

New Order has no cost or cooldown. Rapid clicks queue behind the current request,
then use each newly returned order ID. Failed requests clear the local queue;
successful rerolls release that offer's committed goods. Nothing is earned just
by rolling an offer.

| Roll | Chance | Distinct products | Quantity factor | Cash premium factor |
|---|---:|---:|---:|---:|
| Standard | 65% | 1 for cash; up to 2 for supplies/regulars | 1× | 1× |
| Large | 25% | Up to 3 | 1.5× | 1.3× |
| Rare | 8% | Up to 4 | 2× | 1.75× |
| Jackpot | 2% | Up to 5 | 2.5× | 2.5× |

The cash premium factor multiplies that slot's usual percentage of retail value,
after valuing all requested quantities. Thus a Quick Cash jackpot pays about
3.13× retail value (125% × 2.5, rounded to an integer percentage). Supply orders
also retain material rewards proportional to their goods; Breakfast Regulars
still progress their customer relationship only on delivery.

Orders now draw complete named jobs from the [delivery recipe catalog](../DELIVERY_RECIPES.md).
Each has a specific purpose and a distinct combination of products. Larger rolls
choose a larger authored bundle; they never add unrelated products to a small job.
If a town cannot yet supply that many products coherently, the roll uses the
largest eligible recipe below its target size and keeps its rarity premium.
Every product's full supply chain must be owned. A bundle never pairs a finished
product with its own ingredients, so saving the order cannot hold back those
ingredients from making the same order's finished goods. Quantities remain
bounded by each product's shelf capacity.

Cash and building-supply jobs span the town's industries. Breakfast Regulars
draw only food jobs and retain their three-delivery roastery demand bonus.
Each slot remembers which recipes it has shown, deals unseen eligible recipes
of the rolled size first, and then returns to the least recently shown jobs.
Among unseen jobs it prefers recipes not already displayed on the board, while
still allowing every recipe to be reached when other cards are left parked.
Stored goods are consumed only on successful fulfillment; missing even one item
rejects the whole action. Each fulfilled ID pays once.

Standard/large/rare/jackpot colors and a payout multiplier make bigger rolls
recognizable. Every ingredient stays visible inside the card; text, icons and
spacing adapt to fit, with shorter lists returning to the current maximum size.
No ingredient arrows are needed. The pixel crying face flashes whenever a
successful replacement skips a ready order, including offers skipped by queued
spam clicks. It does not delay rerolls or charge a penalty.

Existing orders retain their requirements and rewards until replaced or fulfilled.
Old saved cooldown timestamps are ignored. Rarity and recipe selection use an
independent hash of the saved player seed, order serial and board slot plus saved
recipe history, so timing or reloading does not change the sequence.
The catalog ships with the engine and uses each class's existing configuration
for quantities and supply chains. Existing v4 saves gain empty recipe histories
in place and start drawing the catalog when offers are replaced or fulfilled;
no class reset is needed. Release to the live site needs Manual Deploy.

## Verification

- A 10,000-offer deterministic sample checks rarity distribution, distinct goods,
  shelf limits, product counts and payout formulas.
- Tests cover unlimited same-tick replacement, old cooldown saves, replay,
  reservations released on reroll, and jackpot payouts exactly once.
- Browser tests hold a response, click six times, and verify six sequential
  requests with the latest order ID. Five-product jackpot cards are checked at
  1366×768, 1728×694, 390×844 and 844×390.
- Full Python suite after named recipes: 205 passed. The new recipe-card check
  and general viewport check pass at eight sizes; the rapid-order queue check
  also passes. Recipe tests cover all 185 jobs, saved rotation, old towns without
  food businesses, and production followed by atomic delivery.

```sh
.venv/bin/python -m pytest tests -q
node tests/ui_order_rolls.cjs http://127.0.0.1:3006
node tests/ui_viewport.cjs http://127.0.0.1:3006
```

[Desktop example](jackpot-order-1366.png) · [Mobile example](jackpot-order-390.png)

The updated [seven-day simulation](order-roll-balance.json) exercises the normal
upgrade, expansion, delivery and casual policies. Those bots do not hunt for
jackpots, so their results do not measure the advantage of repeated rerolling or
prove balance for that strategy.
