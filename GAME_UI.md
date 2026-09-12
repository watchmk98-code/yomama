# YoMama game interface

The management pages share Dash's black surfaces, thin amber borders, terminal
font and supplied pixel art. Green means readiness or progress. The top-level
section is Game; Build is its business-management screen.

| Page | Purpose |
| --- | --- |
| Dash | Business overview and class standings |
| Build | Selected business, goods, quick upgrades, construction, and events |
| Warehouse | Inventory, capacity, and holding goods |
| Market | Orders, customer prices/upgrades, and surplus sales |
| Operations | Raw output, recipes, and production upgrades |
| Licence | Milestones, quiz, and the separate practice portfolio |

## Build reference layout

The user explicitly prefers the earlier three-column Build layout: building
list left, selected building and goods center, upgrades/construction right,
and four stats above. Do not replace it with the town tile gallery. Build has
quick management controls; the detailed pages retain their specialized layouts.

General orders and their quantity-specific reservation controls belong to Market, not Build. Warehouse retains a manual sales pause.
There is no general Orders button or popup on Build. Breakfast Club is a
separate event, accessed from the bottom container.

Selecting the next business updates a greyed-out image beside the construction
controls. The image uses the selected frontier ID and existing art. Grayscale
applies to the image, never to a grey panel background. Actual construction
costs, ingredients, stock, timers and permissions remain server-owned.

## Screen fit

`game-fit.js` makes the five management pages fill the available viewport.
Desktop panels stretch to the bottom. Buildings, recipes, inventories, orders,
and milestones use explicit pagination when their content exceeds available
room. Controls must not be clipped merely to hide scrollbars.

Below 900px width or at most 650px height, view tabs switch between panels. A compact
navigation select and business selector preserve access without long lists.
Short landscape layouts reserve the Build summary/event for its Building view
and use the other views for goods, upgrades and construction. Orders remain on
Market. All panel/tab/page selections survive economy refreshes. Business
selection also persists across navigation in the browser session.

Inventory rows show actual item counts, reserved quantities and capacity bars.
Market displays real prices and delivery requirements. Surplus sales protect
recipe supplies but can sell held stock; the relevant sale note says so.
Operations shows both raw goods and recipe dependencies. Licence removes passed
quiz cards and locked investment placeholders, with every milestone reachable
through its pager. No fake data, filler paragraphs, or repeated order cards.

## Market feedback

Market gives a brief pixel-art crying-face reaction on an order card when the player
successfully replaces an order that was fulfillable or a jackpot when its request
was sent, including orders skipped by queued spam clicks. Saving a jackpot with
Save for this order shows a green pixel dollar sign using the same reaction;
releasing goods or saving other orders does not trigger it. New Order has no cooldown.
The reaction appears immediately, lasts 0.5 seconds with a fade at the end,
survives rapid card re-renders, and does not
intercept clicks. Failed requests and newly generated ready orders do not
trigger it. Merely finding a jackpot does not trigger it either. Reduced motion
shows the same icon without animation. This is
local visual feedback with no economic penalty or saved state. Verify with
`node tests/ui_order_reaction.cjs` using intercepted API responses.
The transparent sprite is `assets/game-art/reactions/crying-face-pixel.png`,
preloaded by Market alongside `assets/game-art/reactions/dollar-sign-pixel.svg`.
The crying face's generation prompt is stored beside it.

## Breakfast Club

Breakfast Club is a recipe workshop unlocked by a completed roastery. Existing started workshops stay accessible. It uses separate workshop supplies and practice coins, one cooking slot and one queue, four deliveries and one upgrade choice. Completion grants five town materials and +25% of base speed for the selected roastery recipe, once. Progress saves on the server; Close/Escape restores focus. Existing art
is used without new animations. Four simulated paths take 360–465 seconds of
cooking; enjoyment still needs human playtesting.

## Validation

- `node tests/ui_page_purposes.cjs http://127.0.0.1:3003`: reads a representative
  snapshot, then intercepts economy calls inside the test browser. Verifies
  relocated controls, upgrades, holds, recipe processing, delivery IDs, surplus
  sales, quiz answers and the separate practice-portfolio explanation, persistent business selection, the
  selected grey construction image, and the event trigger. No purchases touch
  the running save.
- `node tests/ui_viewport.cjs http://127.0.0.1:3003`: read-only checks at 1366×768,
  1366×650, 1728×694, 1920×1080, 1024×768, 768×768, 390×844 and 844×390. Visits every view and list
  page, checking page scroll and the actual bounds of visible content/buttons.
- Engine/API tests remain separate: `.venv/bin/python -m pytest -q`.

## Progression update

Upgrade rows explain their town income effect or storage benefit. Farm and
roastery gain a specialty selector at production level 3; its output tradeoff is
shown below the selector. Their level 3/6 exterior sprites reflect the highest
upgrade level and remain static (no misleading animation toggle).

Market shows an active Town project first, followed by Quick cash and Building supplies deliveries. Projects fund the first two expansions and then café reputation. Only the two ordinary delivery channels have free rarity rolls. Save / Release controls bounded reservations; existing reactions remain on ordinary deliveries. Regular buyers provide automatic repeat income in their own panel.
Licence accepts 100 ordinary goods sold as an alternative to three deliveries.
Breakfast Club completion explains the permanent roastery recipe bonus.

`node tests/ui_progression.cjs http://127.0.0.1:3005` tests commitment/release,
persistence on reload, specialty changes, free replacement feedback and all four art
variants with intercepted mutations. It writes five in-game screenshots to
`previews/`. Viewport tests cover eight sizes including 844×390 landscape.

Market now labels Standard, Large, Rare and Jackpot offers with distinct colors
and the actual retail payout multiplier. New Order remains clickable while a
request is running; extra clicks queue and use each newly returned order ID.
Recipe requirements paginate within a card when needed, preserving access to
Deliver, Save and New Order on short screens. A new offer resets its ingredient
page to the beginning. `tests/ui_order_rolls.cjs` verifies six rapid clicks,
correct IDs, five-product jackpot display, and four screen sizes.

## Opening and income revision

See [GAMEPLAY_SEQUENCE.md](GAMEPLAY_SEQUENCE.md) for the finite project sequence, construction grant rules, income accounting, migration and pacing evidence. Build keeps its three-column desktop layout and uses the lower strip for the current goal and workshop. Compact layouts combine business selection with view tabs; no selector appears for a single business. Tablets below 1100px use those tabs to keep every control readable. Actual shop income includes walk-ins and regular buyers; the estimate is labeled separately. `tests/ui_purpose_fixes.cjs` checks the new behavior and content bounds without mutating the preview save.
