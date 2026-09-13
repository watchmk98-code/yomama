# Opening, income and system purposes

> The fixed-project sequence documented below describes legacy class snapshots. New classes with `businessDesign.connectedProgression` use three active order containers, separate group-project tracking and real business quests. See [SYSTEM_ROLES.md](SYSTEM_ROLES.md) for the current rules and deployment/reset behavior. The historical pacing results below do not measure the connected version.

Implemented 2026-09-13. These rules are in the game engine; no economy configuration version bump or class reset is required. Existing access, seats, authentication and class clocks are preserved.

## What each system does

| System | Player decision | Purpose and reward |
| --- | --- | --- |
| Walk-in customers | Increase customer capacity when spare supply supports it | Automatic cash from remaining shop stock |
| Regular buyers | Choose a limited roster, supply whole shipments, adjust size or pause | Repeat cash payments; shipments can run while away and wait without a late fee |
| Quick cash deliveries | Save and deliver a requested bundle | One-time cash; free rarity rolls remain |
| Building supplies deliveries | Trade a bundle for cash and materials | Materials reduce future construction costs; free rarity rolls remain |
| Town projects | Complete three fixed, bounded deliveries | First two construction grants, then permanent café reputation |
| Breakfast Club | Plan batches and choose a recipe upgrade after opening the roastery | A permanent improvement to that recipe’s base production speed, plus five materials once |

Town projects replace the repeating Breakfast regulars channel. Breakfast Club remains a separate, optional recipe workshop; regular buyers remain recurring logistics. No new general-purpose currency was added. Construction grants are specific entitlements that cash upgrades cannot spend.

## A playable opening

1. The farm produces and walk-in customers buy automatically. Build displays the next town project, while upgrade previews explain whether they improve estimated ongoing income or only add stock.
2. In Market, the first card is **Feed the neighborhood**. Save and deliver six tomatoes. Other goods keep selling. The reward includes a fully funded fish stall and 15 YM.
3. Build the fish stall with its grant. Construction uses neither cash nor owned materials. The next project stays locked until construction completes.
4. Save and deliver two smoked fish and four oysters for **Serve the harbor lunch**. The reward includes a fully funded roastery and 55 YM.
5. Build the roastery with its grant. The farm now supplies the pastry recipe; Operations explains the ingredients. Breakfast Club becomes available.
6. Save and deliver four espresso and two pastries for **Open the neighborhood cafe**. Earn 85 YM and a permanent 20% increase in roastery walk-in customer demand.
7. The project card becomes a completed summary after the two ordinary job cards, so finished goals do not obstruct ongoing play. Further growth comes from improving supply and demand, choosing regular buyers, making ordinary deliveries, and expanding with cash/materials. The workshop is an optional production improvement, with its own supplies and practice coins.

The displayed quantities and cash rewards above describe the default configuration. The module resolves businesses by ID against the class’s saved configuration.

Projects have no rarity rolls, expiry, penalties or repeatable completion rewards. Ordinary delivery rolls and their existing reactions continue in the other two slots. All financial actions remain server-authoritative.

## Protecting progression from upgrade spending

A construction grant pays the whole construction quote, including any material shortfall. It cannot buy upgrades, be exchanged for cash, or fund another business. Existing materials stay in inventory. Grants are consumed once, after frontier and queue validation succeed. A rejected purchase leaves the grant available.

Players can still buy an early business normally. Already owned or queued buildings satisfy their corresponding opening milestone without refunds or duplicate grants. The engine refreshes an obsolete project card and releases only that project’s reservation.

The Build goal names the next action: save project goods, resolve a conflicting reservation, deliver, build with the grant, or wait for construction. Market’s locked project links back to Build. The completed project’s reward appears in its transaction feedback.

Optional orders can compete with projects. The UI identifies a saved order sharing the project’s goods or ingredients and explains that releasing it speeds the project. If combined commitments exceed shelf capacity, the project Save button explains the restriction. It never silently cancels the player’s other orders.

## Honest income feedback

The large shop figure is actual operating cash received in the last 60 seconds: walk-ins plus regular buyers. Its two sources are shown directly below it. The accompanying estimate includes sustainable regular shipments and the walk-in supply remaining afterward. Regular buyers pay in batches, so a quiet minute does not imply that their contract stopped earning.

A bundle spanning multiple shops allocates its whole-YM payment by the delivered goods’ retail values, with deterministic rounding. Shop operating receipts reconcile exactly with the town total. Upstream ingredients are not counted again.

One-time deliveries and stock clearance are separate receipt sources; purchases are not income. Grants and workshop supplies are not cash receipts. The dashboard labels its daily forecast as an estimate.

Forecasts consider recipe inputs, whole-bundle bottlenecks, regular-buyer slot priority and paused contracts. Current inventory, finite saved orders, full shelves and discrete arrival timing can change actual results. Forecasts never credit cash. On migration, an empty observation window is shown rather than inventing past payments.

## Existing saves

- Cash, inventory, ownership, materials, seats and earned recipe benefits survive.
- Previously earned Breakfast regulars progress counts toward the finite projects. The earned 20% demand benefit survives.
- A saved pre-project third-slot delivery retains its terms until fulfilled or explicitly replaced; its next card follows the new project sequence.
- Existing or queued opening businesses earn no refund or duplicate grant.
- Started or completed Breakfast Club events remain accessible even if their town lacks a roastery. New events require completed roastery ownership.
- JSON migration and repeated claims are idempotent. Offline income limits continue to apply; skipped time clears stale receipt windows.

Deploy between classes with **Manual Deploy**. These engine changes migrate existing v4 towns in place; no class reset is needed.

## Verification and practical limits

The full Python suite passes: **260 tests**, including real SQLite transactions, simultaneous delivery/build claims, existing access contracts, migration, regular-buyer accounting, and JSON/offline replay. Browser checks cover the new actions, income attribution, protected grants, workshop access and rewards, and desktop/mobile/landscape layouts. The general viewport suite covers eight sizes and every reachable panel/page.

In 80 engine simulations, with one goal action per minute across 20 seeds and four policies, all three projects completed at minute 14. Policies were: no upgrades, buying every affordable upgrade first, signing two regular buyers early, and combining buyers with aggressive upgrades. The normal trace opened the fish stall at 4.25 minutes and the roastery at 11.25 minutes. Upgrade policies made 12–14 purchases without delaying either construction reward.

Parking optional jobs first extended simulated completion to 15–26 minutes. These runs deliberately left the competing reservations in place; the resulting conflict now has explicit guidance. The 14-minute result is a reproducible pacing check, not evidence that every human player will follow that timing or enjoy the game. Observe a first-time class to test whether students can explain what to do next and why each system is useful.

Detailed pacing data and UI evidence are in the local ignored `.checks/purpose-fixes/` directory. Tests live in `tests/test_earnings.py`, `tests/test_town_projects.py`, `tests/test_opening_sequence.py`, `tests/test_breakfast_workshop.py` and `tests/ui_purpose_fixes.cjs`.
