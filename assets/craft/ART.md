# Craft pixel art

## 300-item catalog and 64 supplies

The second expansion adds 150 craft sprites and 28 supply sprites. All seven PNGs were generated with the built-in imagegen tool, using `craft-items-05.png` as a style reference, and copied into `assets/craft/` without bitmap changes. The complete final prompt set is [expansion-300-prompts.json](expansion-300-prompts.json). Names, recipes, and descriptions are in `previews/craft_expansion_300_catalog.json` and `previews/craft_expansion_64_supplies.json`.

| Saved atlas | Catalog indices | Layout | Original generated filename |
| --- | --- | --- | --- |
| `craft-items-06.png` | Items 150–179 | 6 × 5 | `exec-769b9e31-970c-481d-ba27-f6d98dac3cfb.png` |
| `craft-items-07.png` | Items 180–209 | 6 × 5 | `exec-00046a42-8774-4972-be5c-c3c3078a1e97.png` |
| `craft-items-08.png` | Items 210–239 | 6 × 5 | `exec-780a3441-c6c4-468e-b13c-8f3052e591dc.png` |
| `craft-items-09.png` | Items 240–269 | 6 × 5 | `exec-2b4b35cb-0b3d-4e62-b10a-f4909293d625.png` |
| `craft-items-10.png` | Items 270–299 | 6 × 5 | `exec-d55c559a-1276-4865-916a-8533d14d7d26.png` |
| `craft-supplies-04.png` | Supplies 36–51 | 4 × 4 | `exec-fd27a8b5-4981-4045-8c77-82d20bfe0570.png` |
| `craft-supplies-05.png` | Supplies 52–63 | 4 × 3 | `exec-646e702c-ac4b-4759-b401-73d6b17ce837.png` |

Indices are zero-based. `craft-art.js` provides the display rectangles measured by `previews/inspect_craft_atlas.py`; the existing icon-only responsive grid and ingredient popups consume the same mapping. The final item atlas contains the 30 expensive scientific, robotics, industrial, and space crafts.

## Catalog expansion

The built-in image-generation tool produced 120 additional craft icons and 24 additional component icons, using `craft-items.png` as a style reference. Original artwork remains unchanged. New images are copied into this directory and used directly by the game:

| Atlas | Catalog indices | Layout |
| --- | --- | --- |
| `craft-items-02.png` | Items 30–59 | 6 columns × 5 rows |
| `craft-items-03.png` | Items 60–89 | 6 columns × 5 rows |
| `craft-items-04.png` | Items 90–119 | 6 columns × 5 rows |
| `craft-items-05.png` | Items 120–149 | 6 columns × 5 rows |
| `craft-supplies-02.png` | Supplies 12–23 | 4 columns × 3 rows |
| `craft-supplies-03.png` | Supplies 24–35 | 4 columns × 3 rows |

The complete prompts are in `item-expansion-prompts.json` and `expansion-prompts.json`. Appearance descriptions and item order are also recorded in `previews/craft_expansion_catalog.json` and `previews/craft_expansion_supplies.json`.

`craft-art.js` maps each atlas to a stable starting index, image URL, dimensions, and display rectangles. `previews/inspect_craft_atlas.py` measures those rectangles without modifying image pixels. The catalog and ingredient dialogs share this mapping, so every item and supply has its own artwork.

Generated with the built-in imagegen tool from the user-approved black/amber crafting mockup. The PNGs are original tool outputs; the UI selects cells through CSS background positions without cropping or changing the bitmaps.

- `craft-items.png`: 1374 × 1145, 6 columns × 5 rows. Row-major order follows `crafting.RECIPES` / payload `iconIndex`.
- `craft-supplies.png`: 1448 × 1086, 4 columns × 3 rows. Row-major order: wooden boards, fiber bundles, metal sheets, copper stock, battery cells, solar cells, glass panels, rubber sheets, plastic casings, circuit boards, insulation, packaging.

Black gutters are intentional, matching the game's pure-black surface. The generator did not perfectly align equal-size cells, so `craft-art.js` records each visible sprite's display rectangle. CSS positions the original bitmap within those rectangles and preserves each sprite's aspect ratio; no sprite is cut off and neighboring sprites stay hidden. Keep `image-rendering: pixelated` when changing CSS sizes.

## Expanded catalog

Four additional 6-column by 5-row sheets add 120 items, in the order recorded in `previews/craft_expansion_catalog.json`:

- `craft-items-02.png`: item indices 30–59.
- `craft-items-03.png`: item indices 60–89.
- `craft-items-04.png`: item indices 90–119.
- `craft-items-05.png`: item indices 120–149.

Two additional 4-column by 3-row sheets, `craft-supplies-02.png` and `craft-supplies-03.png`, cover supply indices 12–23 and 24–35. Each generated PNG is preserved without bitmap changes. Final prompts from the built-in imagegen tool are saved in [expansion-item-prompts.json](expansion-item-prompts.json) and [expansion-prompts.json](expansion-prompts.json).

The small CRAFT navigation icon reuses the original Portable Toolbox sprite with CSS background positioning.

## Final item-atlas prompt

Transform this approved game UI mockup into ONE PRODUCTION SPRITE ATLAS image for use in the actual game. Preserve the rich crisp colorful pixel-art visual language of the supplied item's illustrations, but REMOVE ALL interface, borders and text. Output exactly 30 isolated item sprites laid out in an EXACTLY UNIFORM 6 COLUMN by 5 ROW grid. Canvas target1536x1280 pixels, each cell256x256. Pure solid black #000000 background everywhere, no transparency needed. Absolutely no labels, text, grid lines, borders, separators, decorative framing or interface. Equal cell dimensions, equal spacing, centered sprites with 30-pixel safe inset from EVERY cell edge. Never overlap neighboring cells. Every cell contains exactly ONE item. All sprite centers on the regular grid with no irregular spacing. Sprites should occupy about190x190px of each256px cell (larger objects fit within196x196). Strong readable silhouettes, slight three-quarter view, crisp clearly visible square-pixel blocks as though48x48 pixel sprites enlarged 4x, rich16bit palette, limited color ramps, dark outlines, careful highlights. This is a practical CSS sprite sheet; EXACT COUNT AND GRID ALIGNMENT MATTER.
The original reference has15 items. Reuse those distinctive designs for the first15 then invent15 matching new designs. EXACT ROW-MAJOR ORDER:
ROW1 columns1–6: (1) Wooden Storage Crate, wood cube steel corner straps. (2) Wheeled Market Cart, wood handcart two wheels long handles. (3) Seedling Tray, low gray tray with green seedlings. (4) Woven Fish Trap, woven wicker funnel fish trap. (5) Smoking Cabinet, wood-and-steel cabinet chimney. (6) Copper Coffee Grinder, copper hand crank grinder.
ROW2 columns1–6: (7) Pastry Mold Set, grouped nested steel baking molds. (8) Portable Toolbox, red and steel box with handle. (9) Folding Workbench, plank top metal folding legs. (10) Hand-Crank Can Sealer, small bench mounted mechanical sealer and can with crank. (11) Rechargeable Battery Pack, compact green battery with two terminal contacts. (12) Solar Lantern, glowing lantern with blue solar panel roof.
ROW3 columns1–6: (13) Wind Turbine Rotor, standalone three white blades and central steel hub. (14) Homemade Radio Antenna, copper aerial on metal base. (15) Mini Generator, orange small portable generator black metal cage. (16) Farm Breakfast Basket, wicker basket holding red tomatoes, white eggs, little golden honey jar. (17) Seafood Picnic Box, open teal lunchbox with cooked fish, oyster shells and garnish. (18) Coffee Gift Set, small wooden presentation box holding coffee bean bag, cup and croissant.
ROW4 columns1–6: (19) Roadside Repair Kit, open orange tool case with wrench, gear, cables. (20) Reinforced Worktable, heavy dark steel worktable with thick wood top and angular braces distinct from folding bench. (21) Solar Charger, small folded blue solar panel attached to yellow charging pack. (22) Pantry Hamper, wicker basket of canned foods, red sauce bottle and purple preserve jars. (23) Precision Drill, compact teal desktop pillar drill with metal bit and work plate. (24) Wind-Powered Beacon, tiny red-and-white coastal beacon on base with miniature wind vane and gold lamp.
ROW5 columns1–6: (25) Steam-Powered Press, brass steam-driven industrial tabletop press, piston and curved copper tube. (26) Emergency Radio, rugged red portable radio with antenna, large tuning dial and speaker. (27) Cold-Chain Cargo, pale blue insulated shipping crate with dark metal edges and white snowflake symbol. (28) Automation Controller, green-gray compact control module with dark screen and colored buttons, short wire connectors. (29) Grid Battery Module, blue-gray sturdy industrial battery tower with yellow lightning symbol. (30) Satellite Survey Map, folded pale paper map with green land, blue water, orange location pin, and a small satellite motif.
Avoid photorealism, smooth CGI, painterly gradients, anti-aliased blurry edges, shadows outside sprites, floor planes. No written words or numbers in sprites. No fake screenshot. Only this exact30-sprite atlas. Do not miss items or add extras.

## Final supply-atlas prompt

Use case: sprite atlas / pixel-art game asset. Create ONE production sprite-sheet image of12 BASIC CRAFTING SUPPLIES for the same black-background pixel-art business game as the reference image. The reference is a visual style reference; transform the sprite contents to the supplies listed below. This is a single atlas asset. Output an EXACT UNIFORM 4-COLUMN by3-ROW GRID, each cell square; overall4:3 aspect ratio, target1024x768. Pure solid black #000000 background everywhere. No text, labels, numbers, grid lines, cell borders, floor planes, shadows outside sprites, UI, containers behind icons, or watermarks. Center exactly one supplier inventory sprite in each equal cell, with30px safe inset on every cell edge; sprite occupies about180–190px within each256px cell. EXACTLY12 sprites, evenly spaced. Match reference: rich colorful crisp16bit pixel art, slightly three-quarter view, readable silhouettes, limited palette, clearly visible square pixel clusters as if48x48 icons enlarged4x, steel gray, copper orange, wood brown, blue and green accents; no CGI or smooth paintings.
EXACT ORDER left to right:
ROW1: (1) Wooden Boards: tidy bundle of four warm brown timber planks. (2) Fiber Bundles: tan coiled natural rope and bound fibers. (3) Metal Sheets: three stacked shiny blue-gray flat steel sheets. (4) Copper Stock: three warm orange copper bars and short copper tube.
ROW2: (5) Battery Cells: grouped three short green rechargeable cylindrical cells with silver terminals. (6) Solar Cells: a small pair of dark blue photovoltaic panels with clear square cells and gray edges. (7) Glass Panels: two stacked pale cyan translucent glass panes with crisp white glints, solid black behind. (8) Rubber Sheets: one rolled black charcoal rubber sheet and a flat dark rubber sheet, use gray highlights so visible against black.
ROW3: (9) Plastic Casings: a pair of light gray molded electronic enclosure halves with small screw sockets. (10) Circuit Boards: a bright green small printed circuit board with dark chips and copper pin connectors. (11) Insulation: a roll of pale yellow fibrous insulation with silver foil backing. (12) Packaging: a small folded tan cardboard carton alongside folded packing paper and a short roll of packing tape, one cohesive sprite.
All12 are MATERIALS, do not substitute finished craftable tools, batteries housings, generators or baskets. No duplicate items. Exact regular4x3 layout so CSS background-position can address each item. Preserve clean black gutters.
