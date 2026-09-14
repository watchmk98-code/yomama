# Economy choices playtest — 14 September 2026

**Historical results:** this study predates independent production. Automatic
ingredient consumption and supplier reservations have since been removed.
Its supply-chain findings and numeric comparisons describe the earlier rules;
they are not balance validation for the current independent-production model.

The three sales channels support different goals. The strongest demonstrated
choices are choosing a buyer roster, accepting or refusing larger shipments,
and pausing buyers for a material goal. The main design concern is how quickly
free offer searching removes stock mismatch and increases payment per unit.
No game parameters, player saves, or live service settings were changed.

**What was tested.** 91 recurring-buyer scenarios, 108 active-play scenarios,
and 18,000 actual offer replacement actions. These are scripted simulations of
the current engine and isolated three-card prototype, not human playtesting.
The regular-buyer study includes a six-hour warmup sensitivity check. Active
policies use three seeds; offer sampling uses five seeds.

Towns have 1, 3, or 6 owned businesses with their recipes unlocked. They start
with empty inventory, normal shelves, walk-in sales enabled, no staff or quest
speed bonuses, and ample cash to isolate operating behavior. Production and
customer levels are controlled scenarios, not purchased progression. Operating
cash includes real costs, but excludes setup costs and unsold inventory value.

**The roles survive the tests.**

| Mechanism | Useful purpose | Meaningful cost |
| --- | --- | --- |
| Walk-ins | Automatically sell uncommitted output at retail | Demand can leave output unsold; inventory spent here cannot fill orders |
| Regular buyers | Sell predictable quantities with little attention | Lower prices, priority stock, and possible diversion of crafting inputs |
| Manual orders | Convert selected goods into chosen cash/material rewards | Visits, actions, stock allocation, and delivery time on the first card |

Regulars do not universally dominate passive income. At production/customer
level 1, representative farm, three-business, and six-business rosters improve
net operating cash. After a six-hour warmup, their advantages are approximately
27%, 16%, and 10%. When Customers reaches level 3 while production stays at 1,
the same rosters instead reduce net operating cash by about 6%, 6%, and 3%:
walk-ins can now absorb more output at full price. This is a useful reason to
reconsider a commitment as a town develops.

Roster choice affects what the town makes. In the three-business scenario,
pastry production is 60/hour without regulars, 25/hour with tomato/egg/honey
buyers, and zero after enlarging those ingredient contracts. The finished-goods
roster preserves 60 pastries/hour. Larger shipments also become late when
production cannot meet their schedule. They are consequential choices.

**Pausing for a goal works without requiring constant toggling.** Both policies
below prioritize the sector card until reaching the same benchmark of 10
materials, then return to ordinary order selection. Only one pauses buyers
while pursuing the goal. Results are means of three seeds, six businesses,
production/customer level 1, over a measured hour after a 10-minute warmup.

| Material-goal policy | Time to 10 materials | Regular shipments/hour | Buyer pause/resume actions |
| --- | ---: | ---: | ---: |
| Keep buyers active | 10.25 min | 44 | 0 |
| Pause until the goal is met, then resume | 6.58 min | 37.3 | 8 |

This benchmark represents a reason to gather materials, not a simulated building
purchase. In the higher-production six-business scenario, keeping buyers active
reaches the goal sooner than pausing: the spare capacity makes pausing
unnecessary. That is an earned reduction in scarcity, not automatically a flaw.

A separate cash-oriented policy that pauses/resumes around blocked individual
orders performs about 189 buyer actions/hour in the base six-business case,
reduces regular shipments to 12.7/hour, and earns only about 0.8% more net cash
than the goal-pause policy. It also earns more materials, so this is an
attention/output trade-off, not proof of strict dominance. Repeated toggling is
not needed to make the goal-pause strategy useful in these runs.

**Extra clicking is not uniformly better, but rarity searching is powerful.**
The active study allows a visit every 30 seconds, at most one delivery/start per
visit, and either no rerolls or up to five rerolls while retaining one saved
job. These policies accept a usable offer; they do not deliberately hunt rarity.

| Town at base levels, no regulars | Patient orders: net cash / actions | Up to five refreshes: net cash / actions |
| --- | ---: | ---: |
| Farm | 2,013 / 50 | 1,808 / 492 |
| Three businesses | 4,899 / 41 | 4,874 / 438 |
| Six businesses | 17,327 / 42 | 21,819 / 385 |

The six-business refresh policy also earns 66 materials versus 40. It offers
more output at much higher attention cost. This does not make automation
pointless, and frequent refreshing does not help the small towns in these runs.

The separate offer study freezes naturally earned stock after an hour of
production. It samples candidates without delivering or consuming goods:

| Six-business card | One candidate immediately fits | A match among ten candidates | Cash/retail among matching single candidates | Best matching cash/retail among fifty candidates |
| --- | ---: | ---: | ---: | ---: |
| Timed delivery | 57.7% | 100% | 1.36× | 2.47× |
| Sector | 61.0% | 100% | 1.28× | 2.28× |
| Original | 32.2% | 99.8% | 1.27× | 1.74× |

These are observed, overlapping candidate windows, not independent probability
estimates or repeated-delivery income forecasts. Materials are separate from
the cash ratios. Nevertheless, finding a suitable order quickly becomes easy,
and further searching buys a substantial premium for the same unit of stock.
That is the clearest pressure toward repetitive clicking.

Artificially filling every shelf makes all generated offers fit. It raises the
benefit of searching further, but should not be described as the natural town
state. Natural towns still had scarce crafted goods. Only 22.7% of timed
jackpots fit the natural six-business stock; their multi-product requirements
still impose a real constraint. Original-card jackpot quantities were all
clipped to shelf capacity, which softens their quantity challenge in a fully
stocked town.

**The three manual cards need a narrower follow-up.** The material card has a
clear purpose. The timed card is used frequently in the active simulations;
its goods occupy storage until arrival, so waiting has a real cost. The original
instant card is selected only about 2–3 times/hour by the base six-business
cash-oriented policies, versus 16–64 timed starts. The policies favor reachable
jobs, so this is a reason to test that card's distinct usefulness with people,
not proof that it should be removed. This study does not isolate the ideal
timed payout or duration from the cards' different quantities and products.

**Recommendation.** Keep the three income channels, regular priority and the
discount, and free CLICK!!!!. Before tuning every building, test a smaller
rarity premium per unit against the current version. Preserve exciting large
total rewards through substantial deliveries, and measure whether preparing
stock becomes more worthwhile relative to searching. Give the original card
a focused human test: can players explain when they prefer its immediate
payout? No additional currencies, screens, or restrictions are justified by
these findings yet.

Human testing remains necessary for perceived enjoyment, clarity, and tolerance
for clicking. The bots are bounded strategies, not optimal players. Buyer modes
have different warmup stock; goal-pause comparisons use matched sector-goal
preferences and the same buyer warmup. Readiness checks inside reroll loops are
not comparable as per-visit probabilities. Storage-blocked ticks describe any
blocked shelf, not necessarily the income lost specifically to a shipment.

**Reproduction and checks.**

```sh
.venv/bin/python previews/playtest_regular_buyers.py
.venv/bin/python previews/playtest_economy_choices.py
.venv/bin/python previews/playtest_order_refreshes.py
```

Detailed results are written under `.checks/economy-playtest/`. The scripts
assert cash and goods conservation, no payment for refreshing or signing,
and correct delayed payments. All 18 paused-roster cases exactly match their
walk-in baseline. The existing full suite passes: 603 tests; all six game
JavaScript syntax checks pass. Any future game balance release needs Manual
Deploy; this work has changed only playtest scripts and this report.
