# System roles — conglomerate progression

These roles record the user's direction on 13 September 2026. They supersede the proposed direction in `CONNECTED_GAME_IMPLEMENTATION_PLAN.md`, which the user set aside. The connected quest, group-project and Prestige rules below are implemented for configurations with `businessDesign.connectedProgression: true`. The default config enables them; existing classes retain their saved rules.

The game is persistent. Children play whenever they want; there is no assumed classroom play duration. The user is defining costs and constraints incrementally. Unspecified numbers below are not defaults to invent.

The player runs a **conglomerate**, a group of owned businesses. This replaces the town-building framing in the intended design. Business quests develop individual businesses; **group projects** combine businesses into larger achievements for the conglomerate. The existing shared cash/inventory model does not imply separate company wallets or new internal-transfer fees. Any such economic changes require their own design decision.

## User-defined roles

| System | Intended purpose | Resource relationship |
| --- | --- | --- |
| Walk-in customers | Automatic shoppers paying retail prices. | Consume available business goods and return retail cash. |
| Regular buyers | Players set them up before a long absence, such as sleep, to boost earnings. They need a cooldown that creates a reason to return and set them up again. | Use the conglomerate's real production/inventory; duration, cooldown semantics and payout are still to be specified. |
| Three order containers | Intentional active clicker gameplay and an opportunity to understand supply and demand. | Players deliver requested real goods for rewards. All three containers belong to this active loop. |
| Recipes | Unlock advanced products for their dedicated businesses so players can earn more. | Recipe access determines what a business can produce; production uses that recipe's real ingredient requirements and operating rules. |
| Equipment | No functional use yet. | Crafting and equipment construction requirements are inactive under connected rules. Previously crafted quantities and asset value remain intact. |
| Business quests | Develop one business: introduce its products, qualify recipe unlocks, and recognize actual production and sales. | Each business has two one-time quests. Each completed quest earns 1 Know-how and 1 Prestige, plus its chosen product improvement. |
| Group projects | Develop the conglomerate through connected suppliers and product deliveries. | The three existing opening achievements now observe ordinary orders, outside the three containers. Their original goods targets, cash bonuses and construction grants/customer perk remain. |
| Worker population | A visible count of ordinary employees, arriving automatically through business growth. | No gameplay purpose yet, by explicit user instruction. No assignments, costs, staffing requirements or bonuses. Separate from HQ specialists. |

Do not apply the previous recommendations to remove the clicker emphasis, limit order rerolls, add contract penalties, introduce shared recipe scheduling, or make equipment a central progression requirement without a new decision from the user.

## Connected progression

- Quest 1 requires actual production and sales of the first two products. Its quantities reuse the previous everyday-product plan targets. It unlocks the third product's recipe at the later twelve businesses.
- Quest 2 requires producing and selling two units of that third product. The first three businesses retain their opening recipes from the start.
- Walk-ins, regular shipments, orders and clearance count as sales. Production inputs are consumed by recipes; they are not customer sales. Stock snapshots and forecasts do not create progress. Activity counts from adoption of connected rules, including work done before choosing a quest perk.
- Quest claims recognize activity; they do not consume inventory again. Each ordinary order settles its own goods and cash once, then can advance a quest and the current group project. Project claims pay the existing milestone bonus once, without another stock debit.
- All three order containers reroll and deliver ordinary product orders. Group projects are visible in Build and Operations, with the contributing suppliers shown.

## Approved Prestige costs

Each of the 30 business quests awards **1 Prestige once**. Focus induction costs no Prestige or cash, subject to its existing qualification. Basic focus advancements cost **1 Prestige**; advanced advancements cost **2 Prestige**. Both retain their existing YM prices and prerequisites. Available Prestige is shared across the conglomerate, so spending on one business reduces the balance available to the others.

`prestige` is the available balance; `prestigeEarned` records lifetime earnings. Expansion qualifications use lifetime earnings so focus spending cannot remove an earned qualification. Existing focus nodes retain their effects without retroactive charges. Know-how remains the research currency.

## Approved connection between business quests and group projects

The user approved business quests as individual-business development and projects as development across businesses, with a conglomerate framing. Observe actual production and order deliveries where possible. Group projects should have separate tracking so the three order containers can all serve their intended active-clicker role.

The opening sequence recognizes farm deliveries, processed seafood deliveries, then espresso and pastry deliveries. The farm supplies eggs and honey for pastries; the roastery processes beans into espresso. The final project shows both supplying businesses and preserves the permanent 20% roastery walk-in demand benefit. The first two projects preserve the fully funded fish-stall and roastery construction grants.

Use business development, product lines, supply chains and group expansion in future project framing. Existing neighborhood customer names may still describe buyers; they do not make the player a town mayor. Internal identifiers such as `town_projects.py` remain implementation details until a scoped migration/refactor is undertaken.

Avoid a circular unlock: a quest must not require a product whose recipe can only be unlocked by completing that same quest. An earlier objective can unlock a recipe; a later objective can demonstrate the advanced product.

## Worker population — purpose deferred

The user chose growth-driven worker arrivals, then explicitly deferred all worker purposes. The current population is display-only, with adjustable starting arrivals of 5 per first business opening and 1 per new highest production level, capped at 20 per type. The earlier sector labor-intensity request is retained as future design intent, with no active requirements. See [WORKFORCE_DESIGN.md](WORKFORCE_DESIGN.md).

## Next unresolved regular-buyer decision

Define whether activation starts a limited run, when cooldown starts, and when the next run becomes available. Also define the run duration and earning benefit. A cooldown on changing an otherwise permanent buyer does not by itself create a periodic setup-before-leaving activity.

Regular buyers still continue indefinitely under their existing interval, pause and offline rules. Their periodic activation/cooldown lifecycle remains to be specified. Order price balancing, additional recipe-unlock fees, longer quest targets and projects beyond the opening sequence remain design work; this implementation does not assign those new costs or durations.

## Saves and release

The new flag lives in the class configuration snapshot. Existing classes without it keep legacy practice quests, fixed projects, equipment and cash-only focus costs. New classes use the connected rules after release. Existing classes need an explicit reset to adopt the default config; no reset has been performed.

If a save explicitly adopts connected rules in place, earned quests, recipe perks, construction grants, focus nodes and equipment value survive. Started legacy practice quests retain their accepted terms. A saved fixed-project delivery is moved outside the three containers, keeps its original goods/reward and can settle once. Its reservation is retained. No historical production or sales are invented.

The site **needs Manual Deploy**, between play sessions. Pushing alone does not deploy.
