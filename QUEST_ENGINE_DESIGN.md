# Quest engine decisions

Design record, 16 September 2026. **Implemented and tested, and off.** The
engine ships switched off: nothing calls `quest_engine.configure()` outside the
tests, so `questEngine` is absent from every class config and every code path
below returns the old answer. The 30 business quests in
`business_progression.py`, existing saves, Prestige balances, recipe perks and
rewards are unchanged until a class is opted in.

## Decisions taken

- One system. The engine replaces the business-quest system rather than sitting
  beside it. `business_progression.py` keeps the five functions the rest of the
  tree imports; its quest content, objectives, rewards and claim flow retire.
- Fresh content. The 30 two-per-business quests are retired rather than
  re-expressed. Their ids are not preserved. Three things currently depend on
  those ids and are re-pointed instead; see "What retiring the 30 breaks".
- Quests appear at the bottom of the Build page, in their own front-end module,
  not inside `econ.js`.
- Boosts are charge-based, never wall-clock. "Double payout on your next 10
  sales", not "double payout for 30 minutes".
- Quests unlock from progression only. There is no teacher-pushed quest and no
  `source` field for one.
- No quest awards Prestige or Know-how. The user is designing the focus tree
  and will place Prestige with it.
- Quests do not feed the leaderboard. Scoring is a separate later design.

## What the engine replaces, and what it must keep

`business_progression` is imported in about twenty-five places across
`production_economy.py`, `workforce.py`, `business_operations.py` and
`crafting_pilot.py`. Nearly all of them want one of five things, and all five
stay where they are:

| Kept | Used by |
| --- | --- |
| `product_unlocked(cfg, st, gid)` | recipe availability, order generation, production |
| `speed_bonus(cfg, st, b, good)` | production rate |
| `prestige` / `knowHow` / `prestigeEarned` balances | focus tree, expansion qualification |
| `expansion_requirements` / `consume_expansion` | opening a new business |
| `record_production` / `record_sale` | the counter bus |

The engine owns what those functions *report*, not the functions themselves.
`product_unlocked` consults the engine's unlocked list; `speed_bonus` reads
perks the engine granted; the Prestige balances stay in
`st['businessProgression']` so the focus tree and the three Prestige-gated
expansions keep working untouched.

The counter bus needs no new call sites in the production hot loop.
`record_production` and `record_sale` are already called from the five places
that settle goods (`production_economy.py` lines 464, 496, 645, 916, 1130);
they forward to the engine when it is enabled.

## What retiring the 30 breaks

Three systems currently reference quest ids directly. Each is re-pointed, and
none of the three requires those ids to be quest ids at all.

1. **Advanced focus nodes.** `workforce.py:205` requires
   `<businessId>-signature` to be completed before an advanced node can be
   bought. Replaced by a named flag: the engine grants
   `business_developed:<businessId>`, and workforce reads the flag. This
   decouples workforce from quest identity permanently.
2. **Craft item unlocks.** `config/crafting-pilot.v1.json` gates items on
   `unlock.questIds`, currently `fish_stall-plan`. Re-pointed to the new quest
   ids as part of the same change. The pilot's `_achievements` reader needs no
   change; it reads completed quest keys whatever they are called.
3. **Signature recipes.** Twelve of the fifteen businesses produce their third
   good only once a quest unlocks it (`product_unlocked`). The fresh set must
   therefore carry twelve `unlock_recipe` rewards, or those goods can never be
   made. This is a hard requirement on the content, not an option.

Eight craft items gate on old quest ids today. Their re-pointing is fully
determined except for one:

| `crafting-pilot` gate | becomes |
| --- | --- |
| `fish_stall-plan` | `harbour-lunch` |
| `roastery-plan` | `cafe-opening` |
| `workshop-plan` | `develop:workshop` |
| `garage-plan` | `develop:garage` |
| `cannery-plan` | `develop:cannery` |
| `garage-signature` | **undecided** |

`garage-plan` and `garage-signature` were two gates of different difficulty and
both map onto the single `develop:garage` quest, which would quietly make the
Electric Cargo Tricycle as cheap to reach as the Battery Pack. It needs its own
target picked from the chapter quests instead.

## Prestige is deferred

The user is designing the focus tree separately and will place Prestige with
it. No quest in this design awards Prestige or Know-how, and `prestige` is not
a reward type until that design lands.

One consequence follows and is accepted. Prestige currently gates two things:
focus-node prices, and the expansion qualification for the turbine field,
relay station and solar array (lifetime 6, 10 and 14). With no Prestige
source, an engine-enabled class sets `prestigeExpansion: false` and
`prestigeCostsEnabled: false`, so both gates are simply off until the focus
tree is designed. Legacy classes keep both, because they keep the old quests
that feed them.

The numbers are recorded here so the later design starts from them: the focus
tree costs 135 Prestige to buy out (15 businesses x 7 nodes priced 0/1/2), and
the old quest set supplied 30.

## The quest record

One quest is one JSON record in `config/quests.v1.json`. Everything that is not
in this shape is engine behaviour, not content.

```json
{
  "id": "first-harvest",
  "chapter": 1,
  "title": "First Harvest",
  "summary": "Sell ten tomatoes to the neighbourhood.",
  "teaches": "Goods need shelf space before they can be produced.",
  "appear":     { "afterQuests": [], "ownsBusiness": "farm", "minBuildings": 0 },
  "objectives": [ { "kind": "count", "counter": "sell:farm_tomatoes", "target": 10,
                    "label": "Sell 10 tomatoes" } ],
  "rewards":    [ { "type": "cash", "amount": 40 },
                  { "type": "boost", "metric": "sale_payout", "multiplier": 2, "charges": 10 } ]
}
```

A quest moves `hidden → available → tracking → ready → done`. Objectives track
automatically from real activity; the player presses Claim. Manual claim is
kept deliberately: it makes reward grants idempotent, and the child sees what
they earned instead of a number changing silently.

Twelve of the fifteen businesses need the same quest: run the ordinary line,
earn the advanced recipe. Writing that out twelve times would be twelve
near-identical records, so one **template** with `forEachBusiness: true`
instantiates per owned business, resolving `{businessId}`, `{good1..3}` and
their names from the tier table. The farm, fish stall and roastery are skipped:
they keep their opening recipes from the start.

Templates carry no special behaviour. They expand to ordinary quest records
before anything else looks at them.

## Objectives

Two kinds, because two are genuinely needed.

**Counters** are monotonic and incremented by events:

- `produce:<goodId>`, `produce:business:<businessId>`, `produce:any`
- `sell:<goodId>`, `sell:business:<businessId>`, `sell:any`
- `sell:source:<orders|walkIns|regularBuyers|clearance>`
- `deliver:order` — one completed manual order
- `act:<verb>` — `open_business`, `upgrade`, `focus_node`, `accept_contract`,
  `set_regular`, `port_trade`, `quiz_pass`

**State checks** are evaluated when the payload is read, not accumulated:

- `own:businesses`, `level:<businessId>`, `unlocked:<goodId>`
- `businesses_at_level` — how many businesses have reached a given level

The `act:` verbs are the only new instrumentation: roughly eight one-line calls
in `production_economy.py`, `workforce.py` and the port module. Every teaching
quest is content once they exist, which is the whole reason to add them.

Counters are recorded from adoption of the engine onward. No historical
activity is invented, matching the rule already set in `SYSTEM_ROLES.md`.
Claiming recognises activity; it never debits stock a second time.

## Rewards

Typed, granted once, recorded in the save. Every type either reuses a mechanism
that already exists or is listed as new work.

| Type | Effect | Mechanism |
| --- | --- | --- |
| `cash` | plain payment | existing |
| `supplies` | random basic-supply pack | reuses `crafting_pilot._award` |
| `speed_perk` | +n% base speed on one recipe | existing `speed_bonus` path |
| `unlock_recipe` | a business's advanced product | existing `product_unlocked` path |
| `unlock_craft` | one craft-pilot item | writes the pilot's unlocked map |
| `grant_building` | a fully funded business | reuses `town_projects.construction_grant` |
| `upgrade_voucher` | pays up to N YM toward one upgrade | **new** |
| `boost` | charge-based multiplier | **new** |
| `flag` | named achievement other systems read | **new** |
| `unlock_feature` | a page or panel | **new** |

No reward grants Prestige or Know-how; see "Prestige is deferred".

`upgrade_voucher` is a capped payment rather than a free level on purpose.
Upgrade cost scales at `growth: 1.55`, so a free level at tier 12 is worth
thousands of times one at tier 1. A voucher is stable across the whole curve
and teaches budgeting rather than handing out a jackpot.

## Boosts

```json
{ "type": "boost", "metric": "order_payout", "multiplier": 2, "charges": 10 }
```

**One metric, `order_payout`.** The design began with three - adding
`sale_payout` and `production_output` - and implementation killed two of them.
Walk-in retail settles per good per tick inside the production loop, so a
charge spent there would be gone within seconds of being granted, without a
single decision behind it. A reward the player cannot aim is not a reward. An
order delivery is the opposite: one visible payout, at a moment the player
chose, on goods they chose to make. All six boosts in the content now multiply
order payouts, and the player picks which order to spend each charge on.

- A charge is consumed only when it multiplies a non-zero payout.
- One active boost per metric; a second grant queues behind the first rather
  than compounding, so multipliers never stack into a jackpot.
- Charges are consumed during offline catch-up and `admin.py advance --play`,
  because in both cases the town really did deliver. This is what wall-clock
  timers cannot do: a boost cannot be farmed by granting it before a time jump,
  and cannot be wasted by sleeping.
- Displayed as "x2 order payout - 7 left".

If a timer is ever wanted, it is spent in game-seconds of processed production,
never wall-clock seconds.

## The fresh quest set

Drafted in [config/quests.v1.json](config/quests.v1.json): **22 hand-written
chapter quests plus 12 template instances, 34 in total**, against the real
economy numbers (start cash 0, the farm free, the fish stall 110, the roastery
650, goods priced 2 through 760, farm upgrades 24/37/58/89).

- **Chapter 1, Open for business (6).** Sell a tomato, buy an upgrade, learn
  that honey is worth four times a tomato, fill three order cards. Ends with
  the fish stall and then the roastery funded outright.
- **Chapter 2, Supply chain (6).** Four businesses at once, regular buyers
  before an absence, contracts as promises, the first crafted product, one
  business supplying another, and clearance as a real channel.
- **Chapter 3, Scale (5).** Depth over width (three businesses at level 5),
  focus advancements, 200 units sold, Operations unlocked at six businesses,
  advanced products for margin.
- **Chapter 4, Conglomerate (5).** Eight businesses, the power grid, fifty
  orders unlocking the Port, twelve businesses, and Telemetry at 760 YM as the
  closing note against the tomato at 2.

Each quest carries a `teaches` line naming the one idea it exists to convey.
Where a quest teaches nothing new, it says so.

Chapter 1 hands out the fish stall and the roastery, which the three opening
projects in `town_projects.py` currently grant. Both systems cannot grant the
same building, so an engine-enabled class runs the opening sequence off and
Chapter 1 carries the grants instead. Legacy classes are untouched.

Quest count is now content. Adding a quest is an edit to one JSON file.

## Files, state and route

Built:

- `quest_engine.py` - `configure / enabled / ensure / record_* / payload / act`,
  plus the read side other systems call (`product_unlocked`, `speed_bonus`,
  `has_flag`, `has_feature`, `building_grant`, `apply_boost`, `apply_voucher`).
  It validates every claim against a deep copy and commits only on success, so
  a refused claim grants and spends nothing.
- `config/quests.v1.json` - the content and the `enabled` flag.
- `quests.js` + `quests.css` - loaded by `buildings.html`, rendering into
  `#econ-quests` below `#econ-building`. It reads the snapshot `econ.js`
  already polls (`window.YomamaEcon.state()`) and issues **no requests of its
  own** except a claim, so a thirty-seat class adds no polling load.
- `tests/test_quest_engine.py` (18) and `tests/test_quest_engine_integration.py` (8).

Save state is one additive key:

```
st['questEngine'] = { version, counters{}, completed{}, boosts[], vouchers[],
                      flags[], unlockedRecipes[], perks{}, features[],
                      grants[], recent[], sequence }
```

Route `POST /api/game/quests` -> `game_api.econ_quests`, in the `_class_locked`
tuple and `server.GAME_POST_ROUTES`.

`previews/quests_preview.py PORT` serves a disposable town with the engine on,
its opening quests claimed through the real claim path, live boosts and several
quests ready; `--fresh` starts at First Crop with nothing earned.

Touched on the game side, each minimally:

| File | Change |
| --- | --- |
| `business_progression.py` | forwards the counter bus; delegates `product_unlocked` and adds engine perks to `speed_bonus` |
| `production_economy.py` | `quests=` in the payload; order/upgrade/expand observation; quest building grants join the construction-grant path; the upgrade voucher; the order-payout boost |
| `workforce.py` | advanced focus nodes read the `business_developed:` flag instead of a quest id; focus purchases are observed |
| `game_api.py`, `server.py` | the route |
| `buildings.html` | the panel, its stylesheet and its script |

`econ.js` was not touched. Its `questsPanel` still renders the legacy quests
for legacy classes, which is correct: the two systems never run in one class.

## Migration and release

Behind `cfg['questEngine']['enabled']` in the class-stamped configuration
snapshot, the same way `businessDesign.enabled` was introduced.

Because the flag lives in the snapshot, retiring the 30 quests does **not**
force a reset of the live classes. YSNRD and F2XHJ keep the legacy quests,
their completed records, Prestige, recipe perks and focus qualification until
they are reset; they simply never see the engine. New classes get the engine
and never see the legacy quests. No class runs both.

An engine class also runs with `townProjects` opening sequence off,
`prestigeExpansion: false` and `prestigeCostsEnabled: false`, for the
reasons given above. None of the three affects a legacy class.

Schema is additive: one new state key, no new columns, no change to any
existing key. The site needs Manual Deploy, between play sessions. Pushing
alone does not deploy.

## What remains

The engine is built, wired and green: 1391 tests pass, `node --check` passes on
every script CI checks plus `quests.js`, and everything compiles on 3.9 as well
as 3.13. Verified end to end against the real economy - real production and
walk-in sales reach the counters, a claim pays from the player's own cash, a
granted building makes the real expansion quote cost 0 while still booking its
full value, and a voucher pays a real upgrade without touching cash.

To switch it on for a class: call `quest_engine.configure(cfg)` where the class
config is loaded, then `admin.py reset CODE --yes` so the class re-stamps its
rules. An engine class must also run with the `townProjects` opening sequence
off and `prestigeExpansion` / `prestigeCostsEnabled` false, for the reasons in
their sections above. **Needs Manual Deploy**; pushing alone does not deploy.

Still open, all of it tuning rather than mechanism:

- Chapters 3 and 4 targets, voucher amounts and boost sizes are estimates. The
  cash curve past six businesses has not been measured, so they should be set
  from an `advance --play` run rather than from judgement.
- `garage-signature` needs a new gate target, per the table above.
- Both feature locks are wired. **Port**: `game_api._port_request` adds the
  quest feature to the licence check it already ran, so an engine class needs
  the Network Effect quest and a class without the engine is gated exactly as
  before. **Operations**: `operations-lock.js` was a hardcoded
  `LOCKED = true`; it now opens the page once the player holds the
  `operations` feature, and falls back to that testing lock unchanged whenever
  the engine is off. The Operations lock is presentational, as it always was -
  the API enforces its own rules.
- Two Chapter 2 quests originally asked for "accept a contract" and "set up a
  regular buyer", which turned out to be the same action: `accept_contract` is
  an alias for fulfilling an order, and the game's contracts *are* its regular
  buyers. The second quest now asks for the distinct decision the game really
  teaches - growing a regular who has taken three deliveries into its larger
  order. A test asserts that every counter the content asks for is one the
  engine actually records, so this class of mistake cannot come back.
- The circular-unlock rule in `SYSTEM_ROLES.md` holds by construction for the
  template set; the chapter quests still want one read-through.
