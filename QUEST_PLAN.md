# Quest content plan v2 — from progress bars to decisions

Plan, 16 September 2026. **Implemented 17 September 2026** — see the
"What shipped" section at the end for what the numbers changed. Follows [QUEST_ENGINE_DESIGN.md](QUEST_ENGINE_DESIGN.md),
which describes the engine as built and switched off.

## The problem being fixed

28 of the 34 shipped quests are a lifetime counter that only goes up, and the
counters that matter — sales — rise on their own from walk-in customers. So the
only verb the content can express is "accumulate", and the player's role is to
wait. Six quests ask for an action; the rest are progress bars.

The fix is not more quests. It is more *kinds* of objective, and a reason to
make a choice.

## Decisions taken

Approved: profit-margin and income-rate objectives; choice rewards, balanced;
a crafting chapter; an operating-margins chapter; pause/salvage; quiz/licence;
repeatable dailies with scaling targets.

Rejected: deadline quests ("deliver 5 orders before the next game day"),
anti-clearance quests ("sell 50 without one going to clearance") and
anti-overflow quests ("a full game day with nothing overflowing").

Dropped on the numbers: **"Lean — cut operating cost below sales"**. Measured on
a six-business town, operating cost runs 37 YM/min against 249 YM/min of sales.
Costs are already a seventh of sales, so the quest would complete the moment it
appeared. The user's doubt was right.

## What the numbers say

Measured on a level-1 six-business town, 700 ticks:

| Figure | Value | What it means for content |
| --- | ---: | --- |
| Town profit margin | **13.4%** | a 30% target is a real stretch, not a gift |
| Gross sales | 266,372 | |
| Selling costs | 222,807 | **84% of gross** — the biggest lever in the game |
| Take-home | 43,565 | 16% of gross |
| Operating cost | 37 YM/min | vs 249 YM/min sales; not a constraint |

Selling costs eating 84% of gross is the single most interesting fact in this
economy and no quest mentions it. The margins chapter below is built on it.

Before release, one calibration run must confirm 30% town margin is reachable
at all through upgrades, focus and assets. If it is not, the target moves; the
quest does not get deleted.

## Phase 1 — engine primitives

Three additions to `quest_engine.py`. Everything in phases 2-4 is content once
these exist.

**1. Live-number state checks.** New `state` checks read from the economy
rather than from counters, so they cannot be idled into:

- `income:perMinute` — town income per minute
- `margin:town` — town profit margin, from `operating_margins.town_statement`
- `margin:business` — best single business, via `operating_margins.statement`
- `netWorth`, `cash`

`quest_engine` cannot import `production_economy` at module scope without a
cycle; it does the lazy import inside the check, as `crafting_pilot` already
does in `record_order`.

**2. Start-scoped counters.** `st['questEngine']['scopes'][questId]` snapshots
the counters a quest watches when it becomes visible; an objective marked
`"scoped": true` measures the delta. Needed only by the dailies in phase 4 —
the rejected deadline quests were its other use — but without it a daily can
never reset.

**3. Choice rewards.** A quest may carry `choices` instead of `rewards`:

```json
"choices": [
  { "id": "cash",  "label": "5,000 YM now",              "rewards": [ … ] },
  { "id": "boost", "label": "x3 order payout, 10 uses",  "rewards": [ … ] },
  { "id": "perk",  "label": "+10% Pastries speed, forever", "rewards": [ … ] }
]
```

`quest_claim` takes a `choiceId`; the engine grants that branch only, records
which was taken, and refuses an unknown or absent choice. The old system's
`quest_plan` action and its `choices` UI are the precedent.

New verbs to record at their call sites: `act:craft_unlock`, `act:buy_asset`,
`act:assign_asset`, `act:pause_business`, `act:salvage_business`,
`act:quiz_pass`. New state check `licence:open`, reading `economy.gate_open`.

## Phase 2 — balanced choice rewards

Balance rule, so the three options are a real decision rather than an obvious
pick. Each chapter defines one **unit**, roughly what that stage earns in ten
minutes. The three branches are then:

| Branch | Worth | Shape |
| --- | --- | --- |
| Cash | 1.0 unit | all of it now, no conditions |
| Boost | ~1.2 units | only if the charges get spent on real orders |
| Permanent perk | ~0.6 unit now | overtakes 1.0 after roughly 20 more minutes of play |

The cash is safest, the boost pays most but only to a player who delivers, and
the perk wins for anyone who keeps playing. There is no dominant option, which
is the whole lesson: opportunity cost. A child who is about to stop for the day
should rationally take the cash, and that is a correct answer, not a mistake.

Retrofit choices onto the six chapter-closing quests rather than all of them —
a choice on every quest turns into noise.

## Phase 3 — new chapters

**Crafting (5 quests).** The 15 items, 10 assets and assignment slots currently
have two unlock rewards between them.

- Unlock your first crafted product.
- Buy a business asset, then assign it to the business that uses it.
- Craft an item whose ingredient your own business produced.
- Sell a crafted item for more than 3x the value of its inputs.
- Have three products crafting automatically at once.

**Margins and costs (5 quests).** Built on the 84% figure.

- **In the Black** — reach 30% town profit margin. *(approved)*
- **A Thousand a Minute** — reach 1,000 YM/min income. *(approved)*
- Where does the money go — reach 25% take-home of gross sales.
- Own an asset long enough to see its depreciation reported.
- Run one business whose profit beats every other business you own.

**Pause and salvage (2 quests).** Closing a business is a real decision and
nothing currently asks for one.

- Pause a business that is losing money, and resume it once it is not.
- Salvage a business and reinvest the proceeds into another.

**Quiz and licence (2 quests).** `economy.gate_open` already requires three
buildings, production level 3, a sales upgrade, three deliveries and the quiz.

- Pass the quiz.
- Earn your licence (the whole gate).

## Phase 4 — repeatable dailies

```json
"repeat": { "every": "day", "scale": 1.25, "maxOutstanding": 1 }
```

A game day is 1,440 game-minutes. On each day boundary the quest re-arms, its
target multiplies by `scale`, and its reward scales with it. Objectives are
`scoped`, so each day measures only that day's activity.

Three or four to start: a sales target, an order-delivery target, a production
target. Deliberately not a login streak — the game is played irregularly and a
streak punishes the child who was busy.

`maxOutstanding: 1` matters. A player away four days, or a class moved by
`admin.py advance --play`, must come back to one daily waiting, not four
stacked rewards. The target is a delta of activity counters rather than of
elapsed time, so a time jump that really did produce the activity completes it
honestly; only the reward stacking needs the cap.

## Order of work

1. Phase 1 primitives with tests — nothing else can be built first.
2. Phase 2 choice rewards on six existing quests. Smallest visible change.
3. Margins chapter — needs only the live-number checks from phase 1.
4. Crafting chapter — needs the new verbs recorded in `crafting_pilot`.
5. Pause/salvage and quiz/licence — small, independent, can slot anywhere.
6. Dailies last: they need scoped counters and the most balancing care.

Ships in the same shape as the engine: behind `questEngine.enabled`, additive
state only, off by default, **needs Manual Deploy**.

## Open questions

- Is 30% town margin reachable? One calibration run decides the number.
- Dailies need a reward size that is worth returning for without making the
  chapters pointless. This is the balancing risk in the whole plan.
- The 12 `develop:` template quests stay as they are. They are the most
  repetitive content in the set, and making each business ask for something of
  its own is a bigger content job than anything above.

## What shipped, 17 September 2026

All four phases. The content went from 34 quests to **51** in ten named groups,
and the engine gained four primitives. Everything is still behind
`questEngine.enabled` and still off by default.

### The calibration changed the margins chapter

The plan asked for a 30% town margin and 25% take-home. Measuring first showed
both were impossible, and for a reason worth recording:

| Portfolio | Town margin | Take-home | Best business |
| --- | ---: | ---: | ---: |
| Low-margin sectors, level 1 | 11.6% | 14.1% | 15.0% |
| Low-margin sectors, level 6 | 9.7% | 14.1% | 12.5% |
| High-margin sectors, level 1 | 21.1% | 25.8% | 23.0% |
| High-margin sectors, level 6 | 17.7% | 25.8% | 19.2% |
| Mixed eight, level 6 | 14.4% | 21.0% | 17.5% |

`operatingMargins.targets` designs each business between 6% (farm) and 23%
(solar array), so a 30% town margin cannot exist. Worse, **upgrading lowers
margin** — more sales at the same unit economics plus more operating cost.

So the chapter now teaches what the data actually says: margin comes from
*which industries you are in*, not from upgrading harder. Targets are 16% town
margin, 18% for one business, 20% take-home — each reachable only by leaning
into the high-margin sectors, and none reachable by a low-margin portfolio.
Three tests pin this: the targets must be reachable in a strong town, and a
low-margin town must fall short, or the lesson has no teeth.

`margin:business` was also silently broken — it called `operating_margins
.statement` without its rate tables and an `except` swallowed the error, so it
always returned 0. It now reads `_recent_sales`, the same matched-sales basis
the shop panel shows.

### Also dropped or changed

- **Lean** is gone. Operating cost runs 37 YM/min against 249 YM/min of sales,
  so "cut operating cost below sales" was already true.
- The three rejected quest shapes (deadlines, anti-clearance, anti-overflow)
  were never written.
- Finished chapters collapse to one line in the UI. At 51 quests a flat list is
  a wall; a completed chapter should fold away, not take a full row of dimmed
  cards.
