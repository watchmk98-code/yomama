# Crafting decisions

Design record, 16 September 2026. The proposed catalog in
[design/crafting_catalog.json](design/crafting_catalog.json) is not loaded by the
game. The separate [15-item trial](design/crafting-pilot.md) is now implemented
in `crafting_pilot.py` and `config/crafting-pilot.v1.json`. It runs only when a
class snapshot explicitly enables it. The default class rules are unchanged.

## Agreed rules

- Unlocks combine a cash payment with appropriate quest, focus-tree and/or
  completed manual-order milestones. A product need not require all four routes.

- Every eligible unlocked product produces automatically. There is no selected
  recipe, active-product limit, manual batch button or premium-line toggle.

- Production needs its recipe ingredients and any explicitly required assets
  assigned to that business. An unavailable ingredient or required asset pauses
  the affected product; restoring it allows production to resume.

- Equipment and intangibles are retained assets. Basic supplies and intermediate
  crafted products are consumed ingredients. Owning an asset in storage does not
  activate its business benefit.

- Supplies remain manually purchased. Welcome-back packs, quests and other
  milestones can also award random basic supplies. Rewards do not depend on which
  businesses the player owns. Crafted products and business assets are excluded
  from rewards for now.
  
- Some recipes may consume other crafted items. Add these links only when they
  make physical or commercial sense; a simple recipe can stay simple.

## How products are connected

The catalog identifies the business that actually manufactures, prepares or
finishes an item. A business using an item, or producing one of its inputs, does
not automatically become its manufacturer.

For example, metal trays and cabinets fit Ironworks; machined tools fit Machine
Works; coffee gift assortments fit the Roastery; preserves fit the Cannery.
Power plants do not become electronics factories, and farmers do not fabricate
machinery merely because the machinery is used on a farm.

`mapped` means the product has a natural proposed producer. `deferred` means no
connection is assigned yet; it is not a removed item or a new unlock condition.
Unrelated electronics, textiles and specialist space/quantum projects can remain
unconnected. There is no quota of products or dependencies per business.

Asset requirements describe the current product's manufacturing step. Packing
already roasted beans does not require roasting them again. Pressing a metal
tray can require a press; welding a frame can require welding equipment. Simple
assembly can have no special asset requirement. An intangible may give a useful
stat benefit even when it is not a recipe prerequisite.

The two equipment slots and one intangible slot already shown in the building
panel are assignment destinations. One assigned asset can serve multiple
compatible products at that business; it is not consumed by each batch.

## Existing recipes that need correction

The original 300 item IDs and 64 supply IDs are preserved in this design.
`currentIngredients` records the existing recipe, not an approved automatic
production bill of materials. `recipeReviewRequired` flags problems to resolve
before activating that recipe.

Several old recipes mix a container or machine with the goods it would hold or
process. Pastries should not be consumed to manufacture a cooling rack. Tomatoes
should not be consumed to fabricate a bare metal screen. Do not redefine an empty
container as a filled food bundle merely to justify those ingredients.

A clear component example is a rechargeable battery pack used inside a solar
lantern. That connection can remain a candidate while either product lacks a
natural producer. A dependency does not justify inventing a manufacturer.
Before adding any chain, replace the corresponding loose inputs rather than
charging for the same component twice, and check that the chain has no cycle.

## Asset effects

All 45 existing assets have a proposed benefit and an explicit list of affected
base products in the JSON. The percentages are initial tuning targets, not
validated balance or currently active bonuses.

- Production speed improves the relevant production operation.
- Processing-cost reductions affect cash operating/processing costs, not the
  quantities of recipe ingredients and not a second discount on their purchase.
- Storage adds capacity for the specified goods.
- Shop demand expands potential sales; it does not create cash without stock.
- A selling-price premium applies to eligible sold goods. Margin reporting must
  include their real ingredient and processing costs.

Use additive percentage-point bonuses against the base value for the same stat;
do not compound the same asset through different systems. A repeated copy of the
same asset does not stack on one business. Bonuses apply only while assigned.
The asset's accounting value and its productive effect are separate.

The JSON lists craft products requiring each asset so the proposed connection is
inspectable. It does not extend a benefit to unrelated products at the same
business. Independent basic production remains available without acquiring these
new assets.

## Catalog review summary

All 300 existing items were reviewed: **154 have a natural proposed producer**; **146 remain unconnected**. **90 existing recipes need ingredient review**, including some deferred products. Mapping a producer does not approve every old ingredient or activate that product.

| Business | Connected products | Examples |
| --- | ---: | --- |
| Greenfield Farm | 3 | Farm Breakfast Basket, Hanging Garden, Tomato Seed Packets |
| Harbor Fish Stall | 4 | Seafood Picnic Box, Oyster Tasting Tray, Smoked Fish Gift Box |
| Copper Kettle Roastery | 4 | Coffee Gift Set, Honey Pastry Tower, Honey-Glazed Pastries |
| Tinker’s Garage | 4 | Rechargeable Battery Pack, Roadside Repair Kit, Electric Cargo Tricycle |
| Ironworks Shop | 55 | Wooden Storage Crate, Wheeled Market Cart, Seedling Tray |
| Meridian Cannery | 8 | Pantry Hamper, Honey Spread Jars, Tomato Chutney |
| Bluecollar Machine Works | 74 | Copper Coffee Grinder, Hand-Crank Can Sealer, Wind Turbine Rotor |
| Atlas Freight Terminal | 1 | Cold-Chain Cargo |
| Orbital Uplink Center | 1 | Satellite Survey Map |

Businesses absent from the table currently have no natural craft-product connection. Their assets can still improve the relevant existing business outputs.

Two proposed component links replace six loose battery cells with two assembled three-cell battery packs: Electric Cargo Tricycle and Folding Electric Scooter. No other craft-to-craft link is being imposed.

## Remaining catalog work

Finish flagged recipes, set and simulate unlock/acquisition prices, batch timing,
selling terms, demand and reward sizes. Product `stage` and `focusBranch` fields
are preliminary organization, not yet exact unlock requirements. Deferred items
have no planned gates.

The engine must handle automatic competition for shared ingredients, reserve
promised deliveries, preserve old crafted stock and identities, and account for
finished stock without counting its consumed inputs twice. These are engine
requirements, not extra player controls.

The 15-item trial implements combined unlocks, automatic manufacturing and sales,
ten purchasable assets with working building slots and finite lifetimes, and
random basic-supply rewards. Its prices, effects and exact recipe overrides take
precedence over proposals in the broad catalog above. The other items retain
their current behavior. Run `python3 previews/crafting_pilot_preview.py 4146`
to try it with a disposable save. A live release needs Manual Deploy and explicit
class-snapshot adoption; no existing class is reset or opted in automatically.
