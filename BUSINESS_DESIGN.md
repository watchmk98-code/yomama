# Business economy

> For `businessDesign.connectedProgression` classes, [SYSTEM_ROLES.md](SYSTEM_ROLES.md) supersedes the practice-quest, equipment-gate and recipe-unlock descriptions below. Quests observe real production/sales, the first quest unlocks advanced recipes, equipment is inactive, and Prestige is spent on focus advancements. Legacy class snapshots preserve their original rules.

The new rules use `businessDesign.enabled` in the version 4 class configuration.
Buildings produce goods; walk-ins, regular customers and completed orders sell
those goods for cash. Orders, crafting and regular shipments share inventory.

## Player screens

- **Build:** business artwork, sales/cost/profit estimates, stock, upgrades and
  expansion. Selecting a business shows its quests and existing projects.
  Locked stock stays visible in grey, with a link to the required quest.
  Global costs have a dedicated red tile beside sales. Estimates respond to upgrades;
  actual cash changes only when production expenses or transactions occur.
- **Market:** orders and recurring customers. One-off order rewards remain
  separate from ongoing income estimates.
- **Operations:** Recipes, Team and Quests tabs for the selected business.
  Research and equipment open in their own panel.

## Production and staff

Every completed batch pays its configured operating cost before its ingredients
are consumed. A blocked or paused batch costs nothing. The starter tomato crop
costs nothing to produce, providing a recovery path from an empty wallet.
There are no idle fees or involuntary overdrafts.

Each customer upgrade adds 10% of the base batch cost; each warehouse upgrade
adds 5%. These additions accumulate from level 1, before permanent crew efficiency discounts.
Upgrade previews show the business's estimated cost and profit change. Fractional
costs carry forward between batches, including after saving and loading.

Current rules replace temporary shifts with permanent trainers and one shared
workforce per business. Recruitment charges once, funds a finite roster and
has a 30-minute class-clock cooldown. Trainers develop workers; Advanced HQ
can develop additional trainers. Workers are assigned to production, customers
or efficiency through each business's focus tree. The full rules, limits,
snapshot compatibility and validation are in [WORKFORCE_DESIGN.md](WORKFORCE_DESIGN.md).

Business pauses and skipped offline production preserve training progress.
Teacher pauses stop the class clock. Ingredients, storage, operating costs and
customer demand continue to limit the value of hiring.

## Quests, research and equipment

Each of the 15 building types has two finite quests. Planning quests balance
two products against limited supplies and work time. Signature quests make
components before finished goods, with a choice of careful or bulk batching.
Practice can be reset before completion without spending town resources.

Each first completion grants 1 Know-how, 1 Prestige and a permanent selected
product improvement. Know-how buys research; Prestige qualifies the town for
later construction and is not spent. Wind Turbines require 6 Prestige, Relay
Station requires 10, and Solar Array requires 14. These milestones are shown
in the existing growth panel. Food, Industry and Energy/Tech each have two research steps.
The final product at each of the later 12 businesses requires its signature
quest. All products at the first three businesses remain available for the
opening projects. The original Breakfast Club also qualifies for the roastery
signature quest after its planning quest.

Six later buildings require relevant crafted equipment and research. Crafting
uses available town goods and respects delivery reservations. Held equipment
retains its component value in net worth; construction transfers that value
into the building, without treating it as refundable cash spending.

Construction requirements open their relevant research branch, equipment kit,
or business quests directly. A locked kit links to its required research.
The quest chooser keeps each business's dedicated quests together and lets the
player choose another owned business when earning Know-how or Prestige.

## Pause and closure

Pausing is free. Permanent closure returns 45% of recorded eligible cash spent
on construction and upgrades and starts a 300-second rebuild cooldown for that
building type. Grants, equipment value and consumed resources do not increase
the cash refund. The starter farm is protected.

Closure requires empty shelves, finished construction,
and released orders or regular contracts using the business's goods. The
review shows the refund and affected supply chains. Learned products, research
and completed quests survive closure. Rebuilding creates a new instance ID so
a stale browser action cannot affect the replacement business.

## Local previews and rollout

```
.venv/bin/python previews/business_design_preview.py 3011
.venv/bin/python previews/business_design_preview.py 3012 --all-buildings
```

Both previews bind to localhost and use temporary databases. The second grants
a sample town for exploring all 15 businesses; it is not a balance simulation.

Existing classes without the flag retain their saved rules. New classes receive
the new configuration. Existing opted-in saves receive defaults without wiping
their towns; already owned products are grandfathered once. Unknown historical
construction spending is never invented to calculate refunds.

Prestige construction requirements additionally use `businessDesign.prestigeExpansion`.
New configurations enable it; older class snapshots without it keep their previous
construction rules. Existing ownership and earned Prestige are preserved.

Publishing these changes **needs Manual Deploy**. Existing live classes need an
explicit class reset after deployment to adopt the new configuration. Deploying
or running a reset is separate from creating and testing these changes.
