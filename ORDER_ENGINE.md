# Three Market cards

Each of the three existing cards has one fixed role.

| Card | Behavior |
| --- | --- |
| **1. Delivery orders** | Start a delivery, reserve its goods, and receive payment when it arrives. Show the delivery time inside this card. |
| **2. Sector orders** | Each new order automatically chooses Food, Industry, or Energy/Tech from the sectors the town can supply. All requested products belong to that sector. |
| **3. Current orders** | Keep the existing third card's orders, rewards, and actions. |

Keep the current Market layout, controls, emoji actions, and reaction animations.
The sector card needs only a sector label; it does not need a sector selector.
The delivery card shows a countdown while the shipment is in progress.

## Delivery time

Delivery time grows with the **cash payout**, including any rarity bonus. The
initial curve uses a 30-second minimum and scales gently for bigger orders:

| Payout | Delivery time |
| --- | --- |
| 75 YM | 30 seconds |
| 300 YM | 1 minute |
| 1,200 YM | 2 minutes |
| 4,800 YM | 4 minutes |

The exact duration appears on **Start delivery** before the player commits.
Internally it is `max(30, 60 × sqrt(payout / 300))` seconds, rounded up to a game
tick. Nearby payouts can share a duration because game ticks are 15 seconds.
These values are an initial balance proposal, with no maximum-time cap.

The player presses **Start delivery** when the goods are available. Those goods are reserved
for the shipment and cannot be sold, crafted with, or used by another order.
The card shows **Delivering**, **Arrives in**, and the payment due on arrival.

Payment, completed-delivery statistics, and quest/project progress are awarded
once, on arrival. The next order then appears immediately. Before starting,
replacing an offer stays instant and saving/releasing goods works as before.
During delivery, the shipment cannot be replaced, released, or started again.
The other two cards remain available throughout.

The timer uses the saved game clock, rounded up to whole game ticks. Pausing the
class stops it. Reloading preserves the shipment and its remaining time. Existing
save and skip emojis stay the same; the delivery emoji plays when payment arrives.
The duration is saved with each offer and remains fixed during delivery, including
older shipments already in progress. Each new offer receives a fresh quote.

## Sector behavior

The next sector is selected automatically. When more than one sector can supply
an order, prefer a different sector from the previous one. A town with only Food
businesses receives Food orders.

Requested products must share a sector and belong to owned businesses with the
products unlocked. Each product is made independently, so no supplier chain is
required. Requests fit the relevant shelves.

Current quantities, rarity rules, and per-card cash/material rewards remain the
basis for the prototype. Regular buyers pay 90% of the full bundle's normal
shop payout, rounded to whole YM, including larger shipments. These are
take-home amounts after selling charges, with production costs paid separately.
The Build operating statement separately shows gross customer sales and their
operating expenses. Reward amounts and their comparisons retain the same
take-home basis. Their next shipment
gets stock before saved manual orders, explicit equipment crafting, and walk-ins.
Only the requested shipment goods are reserved; there are no automatic recipe
inputs or ingredient buffers.
Pausing or releasing a buyer frees that reservation. Already dispatched goods
remain with their shipment and cannot be recalled by a newly signed buyer.

This regular-buyer change is in the shared economy engine. Existing contracts
reprice in place when loaded, preserving cash, history, quantities and schedules;
no class reset is needed. Publishing it still needs Manual Deploy.

## Order sizes and bonuses

The existing badge now has six possible labels. Small and Bulk add different
stock choices without adding another card, button, timer, or currency.

| Label | Chance | Request | Cash price per item |
| --- | --- | --- | --- |
| Standard | 40% | Normal quantities; usual bundle for this card | Normal order price |
| Small order | 15% | One product, half the normal quantity | Normal order price |
| Bulk order | 10% | One product, three times the normal quantity | 90% of the normal order price |
| Large order | 25% | Up to three products, 1.5 times normal quantities | 130% of the normal order price |
| Rare order | 8% | Up to four products, twice normal quantities | 175% of the normal order price |
| Jackpot order | 2% | Up to five products, 2.5 times normal quantities | 250% of the normal order price |

Small orders use a little spare stock; Bulk orders move a lot of one product
but pay less per item. Quantities round up to whole goods and fit each shelf.
Only unlocked products from owned businesses qualify. The sector card still awards
materials from the retail value delivered. Timed orders still quote travel
time from the cash payout, so a Small order also has a smaller payment and
usually a shorter trip than a larger shipment of the same product.

Both the normal generator and isolated sector prototype read the same roll
table. The API supplies current odds for the CLICK!!!! tooltip. Old offered,
saved, and dispatched orders keep their exact terms; only newly generated
offers use the new table. No class reset is needed. Needs Manual Deploy.

## Prototype status

`order_engine.py` exercises these three cards on an isolated copy of an economy
state. It supports delivery, replacement, saving/releasing goods, automatic
sector selection, and saved shipments. The third card delegates its existing
actions to the current economy engine and preserves an already-saved offer.

This prototype is **not connected to the live Market**. A separate browser
preview uses the current Market page and emoji actions with these card rules.
It does not change current classes or their saved rules. Future live integration
needs Manual Deploy; saved shipment defaults will also need an explicit migration.

Run an in-memory preview:

```sh
.venv/bin/python previews/order_classes_preview.py --buildings 6 --seed 7
.venv/bin/python previews/order_classes_preview.py --demo --output .checks/order-class-examples.json
.venv/bin/python -m pytest tests/test_order_engine.py -q
```

The preview grants an established sample town in memory and never opens a game
database. `--demo` shows dispatch, payment on arrival, and automatic sector changes.

For an interactive browser preview with a separate temporary database:

```sh
.venv/bin/python previews/order_cards_browser.py 3018
```

Open `http://127.0.0.1:3018/marketplace.html`. Its sample town has six businesses
and stocked shelves so deliveries and emoji reactions can be tried immediately.
Only this local preview serves the countdown renderer and uses the new order
actions. The normal server and real saves are unaffected.
