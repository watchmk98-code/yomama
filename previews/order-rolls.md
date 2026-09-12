# Free, repeatable order rolls

New Order has no cost or cooldown. Rapid clicks queue behind the current request,
then use each newly returned order ID. Failed requests clear the local queue;
successful rerolls release that offer's committed goods. Nothing is earned just
by rolling an offer.

| Roll | Chance | Distinct products | Quantity factor | Cash premium factor |
|---|---:|---:|---:|---:|
| Standard | 65% | Usual 1–2 | 1× | 1× |
| Large | 25% | Up to 3 | 1.5× | 1.3× |
| Rare | 8% | Up to 4 | 2× | 1.75× |
| Jackpot | 2% | Up to 5 | 2.5× | 2.5× |

The cash premium factor multiplies that slot's usual percentage of retail value,
after valuing all requested quantities. Thus a Quick Cash jackpot pays about
3.13× retail value (125% × 2.5, rounded to an integer percentage). Supply orders
also retain material rewards proportional to their goods; Breakfast Regulars
still progress their customer relationship only on delivery.

Orders use distinct eligible products and never request more of a product than
its shelf can hold. Early towns with fewer products get fewer distinct requests.
More advanced towns can receive orders spanning several businesses and recipes.
Stored goods are consumed only on successful fulfillment; missing even one item
rejects the whole action. Each fulfilled ID pays once.

Standard/large/rare/jackpot colors and a payout multiplier make bigger rolls
recognizable. Ingredient lists paginate inside the card if needed. Rerolling
resets that list to its first page. The pixel crying face flashes whenever a
successful replacement skips a ready order, including offers skipped by queued
spam clicks. It does not delay rerolls or charge a penalty.

Existing orders retain their requirements and rewards until replaced or fulfilled.
Old saved cooldown timestamps are ignored. Rarity and product selection use an
independent hash of the saved player seed, order serial and board slot, so timing
or reloading does not change the sequence.

## Verification

- A 10,000-offer deterministic sample checks rarity distribution, distinct goods,
  shelf limits, product counts and payout formulas.
- Tests cover unlimited same-tick replacement, old cooldown saves, replay,
  reservations released on reroll, and jackpot payouts exactly once.
- Browser tests hold a response, click six times, and verify six sequential
  requests with the latest order ID. Five-product jackpot cards are checked at
  1366×768, 1728×694, 390×844 and 844×390.
- Full current Python suite: 86 passed. Existing interaction, ready-order reaction
  and eight-viewport tests also pass.

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
