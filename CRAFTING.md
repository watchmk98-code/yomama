# Crafting

CRAFT sits immediately after MARKET in the game navigation. It contains 30 original pixel-art items and an ingredient dialog. The action is labelled **CRAFT**. Item purposes and gameplay perks are intentionally left for a later design decision.

The page reuses BUILD's upper header, navigation styles, and responsive layout. All 30 items appear together in one grid, sized to fit desktop screens. Narrow or short screens scroll the same grid vertically. Full item names remain visible. The black canvas, amber outlines, large pixel artwork, and ingredient dialog follow the approved visual reference.

Crafting consumes one recipe from unreserved stock and purchased supplies, and saves the resulting item. Inventory reserved for regular buyers, saved delivery orders, or in-transit orders is protected. Energy and services are displayed as assembly inputs with their source businesses.

Basic supplies are purchased explicitly inside the ingredient dialog. Their button shows the exact quantity and YM cost. Have means available stock after reservations. Purchases and crafting preserve net worth by carrying the consumed value into stored supplies/items.

Existing saves acquire empty crafting storage in place; no class reset is needed. The live release requires the code/assets to be pushed and a **Manual Deploy**.

Run `python3 previews/craft_preview.py 4130` for a temporary showroom with all businesses, example stock and cash. Add `--fresh` for normal starting availability. The real database is never used.

## Catalog

| Item | Ingredients |
| --- | --- |
| Wooden Storage Crate | 3 Wooden Boards (supply) + 2 Steel Brackets |
| Wheeled Market Cart | 2 Welded Frames + 2 Spare Parts + 2 Machined Bolts |
| Seedling Tray | 2 Metal Sheets (supply) + 1 Steel Brackets |
| Woven Fish Trap | 3 Fiber Bundles (supply) + 2 Wooden Boards (supply) |
| Smoking Cabinet | 3 Metal Sheets (supply) + 2 Welded Frames + 1 Spare Parts + 1 Insulation (supply) + 1 Glass Panels (supply) |
| Copper Coffee Grinder | 2 Copper Stock (supply) + 2 Spare Parts + 1 Machined Bolts + 1 Rubber Sheets (supply) |
| Pastry Mold Set | 2 Metal Sheets (supply) + 1 CNC Parts |
| Portable Toolbox | 2 Metal Sheets (supply) + 2 Steel Brackets + 1 Spare Parts + 1 Plastic Casings (supply) |
| Folding Workbench | 3 Wooden Boards (supply) + 2 Steel Brackets + 2 Machined Bolts |
| Hand-Crank Can Sealer | 2 CNC Parts + 2 Spare Parts + 1 Steel Brackets |
| Rechargeable Battery Pack | 3 Battery Cells (supply) + 2 Copper Stock (supply) + 1 Spare Parts + 1 Insulation (supply) |
| Solar Lantern | 2 Solar Cells (supply) + 1 Battery Cells (supply) + 1 Spare Parts + 1 Glass Panels (supply) + 1 Plastic Casings (supply) |
| Wind Turbine Rotor | 2 CNC Parts + 2 Welded Frames + 3 Machined Bolts |
| Homemade Radio Antenna | 3 Copper Stock (supply) + 2 Steel Brackets + 1 Spare Parts |
| Mini Generator | 3 Copper Stock (supply) + 2 CNC Parts + 3 Spare Parts + 2 Insulation (supply) + 1 Rubber Sheets (supply) |
| Farm Breakfast Basket | 2 Eggs + 3 Tomatoes + 1 Honey + 1 Packaging (supply) |
| Seafood Picnic Box | 2 Fresh Catch + 2 Oysters + 1 Smoked Fish + 1 Packaging (supply) |
| Coffee Gift Set | 2 Roasted Beans + 2 Espresso Shots + 1 Pastries + 1 Packaging (supply) |
| Roadside Repair Kit | 1 Repairs + 3 Spare Parts + 1 Custom Mods + 1 Rubber Sheets (supply) |
| Reinforced Worktable | 2 Steel Brackets + 2 Welded Frames + 3 Machined Bolts + 2 Wooden Boards (supply) |
| Solar Charger | 2 Daytime kWh + 2 Solar Cells (supply) + 1 Battery Cells (supply) + 1 Circuit Boards (supply) + 1 Plastic Casings (supply) |
| Pantry Hamper | 2 Canned Goods + 1 Sauces + 2 Preserves + 1 Packaging (supply) |
| Precision Drill | 2 CNC Parts + 1 Tooling + 1 Prototypes + 1 Rubber Sheets (supply) |
| Wind-Powered Beacon | 2 Wind kWh + 2 Battery Cells (supply) + 2 Spare Parts + 1 Glass Panels (supply) + 1 Circuit Boards (supply) |
| Steam-Powered Press | 2 Steam Heat + 3 Welded Frames + 2 CNC Parts + 2 Insulation (supply) |
| Emergency Radio | 1 Bandwidth + 2 Spare Parts + 2 Copper Stock (supply) + 1 Plastic Casings (supply) + 1 Circuit Boards (supply) |
| Cold-Chain Cargo | 1 Container Slots + 2 Cold Storage + 1 Last-Mile Delivery + 2 Packaging (supply) + 2 Insulation (supply) |
| Automation Controller | 2 Compute Hours + 2 API Calls + 1 Custom Mods + 2 Circuit Boards (supply) + 1 Plastic Casings (supply) |
| Grid Battery Module | 2 Utility kWh + 3 Battery Cells (supply) + 2 CNC Parts + 2 Insulation (supply) + 2 Circuit Boards (supply) |
| Satellite Survey Map | 1 Satellite Bandwidth + 1 Ground Time + 2 Telemetry + 1 Packaging (supply) |

## Basic supplies

| Supply | Unit price |
| --- | ---: |
| Wooden Boards | 6 YM |
| Fiber Bundles | 4 YM |
| Metal Sheets | 10 YM |
| Copper Stock | 12 YM |
| Battery Cells | 18 YM |
| Solar Cells | 24 YM |
| Glass Panels | 8 YM |
| Rubber Sheets | 6 YM |
| Plastic Casings | 8 YM |
| Circuit Boards | 28 YM |
| Insulation | 7 YM |
| Packaging | 3 YM |

## Art and verification

The two original imagegen atlases and their final prompts are documented in [assets/craft/ART.md](assets/craft/ART.md). `craft-art.js` selects per-sprite display bounds within the original PNGs.

`tests/test_crafting.py` checks all recipes, building/supply coverage, persistence, reservations, value conservation, validation, authentication, class pause, and duplicate/stale requests. `tests/ui_craft.cjs` exercises purchases and crafting through the real preview API and checks eight viewport sizes.
