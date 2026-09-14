# YoMama game interface

The management pages share Dash's black surfaces, thin amber borders, terminal
font and supplied pixel art. Green means readiness or progress. The top-level
section is Game; Build is its business-management screen.

| Page | Purpose |
| --- | --- |
| Dash | Business overview and class standings |
| Build | Selected business, stock, sales controls, upgrades, construction, and events |
| Market | Orders, delivery reservations, and regular buyers |
| Operations | Building focus trees, permanent teams, products, quests and Advanced HQ |
| Licence | Milestones, quiz, and the separate practice portfolio |

## Build reference layout

The user explicitly prefers the earlier three-column Build layout: building
list left, selected building and goods center, upgrades/construction right,
and four stats above. Do not replace it with the town tile gallery. Build has
quick management controls; the detailed pages retain their specialized layouts.

The selected business shows actual sales, operating costs and profit over the
last 60 game seconds, their potential per-minute values, and an operating cash
profit margin. When `operatingStatement.enabled` is true, both the global
header and business figures use gross customer payments and the matching
production/selling expenses from that statement. Cash remains spendable money.
The margin tooltip explains cash accounting and the base-level target when all output is sold;
stock building, upgrades and shipment timing can change the actual margin.
There is no additional panel or target metric. Production and walk-in demand
retain their capacity figures. Actual
completed goods and goods sold in the last 60 game seconds appear below the
capacity estimates. Income and sales include walk-ins and regular buyers.
Manual deliveries and clearance are one-off sales, outside these operating
figures. BUILD refreshes every three seconds, highlights
changed values briefly, and shows per-good stock, capacity, and saved quantities beneath the operating
figures. Hold goods pauses walk-in sales; Resume shop sales reverses it. Sell
surplus pays the displayed clearance value while protecting regular-buyer and order
supplies. Shipment details remain on Market. Class pauses freeze the clocks; reconnects
resynchronize them with the server. Existing saves keep their progress and start
recording goods activity on migration, with no reset or invented history.

Order rewards, goal deliveries and regular-buyer cards still quote the actual
cash received after selling fees, with production costs paid separately.
Comparisons read “shop payout” instead of “retail” when statements are enabled.
Both guides explain Sales, Costs, Cash and take-home rewards in one paragraph.
Upgrade rows use gross sales and total cost changes from the before/after
statement; the tooltip and purchase feedback retain the net profit consequence.
Older payloads retain the previous monetary fields and comparisons.

When sector rhythms are enabled, the existing Production / min container adds
one short sector caption: Food small batches, Industry large batches, or
Energy/Tech staggered output. The production tooltip quotes each unlocked
product's nominal batch quantity and average interval at its current speed.
The Build guide explains these patterns, Industry's smaller-batch fallback,
Energy's initial delay and the 15-second stock updates. Average production
rates remain unchanged. Market's guide reminds players that a larger batch
can make stock jump after a wait. There are no additional panels or metrics.

General orders and their quantity-specific reservation controls belong to Market, not Build. Build provides the manual sales pause alongside the selected business stock.
There is no general Orders button or popup on Build. Breakfast Club is a
separate event, accessed from the bottom container.

Selecting the next business updates a greyed-out image beside the construction
controls. The image uses the selected frontier ID and existing art. Grayscale
applies to the image, never to a grey panel background. Actual construction
costs, requirements, stock, timers and permissions remain server-owned.

## Screen fit

`game-fit.js` makes the four management pages fill the available viewport.
Desktop panels stretch to the bottom. Buildings, products, inventories, orders,
and milestones use explicit pagination when their content exceeds available
room. Order and regular-buyer requirements show every item at once without
ingredient arrows. Short lists keep the current maximum type size; longer lists
adapt text, icons and spacing to the available width and height. Sizes reset on
each render and resize so shorter lists grow back. Controls must not be clipped
merely to hide scrollbars. Verify requirements with
`node tests/ui_market_goods_fit.cjs` and `node tests/ui_delivery_recipes.cjs`.

Below 1100px width or at most 650px height, view tabs switch between panels. A compact
navigation select and business selector preserve access without long lists.
Compact Build layouts offer Building, Stock, Upgrades, and Expand views. The
Stock view includes both sales controls and preserves the selected business.
Old warehouse.html links redirect to buildings.html#stock. Short landscape
layouts reserve the Build summary/event for its Building view. Orders remain on
Market. All panel/tab/page selections survive economy refreshes. Business
selection also persists across navigation in the browser session.

Inventory rows show actual item counts, reserved quantities and capacity bars.
Market displays real prices and delivery requirements. Surplus sales protect
buyer and order goods but can sell manually held stock; the relevant sale note says so.
Operations lists the business's products without automatic recipe dependencies.
The Build guide explains that each business makes goods independently, with no
ingredients taken from town stock. Cash, shelf space, unlock quests and business
pauses still govern production. The Products tab replaces the old Recipes label;
legacy payloads retain their recipe view. Separate practice quest kitchens stay
available, as do explicit equipment-crafting actions. Licence removes passed
quiz cards and locked investment placeholders, with every milestone reachable
through its pager. No fake data, filler paragraphs, or repeated order cards.

## Market feedback

Market gives a brief pixel-art crying-face reaction on an order card when the player
successfully replaces an order that was fulfillable or a jackpot when its request
was sent, including orders skipped by queued spam clicks. Save for this order
shows a pixel thumbs-up for standard, large and rare orders, or a pixel lucky 7
for jackpot orders. Successful deliveries show a green pixel dollar sign, or
pixel gold bars when the delivered order was a jackpot.
Town projects also show the thumbs-up when saved and the dollar when delivered,
including the final project. Releasing goods does not trigger a reaction.
New Order has no cooldown.
The reaction appears immediately, lasts 0.5 seconds with a fade at the end,
survives rapid card re-renders, and does not
intercept clicks. Failed requests and newly generated ready orders do not
trigger it. Merely finding a jackpot does not trigger it either. Reduced motion
shows the same icon without animation. This is
local visual feedback with no economic penalty or saved state. Verify with
`node tests/ui_order_reaction.cjs` using intercepted API responses.
The transparent sprite is `assets/game-art/reactions/crying-face-pixel.png`,
preloaded by Market alongside `assets/game-art/reactions/dollar-sign-pixel.svg`,
`assets/game-art/reactions/thumbs-up-pixel.svg`,
`assets/game-art/reactions/lucky-seven-pixel.svg` and
`assets/game-art/reactions/gold-bars-pixel.svg`.
The crying face's generation prompt is stored beside it.

## Breakfast Club

Breakfast Club is a recipe workshop unlocked by a completed roastery. Existing started workshops stay accessible. It uses separate workshop supplies and practice coins, one cooking slot and one queue, four deliveries and one upgrade choice. Completion grants five town materials and +25% of base speed for the selected roastery recipe, once. Progress saves on the server; Close/Escape restores focus. Existing art
is used without new animations. Four simulated paths take 360–465 seconds of
cooking; enjoyment still needs human playtesting.

## Validation

- `node tests/ui_business_live.cjs http://127.0.0.1:3094`: uses intercepted
  snapshots to verify actual metrics, automatic updates, pauses, reconnects,
  stock controls and panel fit at eight viewport sizes, for both
  opening and full towns. No test action changes the running save.
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

Market labels Standard, Small, Bulk, Large, Rare and Jackpot offers with distinct
badge colors and the actual shop-payout multiplier. The guide explains Small
and Bulk as different stock choices. CLICK!!!! shows the server's current roll
odds in its tooltip and remains clickable while a
request is running; extra clicks queue and use each newly returned order ID.
Order requirements paginate within a card when needed, preserving access to
Deliver, Save and New Order on short screens. A new offer resets its goods
page to the beginning. `tests/ui_order_rolls.cjs` verifies six rapid clicks,
correct IDs, five-product jackpot display, and four screen sizes.

## Opening and income revision

See [GAMEPLAY_SEQUENCE.md](GAMEPLAY_SEQUENCE.md) for the finite project sequence, construction grant rules, income accounting, migration and pacing evidence. Build keeps its three-column desktop layout and uses the lower strip for the current goal and workshop. Compact layouts combine business selection with view tabs; no selector appears for a single business. Tablets below 1100px use those tabs to keep every control readable. Actual shop income includes walk-ins and regular buyers; the estimate is labeled separately. `tests/ui_purpose_fixes.cjs` checks the new behavior and content bounds without mutating the preview save.
