# Automatic crafting trial

Implemented trial, 16 September 2026. The authoritative trial rules are in
[config/crafting-pilot.v1.json](../config/crafting-pilot.v1.json). They cover 15
products and 10 business assets. The default economy configuration is unchanged.

## Production and sales

Every unlocked, eligible trial product runs automatically. Players do not select
an active recipe or press a manual batch button. Each finished batch consumes
its full recipe and its processing cash charge together. Missing supplies, held
goods, insufficient cash, a closed business or a missing required asset prevent
that batch. Existing ordinary business production remains independent.

Each processed tick permits at most one completed batch per product. Work is
capped at one batch, so a shortage cannot accumulate an unlimited backlog.
Priority rotates to the product following the last successful producer, avoiding
catalog-position bias when multiple ready products compete for a scarce input.
Committed orders and regular customers retain their reserved ordinary stock.

Crafted goods have separate storage and customer demand. Demand cannot accumulate
unlimited sales while shelves are empty. Business Pause stops production and
sales; the existing stock-hold control stops sales. Stock already made can still
sell after a required production asset expires. Cash is credited only when a
buyer takes an actual unit.

Rechargeable Battery Packs are the only intermediate crafted product in this
trial. Each scooter or cargo tricycle consumes two packs, replacing its former
six loose battery cells. The pack's own ingredients are not charged twice.
Eligible downstream products reserve one batch of packs before pack retail; both
vehicle lines together reserve four packs. Other products have no imposed craft
chain. The seven-business preview includes Machine Works as the scooter's CNC
parts supplier.

## Product tuning

All values below are YM. Batch seconds and processing charges are the unmodified
recipe values. Production levels and applicable assets modify the actual timing
or charge; ordinary Customers and Storage levels also affect craft demand and
capacity. Stock capacity is six units per product, or three for each vehicle,
before modifiers. Default sale intervals equal the listed batch intervals.

Unlocks require the listed cash payment and every listed milestone. Order counts
refer to completed manual orders involving that product's business; two goods
from the same business in one order count once. Quests and focus nodes are real
business progression, not consumable ingredients.

| Product | Producer | Unlock cash | Other unlock milestones | Required asset | Batch seconds | Processing | Sale price |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| Farm Breakfast Basket | Farm | 100 | 1 order | None | 120 | 2 | 40 |
| Seafood Picnic Box | Fish Stall | 150 | 2 orders | Refrigerated display | 150 | 3 | 50 |
| Smoked Fish Gift Box | Fish Stall | 250 | Plan quest; 3 orders | Refrigerated display | 180 | 4 | 134 |
| Coffee Gift Set | Roastery | 180 | 2 orders | None | 150 | 3 | 73 |
| Honey-Glazed Pastries | Roastery | 240 | Plan quest; Sales focus; 2 orders | None | 120 | 3 | 147 |
| Wooden Storage Crate | Ironworks | 200 | 1 order | None | 120 | 2 | 64 |
| Seedling Tray | Ironworks | 300 | Production focus; 2 orders | Metal press | 150 | 3 | 51 |
| Portable Toolbox | Ironworks | 450 | Plan quest; 3 orders | Metal press | 180 | 4 | 99 |
| Wheeled Market Cart | Ironworks | 600 | Plan quest; Production focus; 4 orders | Welding equipment | 240 | 5 | 199 |
| Rechargeable Battery Pack | Garage | 450 | Production focus; 2 orders | Diagnostics | 180 | 5 | 148 |
| Folding Electric Scooter | Garage | 1,800 | Plan quest; Production focus; 5 orders | Diagnostics | 600 | 25 | 1,058 |
| Electric Cargo Tricycle | Garage | 2,800 | Signature quest; Advanced Production focus; 8 orders | Diagnostics | 900 | 40 | 1,192 |
| Tomato Chutney | Cannery | 400 | Plan quest; 2 orders | Sterilisation and preservation licence | 180 | 5 | 127 |
| Honey Spread Jars | Cannery | 450 | Plan quest; Efficiency focus; 3 orders | Sterilisation and preservation licence | 180 | 5 | 164 |
| Pantry Hamper | Cannery | 300 | 2 orders | None | 240 | 4 | 199 |

The two jar recipes use purchased food-safe containers in the trial. Their legacy
manual recipes remain unchanged outside the trial. The original 300 item IDs and
64 supply IDs are preserved; only these 15 items switch to automatic production.

## Assets and useful life

An asset must be owned and assigned to its compatible live business instance.
Either equipment slot accepts a tangible asset; the third slot accepts an
intangible. One copy of each asset type can be owned, and the same copy cannot
occupy two slots. Rebuilding a business does not silently inherit an old
assignment.

Both tangible and intangible assets last 7 days of processed, assigned, active business time.
Storage, business Pause and skipped offline time do
not age them. Book value decreases linearly with that used life. Expired assets
have zero productive effect and can be replaced at the listed acquisition price.
Recipe prerequisites check the specific asset, regardless of which compatible
equipment slot holds it.

These trial benefits apply to the listed crafted products. They do not yet
activate the broader base-product effects proposed in the full design catalog.
Same-stat percentages add against the base value; processing discounts are capped
at 40%. Discounts affect processing cash, not ingredient quantities or the price
paid for basic supplies.

| Asset | Price | Life | Trial effect and affected products | Acquisition value |
| --- | ---: | --- | --- | --- |
| Farm crop-management software | 40 | 7 d | Processing cost −10%: breakfast basket | Optional efficiency investment |
| Fish refrigerated display | 250 | 7 d | Storage +50%: both fish products | Required to produce both fish products |
| Fish ice-making machine | 200 | 7 d | Processing cost −15%: both fish products | Optional efficiency investment |
| Roastery exclusive blend licence | 400 | 7 d | Sale price +10%: coffee gift set | Optional price premium |
| Ironworks metal press | 600 | 7 d | Production speed +15%: seedling tray and toolbox | Required to produce those two products |
| Ironworks welding equipment | 700 | 7 d | Production speed +15%: market cart | Required to produce the cart |
| Garage diagnostics | 800 | 7 d | Processing cost −15%: packs, scooters and tricycles | Required to produce all three |
| Cannery automated canning line | 650 | 7 d | Production speed +15%: chutney and honey jars | Optional capacity investment; see demand condition below |
| Cannery sterilisation equipment | 500 | 7 d | Production speed +10%: chutney and honey jars | Required to produce both |
| Cannery preservation licence | 750 | 7 d | Processing cost −15%: chutney and honey jars | Required to produce both |

Optional-asset checks assume continuous operation, sufficient materials and
buyers, level-one production, and no other modifier. Actual payback changes with
those conditions:

- Farm software saves 6 YM per hour. The price was
  reduced from 180 to 40; continuous-operation payback is about 6.7 hours.
- The ice machine saves 10.8 per hour on picnic boxes and 12 on smoked boxes.
  Both lines repay its 200 price in about 8.8 hours; either line alone can repay
  it within 7 days.
- The blend licence raises a 73 YM gift-set sale to 80 after integer rounding.
  At 24 sales per hour, its 168 additional hourly receipts repay 400 in about
  2.4 hours.
- The optional canning line does not create buyers. At Customers level 1,
  ordinary demand is already the bottleneck; the required steriliser also
  supplies enough speed for Customers level 2. Customers level 3 or higher is
  where its extra speed can improve sustained sales, subject to inputs. It can
  also replenish depleted stock faster. The acquisition UI states this condition.

Required assets have the additional value of permitting a new product line.
Their price is not justified solely by the displayed stat percentage. In
particular, the preservation licence saves 30 YM per hour in processing
with both lines at their base rate; its 750 price also buys the right to
make those higher-value products. Asset acquisition is capital spending, not an
immediate second processing expense on every unit.

## Supply rewards

Supplies are still bought manually. Rewards contain basic supplies only: never
crafted products or business assets. Selection does not depend on owned
businesses. Each pack draws up to three distinct affordable supply types, with
one to five units per type; the total recorded purchase value never exceeds its
budget. Expensive supplies outside the remaining budget are not selected.

| Trigger | Maximum pack value |
| --- | ---: |
| A newly completed quest | 120 |
| A newly completed focus node | 80 |
| Every third completed manual order | 80 |
| A visit after four hours of class game time since that player's prior visit | 300 |

Existing completed quests and focus nodes become the migration baseline and are
not paid retroactively. Repeated polling, observing the same achievement, or
removing and restoring an already rewarded focus cannot replay the reward.
Another player's activity does not count as this player's visit. The welcome
pack is awarded once per qualifying return, not every poll after a long absence.

## Accounting and validation

Stored supplies and crafted goods retain their transferred book value. Creating
a product moves ingredient value and the actual processing cash charge into
that product; the expected selling markup is not booked as new wealth. Asset
purchases likewise move cash into asset book value. Unlock payments are spent.

An independent cost ledger carries actual ingredient cost into each finished
unit. Sales release that cost as cost of goods sold. Business and town operating
statements include actual crafted sales, matched cost, depreciation and
amortization once; repeated payload reads do not duplicate results. A short
reporting window can contain a sale or depreciation charge unevenly, so its
instantaneous margin is not a fixed promise.

The 15 individual real-tick sale simulations conservatively value ordinary
ingredients at their normal sale value and intermediate packs at their own sale
price. All 15 sell for real cash and show margins from **31.16% to 32.50%** before
asset wear. That measures the premium over an alternative use of the ingredients.
Recorded accounting margins can be higher because self-produced ingredients
often cost much less cash than their sale value. The recipe's reference-value
margin and the actual sold-goods statement therefore answer different
questions; neither should be presented as a guaranteed investment return.

The seven-business, all-15-lines one-hour simulation also ran through the real
economy tick loop with finite supplies and no automatic purchases. It made 224
craft units, sold 199, received 29,946 YM in craft sales and matched 9,062 YM of
recorded ingredient/processing cost. Its roughly 69.7% recorded craft margin
reflects that lower actual input cost. Ordinary business receipts are separate
from those craft-sales figures.

Reproducible invariant and individual balance checks:

```sh
.venv/bin/python -m pytest tests/test_crafting_pilot.py tests/test_crafting_rewards.py -q
```

Coverage includes atomic shortages, reserved order goods, scarce-input fairness,
pack consumption, request replay, stale revisions, assignment compatibility,
pause/expiry/rebuild behavior, useful life across the offline cap, legacy stock
migration, real sales, cost conservation, bounded basic-supply rewards, and
reporting without double counting.

## Running the trial and class snapshots

```sh
python3 previews/crafting_pilot_preview.py 3011
python3 previews/crafting_pilot_preview.py 3011 --fresh
```

Choose an unused local port. The preview uses `preview_support` and a disposable
database. It explicitly writes the full trial rules into the SOLO session's
`econ_config`; the SOLO helper otherwise creates an ordinary-rules snapshot.
The normal showcase starts with seven supplied businesses, three products
unlocked, two acquired/assigned assets and completed prerequisites for the other
12 products. `--fresh` keeps the supplied businesses but leaves milestones,
unlocks and assets blank. Neither mode changes the real local save.

`crafting_pilot.configure(cfg)` opts a configuration into the trial by copying
the complete JSON rules under `cfg.craftingPilot`. Loading the ordinary economy
configuration does not enable it. Existing classes retain their own rule
snapshots, so merely shipping the new code does not change their crafting rules.
An explicit class-snapshot opt-in is needed to activate the trial for such a
class. State migration preserves current supplies, crafted ownership, IDs,
recorded value and request history while adding the pilot fields and missing
cost-basis metadata. A destructive class reset is not inherently required for
those additive fields.

The preview is local. Shipping the code to the live site still needs **Manual
Deploy** between classes, followed by an explicit decision about which class
snapshots should opt in. Auto-deploy remains off.
