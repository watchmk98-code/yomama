# Crafting

CRAFT sits immediately after MARKET in the game navigation. It contains **300 pixel-art items** and an ingredient dialog. The action is labelled **CRAFT**. Item purposes and gameplay perks remain a later design decision.

The page reuses BUILD's upper header, five metric panels, navigation styles, and responsive layout. All 300 items fit on one screen without catalog scrolling. Catalog tiles show only icons; complete names remain available on hover, to assistive technology, and in the ingredient dialog. The popup adapts its layout to fit without scrolling. The black canvas, amber outlines, pixel artwork, and ingredient dialog retain the approved style.

The first 150 item IDs, recipes, and icon positions are unchanged. This expansion appends 150 distinct items in five ordered groups of 30. Recipes combine products from all 15 businesses with 64 purchasable crafting supplies. The first 36 supplies retain their IDs and prices; 28 new materials and components range from cork, bamboo, and cloth fittings to superconducting coils, photonic processors, and quantum cores.

Crafting consumes one recipe from unreserved stock and purchased supplies, then saves the resulting item. Stock reserved for regular buyers, saved delivery orders, and in-transit orders is protected. Energy and services are labelled as assembly inputs with their source businesses.

Supplies are purchased explicitly inside the ingredient dialog. Each purchase button shows the exact quantity and YM cost. Have means available stock after reservations. Purchases and crafting preserve net worth by carrying the consumed value into stored supplies/items. The same revision and request-ID checks prevent retries from spending twice.

Existing saves retain all crafted ownership, supplies, and transaction history. New items become visible without changing the class rules snapshot or resetting the class. The live release requires the code/assets to be pushed and a **Manual Deploy**.

Run `python3 previews/craft_preview.py 4130` for a temporary showroom with all businesses, example stock and cash. Add `--fresh` for normal starting availability. The real database is never used.

## Ultra-advanced craft costs

The final 30 items (icon indices 270–299) form the expensive end of the catalog: quantum and photonic computers, fusion and cryogenic assemblies, industrial robotics, and space instruments. Their purchased supplies alone total **29,760–89,400 YM per item**, before the value of any consumed business products. Eight specialist components cost 1,800–5,000 YM each; these recipes use larger quantities of relevant parts.

This tier is a catalog and cost distinction. It adds no licence requirement, timer, perk, reward, or selling mechanism. Crafting still transfers the exact consumed value into the saved object. The remaining new recipes range from household objects and food preparations to machines and scientific equipment.

## Catalog

The order below matches the stable icon indices 0–299. Ingredient quantities are authoritative in `crafting.py`.

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
| Roadside Repair Kit | 1 Repairs (service) + 3 Spare Parts + 1 Custom Mods + 1 Rubber Sheets (supply) |
| Reinforced Worktable | 2 Steel Brackets + 2 Welded Frames + 3 Machined Bolts + 2 Wooden Boards (supply) |
| Solar Charger | 2 Daytime kWh (energy) + 2 Solar Cells (supply) + 1 Battery Cells (supply) + 1 Circuit Boards (supply) + 1 Plastic Casings (supply) |
| Pantry Hamper | 2 Canned Goods + 1 Sauces + 2 Preserves + 1 Packaging (supply) |
| Precision Drill | 2 CNC Parts + 1 Tooling + 1 Prototypes + 1 Rubber Sheets (supply) |
| Wind-Powered Beacon | 2 Wind kWh (energy) + 2 Battery Cells (supply) + 2 Spare Parts + 1 Glass Panels (supply) + 1 Circuit Boards (supply) |
| Steam-Powered Press | 2 Steam Heat (energy) + 3 Welded Frames + 2 CNC Parts + 2 Insulation (supply) |
| Emergency Radio | 1 Bandwidth (service) + 2 Spare Parts + 2 Copper Stock (supply) + 1 Plastic Casings (supply) + 1 Circuit Boards (supply) |
| Cold-Chain Cargo | 1 Container Slots (service) + 2 Cold Storage (service) + 1 Last-Mile Delivery (service) + 2 Packaging (supply) + 2 Insulation (supply) |
| Automation Controller | 2 Compute Hours (service) + 2 API Calls (service) + 1 Custom Mods + 2 Circuit Boards (supply) + 1 Plastic Casings (supply) |
| Grid Battery Module | 2 Utility kWh (energy) + 3 Battery Cells (supply) + 2 CNC Parts + 2 Insulation (supply) + 2 Circuit Boards (supply) |
| Satellite Survey Map | 1 Satellite Bandwidth (service) + 1 Ground Time (service) + 2 Telemetry (service) + 1 Packaging (supply) |
| Harvest Crate | 4 Tomatoes + 2 Honey + 3 Wooden Boards (supply) + 2 Packaging (supply) |
| Garden Planter | 2 Tomatoes + 3 Wooden Boards (supply) + 2 Steel Brackets + 2 Fiber Bundles (supply) |
| Egg Carrier | 4 Eggs + 2 Foam Padding (supply) + 2 Packaging (supply) + 2 Textile Cloth (supply) |
| Honey Spread Jars | 3 Honey + 2 Preserves + 2 Glass Panels (supply) + 2 Packaging (supply) |
| Tomato Chutney | 4 Tomatoes + 2 Sauces + 2 Honey + 2 Glass Panels (supply) |
| Fisherman's Bucket | 2 Fresh Catch + 3 Metal Sheets (supply) + 2 Fiber Bundles (supply) |
| Oyster Tasting Tray | 4 Oysters + 2 Ceramic Pieces (supply) + 2 Smoked Fish |
| Smoked Fish Gift Box | 3 Smoked Fish + 2 Sauces + 2 Wooden Boards (supply) + 2 Packaging (supply) |
| Camping Kettle | 2 Steel Brackets + 3 Metal Sheets (supply) + 2 Copper Stock (supply) + 2 Heating Elements (supply) |
| Iced Coffee Flask | 3 Espresso Shots + 2 Glass Panels (supply) + 2 Insulation (supply) + 2 Metal Sheets (supply) |
| Pastry Display Case | 4 Pastries + 3 Glass Panels (supply) + 2 Wooden Boards (supply) + 2 Hinges (supply) |
| Roasting Drum | 2 Roasted Beans + 3 Metal Sheets (supply) + 2 Welded Frames + 2 Electric Motors (supply) |
| Pocket Wrench | 2 Spare Parts + 2 CNC Parts + 2 Rubber Sheets (supply) |
| Rolling Tool Cabinet | 2 Tooling + 3 Metal Sheets (supply) + 2 Welded Frames + 2 Hinges (supply) + 2 Ball Bearings (supply) |
| Bicycle Repair Stand | 2 Welded Frames + 2 Steel Brackets + 2 Spare Parts + 2 Rubber Sheets (supply) |
| Desktop Fan | 2 Daytime kWh (energy) + 2 Electric Motors (supply) + 2 Copper Stock (supply) + 2 Plastic Casings (supply) |
| Seed Sorter | 2 Tomatoes + 2 CNC Parts + 2 Metal Sheets (supply) + 2 Motion Sensors (supply) |
| Grow Light | 2 Daytime kWh (energy) + 3 LED Arrays (supply) + 2 Welded Frames + 2 Wire Spools (supply) |
| Soup Thermos | 3 Tomatoes + 2 Sauces + 2 Metal Sheets (supply) + 2 Insulation (supply) |
| Sauce Tasting Set | 3 Sauces + 3 Ceramic Pieces (supply) + 2 Wooden Boards (supply) |
| Hanging Spring Scale | 2 CNC Parts + 2 Steel Brackets + 2 Clockwork Gears (supply) + 2 Metal Sheets (supply) |
| Packing Press | 2 CNC Parts + 2 Welded Frames + 2 Pressure Valves (supply) + 2 Foam Padding (supply) |
| Portable Speaker | 2 Bandwidth (service) + 2 Speaker Cones (supply) + 2 Battery Cells (supply) + 2 Plastic Casings (supply) |
| Digital Sketchpad | 2 Cloud Storage (service) + 2 Display Panels (supply) + 2 Microcontrollers (supply) + 2 Wooden Boards (supply) |
| Weather Logbook | 2 Telemetry (service) + 2 Ground Time (service) + 3 Paper Sheets (supply) + 2 Leather Straps (supply) |
| Wind Chime | 2 Copper Stock (supply) + 2 Metal Sheets (supply) + 2 Fiber Bundles (supply) + 2 Ceramic Pieces (supply) |
| Solar Clock | 2 Utility kWh (energy) + 2 Solar Cells (supply) + 2 Clockwork Gears (supply) + 2 Display Panels (supply) |
| Steam Iron | 2 Steam Heat (energy) + 2 Heating Elements (supply) + 2 Metal Sheets (supply) + 2 Textile Cloth (supply) |
| Insulated Delivery Bag | 2 Leather Straps (supply) + 2 Foam Padding (supply) + 3 Textile Cloth (supply) + 2 Insulation (supply) |
| Pocket Microscope | 2 CNC Parts + 3 Optical Lenses (supply) + 2 LED Arrays (supply) + 2 Plastic Casings (supply) |
| Birdhouse | 2 Machined Bolts + 3 Wooden Boards (supply) + 2 Fiber Bundles (supply) + 2 Hinges (supply) |
| Greenhouse Window | 2 Tomatoes + 3 Glass Panels (supply) + 2 Steel Brackets + 2 Sealant (supply) |
| Hanging Garden | 2 Tomatoes + 3 Fiber Bundles (supply) + 2 Textile Cloth (supply) + 2 Wooden Boards (supply) |
| Farmer's Lunch Tin | 3 Eggs + 3 Tomatoes + 2 Metal Sheets (supply) + 2 Foam Padding (supply) |
| Honey Pastry Tower | 3 Honey + 4 Pastries + 2 Ceramic Pieces (supply) + 2 Packaging (supply) |
| Breakfast Skillet | 4 Eggs + 3 Tomatoes + 3 Metal Sheets (supply) + 2 Spare Parts |
| Seafood Skewers | 3 Fresh Catch + 2 Oysters + 2 Tomatoes + 2 Wooden Boards (supply) |
| Harbor Soup Pot | 3 Fresh Catch + 2 Sauces + 3 Metal Sheets (supply) + 2 Heating Elements (supply) |
| Oyster Cooler | 4 Oysters + 2 Cold Storage (service) + 3 Foam Padding (supply) + 2 Plastic Casings (supply) |
| Coffee Drip Stand | 3 Roasted Beans + 2 Copper Stock (supply) + 2 Glass Panels (supply) + 2 Filter Cartridges (supply) |
| Espresso Cup Set | 3 Espresso Shots + 3 Ceramic Pieces (supply) + 2 Resin (supply) |
| Biscuit Tin | 4 Pastries + 2 Metal Sheets (supply) + 2 Paper Sheets (supply) + 2 Hinges (supply) |
| Hand Drill | 2 CNC Parts + 2 Spare Parts + 2 Ball Bearings (supply) + 2 Rubber Sheets (supply) |
| Folding Ladder | 3 Welded Frames + 2 Steel Brackets + 2 Hinges (supply) + 2 Rubber Sheets (supply) |
| Welding Mask | 2 Tooling + 2 Glass Panels (supply) + 2 Plastic Casings (supply) + 2 Leather Straps (supply) |
| Socket Set | 3 CNC Parts + 2 Tooling + 2 Metal Sheets (supply) + 2 Packaging (supply) |
| Solar Watering Kit | 2 Daytime kWh (energy) + 2 Water Pumps (supply) + 3 Flexible Hoses (supply) + 2 Solar Cells (supply) |
| Garden Mister | 2 Daytime kWh (energy) + 2 Water Pumps (supply) + 2 Pressure Valves (supply) + 2 Flexible Hoses (supply) |
| Preserve Sampler | 4 Preserves + 3 Glass Panels (supply) + 2 Packaging (supply) + 2 Paper Sheets (supply) |
| Pantry Shelf | 2 Canned Goods + 4 Wooden Boards (supply) + 3 Steel Brackets + 2 Hinges (supply) |
| Bench Vise | 2 CNC Parts + 2 Tooling + 2 Steel Brackets + 2 Clockwork Gears (supply) |
| Drafting Compass | 2 CNC Parts + 2 Tooling + 2 Copper Stock (supply) + 2 Hinges (supply) |
| Rain Gauge | 2 Wind kWh (energy) + 2 Motion Sensors (supply) + 2 Glass Panels (supply) + 2 Plastic Casings (supply) |
| Heat Exchanger | 3 Steam Heat (energy) + 3 Copper Stock (supply) + 2 Pressure Valves (supply) + 2 Flexible Hoses (supply) |
| Wireless Doorbell | 2 Bandwidth (service) + 2 Speaker Cones (supply) + 2 LED Arrays (supply) + 2 Plastic Casings (supply) |
| Cargo Trolley | 2 Machined Bolts + 3 Welded Frames + 3 Ball Bearings (supply) + 2 Rubber Sheets (supply) |
| Desktop Terminal | 2 Compute Hours (service) + 2 API Calls (service) + 2 Display Panels (supply) + 2 Microcontrollers (supply) |
| Solar Food Dehydrator | 2 Utility kWh (energy) + 2 Tomatoes + 3 Glass Panels (supply) + 3 Metal Sheets (supply) + 2 Insulation (supply) |
| Moon Phase Projector | 2 Telemetry (service) + 3 Optical Lenses (supply) + 2 LED Arrays (supply) + 2 Plastic Casings (supply) |
| Field Notebook | 4 Paper Sheets (supply) + 2 Leather Straps (supply) + 2 Fiber Bundles (supply) + 2 Resin (supply) |
| Tomato Seed Packets | 4 Tomatoes + 3 Paper Sheets (supply) + 2 Packaging (supply) |
| Market Apron | 3 Textile Cloth (supply) + 2 Leather Straps (supply) + 2 Fiber Bundles (supply) + 2 Packaging (supply) |
| Picnic Table | 4 Wooden Boards (supply) + 3 Welded Frames + 2 Steel Brackets + 2 Sealant (supply) |
| Honey-Glazed Pastries | 3 Honey + 3 Pastries + 2 Eggs + 2 Paper Sheets (supply) |
| Tomato Relish Set | 4 Tomatoes + 2 Sauces + 2 Glass Panels (supply) + 2 Textile Cloth (supply) |
| Saltwater Aquarium | 3 Fresh Catch + 4 Glass Panels (supply) + 2 Water Pumps (supply) + 2 Filter Cartridges (supply) + 2 Sealant (supply) |
| Fishing Rod | 2 Custom Mods + 3 Fiber Bundles (supply) + 2 Copper Stock (supply) + 2 Resin (supply) |
| Dockside Smoker | 2 Smoked Fish + 3 Metal Sheets (supply) + 2 Heating Elements (supply) + 2 Insulation (supply) + 2 Hinges (supply) |
| Coffee Roasting Pan | 3 Roasted Beans + 3 Metal Sheets (supply) + 2 Rubber Sheets (supply) |
| Travel Coffee Kit | 2 Espresso Shots + 2 Roasted Beans + 2 Glass Panels (supply) + 2 Foam Padding (supply) + 2 Leather Straps (supply) |
| Pastry Cooling Rack | 3 Pastries + 2 Steel Brackets + 3 Metal Sheets (supply) + 2 Wire Spools (supply) |
| Compact Air Compressor | 3 Spare Parts + 2 Electric Motors (supply) + 2 Pressure Valves (supply) + 2 Flexible Hoses (supply) |
| Mechanic's Stool | 2 Welded Frames + 3 Foam Padding (supply) + 2 Leather Straps (supply) + 2 Ball Bearings (supply) |
| Metal Lockbox | 2 Steel Brackets + 3 Metal Sheets (supply) + 2 Hinges (supply) + 2 Clockwork Gears (supply) |
| Foldable Solar Mat | 2 Daytime kWh (energy) + 3 Solar Cells (supply) + 3 Textile Cloth (supply) + 2 Wire Spools (supply) |
| Portable Water Filter | 2 Daytime kWh (energy) + 3 Filter Cartridges (supply) + 2 Plastic Casings (supply) + 2 Flexible Hoses (supply) |
| Jam Label Printer | 2 CNC Parts + 4 Paper Sheets (supply) + 2 Microcontrollers (supply) + 2 Display Panels (supply) + 2 Electric Motors (supply) |
| Canning Funnel Set | 2 CNC Parts + 3 Metal Sheets (supply) + 2 Ceramic Pieces (supply) |
| Sauce Dispenser | 3 Sauces + 3 Glass Panels (supply) + 2 Pressure Valves (supply) + 2 Plastic Casings (supply) |
| Gear Puzzle Box | 2 CNC Parts + 3 Clockwork Gears (supply) + 3 Wooden Boards (supply) + 2 Resin (supply) |
| Wind-Up Music Box | 2 Prototypes + 3 Clockwork Gears (supply) + 2 Wooden Boards (supply) + 2 Metal Sheets (supply) |
| Wind Spinner | 2 Steel Brackets + 3 Copper Stock (supply) + 2 Ball Bearings (supply) + 2 Resin (supply) |
| Radiator Panel | 3 Steam Heat (energy) + 3 Copper Stock (supply) + 3 Metal Sheets (supply) + 2 Pressure Valves (supply) |
| Pocket Pager | 2 SMS Traffic (service) + 2 Display Panels (supply) + 2 Microcontrollers (supply) + 2 Battery Cells (supply) + 2 Plastic Casings (supply) |
| Shipping Seal Set | 2 CNC Parts + 2 Copper Stock (supply) + 3 Resin (supply) + 2 Paper Sheets (supply) |
| Folding Loading Ramp | 2 Machined Bolts + 3 Welded Frames + 4 Metal Sheets (supply) + 2 Hinges (supply) |
| Portable Memory Drive | 3 Cloud Storage (service) + 2 API Calls (service) + 2 Circuit Boards (supply) + 2 Plastic Casings (supply) + 2 Microcontrollers (supply) |
| LED Message Board | 2 SMS Traffic (service) + 3 Display Panels (supply) + 2 LED Arrays (supply) + 2 Circuit Boards (supply) |
| Emergency Power Cart | 2 Reserve Capacity (service) + 4 Battery Cells (supply) + 2 Welded Frames + 2 Electric Motors (supply) |
| Satellite Camera | 2 Satellite Bandwidth (service) + 2 Telemetry (service) + 3 Optical Lenses (supply) + 2 Display Panels (supply) |
| Portable Cassette Player | 2 Spare Parts + 2 CNC Parts + 2 Electric Motors (supply) + 2 Speaker Cones (supply) + 3 Plastic Casings (supply) |
| Desktop Oscilloscope | 2 Prototypes + 3 Compute Hours (service) + 2 Display Panels (supply) + 3 Circuit Boards (supply) + 2 Wire Spools (supply) |
| Handheld Barcode Scanner | 2 Custom Mods + 3 API Calls (service) + 2 Optical Lenses (supply) + 2 Microcontrollers (supply) + 2 Plastic Casings (supply) |
| Parcel Platform Scale | 3 Steel Brackets + 2 CNC Parts + 2 Motion Sensors (supply) + 2 Display Panels (supply) + 3 Metal Sheets (supply) |
| Shipping Label Printer | 2 CNC Parts + 2 API Calls (service) + 2 Electric Motors (supply) + 4 Paper Sheets (supply) + 3 Plastic Casings (supply) |
| Yellow Pallet Jack | 3 Welded Frames + 3 CNC Parts + 4 Ball Bearings (supply) + 2 Pressure Valves (supply) + 2 Rubber Sheets (supply) |
| Hard-Shell Flight Case | 3 Steel Brackets + 3 Machined Bolts + 3 Metal Sheets (supply) + 4 Foam Padding (supply) + 2 Hinges (supply) |
| Glass-Door Refrigerator | 3 CNC Parts + 4 Baseload Power (energy) + 3 Glass Panels (supply) + 2 Electric Motors (supply) + 4 Insulation (supply) |
| Reflector Solar Oven | 3 Steel Brackets + 2 Machined Bolts + 4 Metal Sheets (supply) + 2 Glass Panels (supply) + 4 Hinges (supply) |
| Pyramid Water Still | 2 Steel Brackets + 2 CNC Parts + 4 Glass Panels (supply) + 2 Flexible Hoses (supply) + 3 Sealant (supply) |
| Paddle Waterwheel | 3 Welded Frames + 3 CNC Parts + 5 Wooden Boards (supply) + 3 Ball Bearings (supply) |
| Cup Anemometer | 2 CNC Parts + 2 Telemetry (service) + 2 Ball Bearings (supply) + 2 Motion Sensors (supply) + 3 Metal Sheets (supply) |
| Copper Rooster Weather Vane | 2 Steel Brackets + 2 CNC Parts + 4 Copper Stock (supply) + 2 Ball Bearings (supply) |
| Illuminated Orbital Globe | 2 Ground Time (service) + 3 Telemetry (service) + 3 Glass Panels (supply) + 2 LED Arrays (supply) + 3 Resin (supply) |
| Rolled Constellation Chart | 3 Telemetry (service) + 2 Compute Hours (service) + 4 Paper Sheets (supply) + 2 Leather Straps (supply) |
| Brass Tripod Telescope | 3 CNC Parts + 2 Steel Brackets + 4 Optical Lenses (supply) + 3 Copper Stock (supply) + 3 Wooden Boards (supply) |
| Miniature Lunar Rover | 2 Prototypes + 2 Telemetry (service) + 3 Electric Motors (supply) + 2 Solar Cells (supply) + 4 Rubber Sheets (supply) |
| Electronic Terrarium | 2 Custom Mods + 2 API Calls (service) + 4 Glass Panels (supply) + 2 Water Pumps (supply) + 2 LED Arrays (supply) |
| Brass Pocket Compass | 2 CNC Parts + 2 Machined Bolts + 2 Permanent Magnets (supply) + 3 Copper Stock (supply) + 2 Glass Panels (supply) |
| Clockwork Signal Train | 3 CNC Parts + 2 Spare Parts + 4 Clockwork Gears (supply) + 3 Metal Sheets (supply) + 2 LED Arrays (supply) |
| Semaphore Signal Tower | 3 Welded Frames + 2 Spare Parts + 2 Electric Motors (supply) + 3 Metal Sheets (supply) + 2 LED Arrays (supply) |
| Open-Frame Server Rack | 3 Welded Frames + 4 Compute Hours (service) + 4 Circuit Boards (supply) + 3 Wire Spools (supply) + 2 Electric Motors (supply) |
| Reel Tape Archive | 4 Cloud Storage (service) + 3 CNC Parts + 2 Electric Motors (supply) + 3 Permanent Magnets (supply) + 3 Metal Sheets (supply) |
| Pocket Pixel Console | 2 Custom Mods + 2 Compute Hours (service) + 2 Display Panels (supply) + 3 Microcontrollers (supply) + 3 Plastic Casings (supply) |
| Arched Mantel Clock | 2 CNC Parts + 2 Machined Bolts + 4 Clockwork Gears (supply) + 3 Wooden Boards (supply) + 2 Glass Panels (supply) |
| Digital Picture Frame | 3 Cloud Storage (service) + 2 API Calls (service) + 2 Display Panels (supply) + 2 Microcontrollers (supply) + 3 Wooden Boards (supply) |
| Camera Quadcopter | 3 Prototypes + 2 Bandwidth (service) + 4 Electric Motors (supply) + 2 Optical Lenses (supply) + 3 Battery Cells (supply) |
| Nautical Signal Lamp | 3 Steel Brackets + 2 CNC Parts + 3 Optical Lenses (supply) + 3 LED Arrays (supply) + 3 Metal Sheets (supply) |
| Spherical Weather Balloon | 3 Telemetry (service) + 2 Bandwidth (service) + 4 Rubber Sheets (supply) + 3 Fiber Bundles (supply) + 2 Motion Sensors (supply) |
| Twin-Dish Ground Station | 3 Satellite Bandwidth (service) + 3 Ground Time (service) + 3 Welded Frames + 4 Metal Sheets (supply) + 2 Microcontrollers (supply) |
| Stackable Bento | 2 Eggs + 2 Tomatoes + 2 Smoked Fish + 2 Food-Safe Containers (supply) + 2 Cork Sheets (supply) |
| Honey Dipper Set | 2 Wooden Boards (supply) + 3 Honey + 2 Food-Safe Containers (supply) |
| Tomato Drying Screen | 4 Tomatoes + 2 Stainless Mesh (supply) + 2 Aluminum Profiles (supply) |
| Oyster Shucking Board | 4 Oysters + 2 Wooden Boards (supply) + 2 CNC Parts + 2 Leather Straps (supply) |
| Coffee Bean Canister | 4 Roasted Beans + 2 Food-Safe Containers (supply) + 2 Cork Sheets (supply) |
| Pastry Stencil Kit | 2 CNC Parts + 2 Silicone Molds (supply) + 2 Metal Sheets (supply) |
| Garden Watering Can | 3 Metal Sheets (supply) + 2 Copper Stock (supply) + 2 Sealant (supply) + 2 Steel Brackets |
| Bamboo Picnic Mat | 4 Bamboo Slats (supply) + 2 Textile Cloth (supply) + 2 Fiber Bundles (supply) + 2 Leather Straps (supply) |
| Cork Notice Board | 3 Cork Sheets (supply) + 3 Wooden Boards (supply) + 2 Felt Sheets (supply) + 2 Adhesive Tape (supply) |
| Zippered Tool Roll | 2 Tooling + 3 Textile Cloth (supply) + 2 Zippers (supply) + 2 Buckles (supply) |
| Retractable Tape Measure | 2 Metal Sheets (supply) + 2 Springs (supply) + 2 Plastic Casings (supply) + 2 Machined Bolts |
| Pedal Bin | 3 Metal Sheets (supply) + 2 Hinges (supply) + 2 Springs (supply) + 2 CNC Parts |
| Plant Moisture Meter | 2 Custom Mods + 2 Humidity Sensors (supply) + 2 Microcontrollers (supply) + 2 Display Panels (supply) + 2 Plastic Casings (supply) |
| Clothes Drying Rack | 3 Aluminum Profiles (supply) + 2 Steel Tubing (supply) + 2 Hinges (supply) + 2 Textile Cloth (supply) |
| Folding Camp Chair | 3 Steel Tubing (supply) + 3 Textile Cloth (supply) + 2 Hinges (supply) + 2 Buckles (supply) |
| Marionette Puppet | 3 Wooden Boards (supply) + 2 Textile Cloth (supply) + 3 Fiber Bundles (supply) + 2 Pigments (supply) + 2 Hinges (supply) |
| Tabletop Pinball | 2 Springs (supply) + 2 CNC Parts + 3 Wooden Boards (supply) + 2 Glass Panels (supply) + 2 Clockwork Gears (supply) |
| Mechanical Butterfly | 2 Prototypes + 2 Servo Motors (supply) + 2 Metal Sheets (supply) + 2 Pigments (supply) + 2 Springs (supply) |
| Ceramic Tile Mosaic | 4 Ceramic Pieces (supply) + 3 Pigments (supply) + 2 Resin (supply) + 2 Wooden Boards (supply) |
| Paint Palette | 2 Wooden Boards (supply) + 4 Pigments (supply) + 2 Sealant (supply) |
| Wicker Laundry Basket | 3 Bamboo Slats (supply) + 3 Fiber Bundles (supply) + 2 Textile Cloth (supply) |
| Rolltop Bread Box | 3 Wooden Boards (supply) + 3 Bamboo Slats (supply) + 2 Hinges (supply) + 2 Food-Safe Containers (supply) |
| Stovetop Popcorn Pot | 3 Metal Sheets (supply) + 2 Clockwork Gears (supply) + 2 Wooden Boards (supply) + 2 CNC Parts |
| Manual Pasta Press | 2 CNC Parts + 3 Aluminum Profiles (supply) + 2 Drive Belts (supply) + 2 Clockwork Gears (supply) |
| Accordion Desk Lamp | 2 LED Arrays (supply) + 3 Aluminum Profiles (supply) + 2 Springs (supply) + 2 Wire Spools (supply) |
| Wall Coat Rack | 3 Wooden Boards (supply) + 2 Steel Brackets + 2 Cork Sheets (supply) |
| Travel Sewing Case | 2 Tooling + 2 Textile Cloth (supply) + 2 Zippers (supply) + 2 Buckles (supply) |
| Folding Room Divider | 3 Bamboo Slats (supply) + 4 Textile Cloth (supply) + 2 Hinges (supply) + 2 Wooden Boards (supply) |
| Handheld Vacuum | 2 Electric Motors (supply) + 2 Filter Cartridges (supply) + 2 Plastic Casings (supply) + 2 Battery Cells (supply) + 2 Custom Mods |
| Floating Pool Lantern | 2 Solar Cells (supply) + 2 LED Arrays (supply) + 2 Plastic Casings (supply) + 2 Sealant (supply) + 2 Solar Charge Controllers (supply) |
| Hand-Crank Ice Cream Maker | 3 Food-Safe Containers (supply) + 2 Clockwork Gears (supply) + 3 Metal Sheets (supply) + 2 Wooden Boards (supply) |
| Honeycomb Candy Tin | 4 Honey + 2 Steam Heat (energy) + 2 Metal Sheets (supply) + 2 Food-Safe Containers (supply) |
| Tomato Paste Tubes | 4 Tomatoes + 2 Sauces + 3 Food-Safe Containers (supply) + 2 Adhesive Tape (supply) |
| Marinated Oyster Jars | 3 Oysters + 2 Sauces + 3 Food-Safe Containers (supply) + 2 Packaging (supply) |
| Coffee Siphon | 3 Glass Panels (supply) + 2 Heating Elements (supply) + 2 Steel Brackets + 2 Copper Stock (supply) |
| Picnic Cutlery Set | 2 Tooling + 2 Metal Sheets (supply) + 2 Bamboo Slats (supply) + 2 Packaging (supply) |
| Egg Poaching Cups | 4 Eggs + 2 Steam Heat (energy) + 2 Food-Safe Containers (supply) + 2 Silicone Molds (supply) |
| Tomato Spiralizer | 2 CNC Parts + 2 Welded Frames + 2 Steel Tubing (supply) + 2 Ball Bearings (supply) |
| Folding Fishing Net | 3 Fiber Bundles (supply) + 2 Aluminum Profiles (supply) + 2 Hinges (supply) + 2 Cork Sheets (supply) |
| Cork Fishing Floats | 4 Cork Sheets (supply) + 2 Pigments (supply) + 2 Wire Spools (supply) + 2 Sealant (supply) |
| Nautical Rope Ladder | 4 Fiber Bundles (supply) + 3 Bamboo Slats (supply) + 2 Buckles (supply) |
| Canvas Hammock | 4 Textile Cloth (supply) + 3 Fiber Bundles (supply) + 2 Buckles (supply) + 2 Wooden Boards (supply) |
| Camping Shower | 2 Textile Cloth (supply) + 2 Flexible Hoses (supply) + 2 Water Pumps (supply) + 2 Pressure Valves (supply) + 2 Temperature Probes (supply) |
| Insulated Sleeping Roll | 4 Textile Cloth (supply) + 3 Insulation (supply) + 2 Zippers (supply) + 2 Buckles (supply) |
| Leather Binocular Case | 4 Leather Straps (supply) + 3 Felt Sheets (supply) + 2 Buckles (supply) + 2 Zippers (supply) |
| Star Finder Wheel | 3 Paper Sheets (supply) + 2 Cork Sheets (supply) + 2 Pigments (supply) + 2 Telemetry (service) |
| Lighthouse Model | 3 Wooden Boards (supply) + 2 LED Arrays (supply) + 2 Glass Panels (supply) + 2 Pigments (supply) |
| Tin Sailing Boat | 3 Metal Sheets (supply) + 2 Textile Cloth (supply) + 2 Steel Tubing (supply) + 2 Sealant (supply) |
| Bamboo Flute | 3 Bamboo Slats (supply) + 2 Cork Sheets (supply) + 2 Sealant (supply) |
| Handmade Drum | 3 Textile Cloth (supply) + 3 Leather Straps (supply) + 3 Wooden Boards (supply) + 2 Buckles (supply) |
| Kalimba | 3 Metal Sheets (supply) + 3 Wooden Boards (supply) + 2 Springs (supply) + 2 Pigments (supply) |
| Acoustic Guitar | 4 Wooden Boards (supply) + 3 Fiber Bundles (supply) + 2 Metal Sheets (supply) + 2 Resin (supply) |
| Folding Easel | 4 Wooden Boards (supply) + 2 Hinges (supply) + 2 Steel Brackets + 2 Buckles (supply) |
| Watercolor Travel Set | 4 Pigments (supply) + 2 Silicone Molds (supply) + 2 Food-Safe Containers (supply) + 3 Paper Sheets (supply) |
| Stained-Glass Suncatcher | 4 Glass Panels (supply) + 3 Copper Stock (supply) + 2 Pigments (supply) + 2 Resin (supply) |
| Travel Backgammon Set | 3 Wooden Boards (supply) + 3 Felt Sheets (supply) + 2 Pigments (supply) + 2 Hinges (supply) |
| Sundial Pedestal | 2 CNC Parts + 3 Copper Stock (supply) + 3 Ceramic Pieces (supply) + 2 Steel Brackets |
| Balance Bird Toy | 2 Metal Sheets (supply) + 2 Wooden Boards (supply) + 2 Permanent Magnets (supply) + 2 Pigments (supply) |
| Bellows Film Camera | 3 Optical Lenses (supply) + 3 Textile Cloth (supply) + 3 Wooden Boards (supply) + 2 Hinges (supply) + 2 CNC Parts |
| Mechanical Cash Register | 4 Clockwork Gears (supply) + 3 CNC Parts + 2 Wooden Boards (supply) + 3 Metal Sheets (supply) + 2 Paper Sheets (supply) |
| Motorized Potter's Wheel | 4 CNC Parts + 3 Electric Motors (supply) + 3 Welded Frames + 3 Drive Belts (supply) + 3 Rubber Sheets (supply) |
| Desktop Vinyl Cutter | 4 CNC Parts + 3 Linear Actuators (supply) + 3 Microcontrollers (supply) + 3 Electric Motors (supply) + 4 Plastic Casings (supply) |
| Filament 3D Printer | 5 CNC Parts + 4 Linear Actuators (supply) + 4 Heating Elements (supply) + 4 Microcontrollers (supply) + 5 Aluminum Profiles (supply) |
| Embroidery Machine | 4 Tooling + 4 Servo Motors (supply) + 3 Microcontrollers (supply) + 3 Steel Tubing (supply) + 4 Textile Cloth (supply) |
| Robotic Chessboard | 4 CNC Parts + 4 Wooden Boards (supply) + 4 Permanent Magnets (supply) + 4 Servo Motors (supply) + 3 Microcontrollers (supply) |
| Six-Axis Robot Arm | 6 CNC Parts + 6 Servo Motors (supply) + 4 Welded Frames + 4 Microcontrollers (supply) + 4 Wire Spools (supply) |
| Digital Synthesizer | 4 Spare Parts + 4 Microcontrollers (supply) + 3 Speaker Cones (supply) + 3 Display Panels (supply) + 4 Circuit Boards (supply) |
| Reel Film Projector | 4 CNC Parts + 3 Electric Motors (supply) + 4 Optical Lenses (supply) + 4 LED Arrays (supply) + 4 Metal Sheets (supply) |
| Desktop Letterpress | 5 Welded Frames + 4 CNC Parts + 3 Linear Actuators (supply) + 4 Metal Sheets (supply) + 4 Pigments (supply) |
| Watchmaker's Lathe | 5 CNC Parts + 4 Tooling + 3 Electric Motors (supply) + 3 Drive Belts (supply) + 4 Steel Brackets |
| Hydroponic Tower | 4 Tomatoes + 4 Water Pumps (supply) + 4 Humidity Sensors (supply) + 5 Plastic Casings (supply) + 5 Flexible Hoses (supply) |
| Compact Electric Kiln | 4 Welded Frames + 6 Ceramic Pieces (supply) + 5 Heating Elements (supply) + 6 Insulation (supply) + 4 Temperature Probes (supply) |
| Desktop Laser Engraver | 4 Prototypes + 4 Linear Actuators (supply) + 4 Optical Lenses (supply) + 4 Circuit Boards (supply) + 5 Metal Sheets (supply) |
| Robot Floor Sweeper | 4 Custom Mods + 4 Servo Motors (supply) + 4 Motion Sensors (supply) + 5 Battery Cells (supply) + 4 Plastic Casings (supply) |
| Tabletop Air Hockey | 5 Wooden Boards (supply) + 4 CNC Parts + 4 Electric Motors (supply) + 4 Plastic Casings (supply) + 3 LED Arrays (supply) |
| Electric Harp | 4 CNC Parts + 5 Copper Stock (supply) + 3 Speaker Cones (supply) + 5 Wooden Boards (supply) + 4 Circuit Boards (supply) |
| Holographic Display Cube | 4 Prototypes + 4 Compute Hours (service) + 5 Optical Lenses (supply) + 5 LED Arrays (supply) + 6 Glass Panels (supply) |
| Motorized Camera Slider | 5 CNC Parts + 5 Aluminum Profiles (supply) + 4 Servo Motors (supply) + 4 Drive Belts (supply) + 3 Microcontrollers (supply) |
| Programmable Drawing Robot | 4 CNC Parts + 4 Microcontrollers (supply) + 4 Servo Motors (supply) + 3 Drive Belts (supply) + 4 Pigments (supply) |
| Digital Braille Reader | 4 Prototypes + 5 Linear Actuators (supply) + 4 Microcontrollers (supply) + 4 Circuit Boards (supply) + 4 Plastic Casings (supply) |
| Motorized Orrery | 5 CNC Parts + 5 Clockwork Gears (supply) + 4 Servo Motors (supply) + 5 Copper Stock (supply) + 5 Resin (supply) |
| Rotating Display Pedestal | 4 Welded Frames + 4 CNC Parts + 3 Electric Motors (supply) + 5 Ball Bearings (supply) + 4 Glass Panels (supply) |
| Magnetic Pendulum Sculpture | 4 Welded Frames + 4 CNC Parts + 5 Permanent Magnets (supply) + 4 Copper Stock (supply) + 4 Glass Panels (supply) |
| Electric Marble Run | 4 CNC Parts + 5 Metal Sheets (supply) + 6 Ball Bearings (supply) + 4 Electric Motors (supply) + 5 Wooden Boards (supply) |
| Pneumatic Tube Station | 5 CNC Parts + 5 Pressure Valves (supply) + 5 Flexible Hoses (supply) + 4 Electric Motors (supply) + 5 Plastic Casings (supply) |
| Desktop Book Scanner | 4 API Calls (service) + 4 CNC Parts + 5 Optical Lenses (supply) + 4 Display Panels (supply) + 4 LED Arrays (supply) |
| Polar Alignment Mount | 5 CNC Parts + 2 Precision Gyroscopes (supply) + 4 Servo Motors (supply) + 5 Steel Tubing (supply) + 4 Microcontrollers (supply) |
| Digital Mixing Console | 4 Compute Hours (service) + 4 Microcontrollers (supply) + 4 Display Panels (supply) + 5 Circuit Boards (supply) + 5 Spare Parts |
| Electric Spinning Wheel | 4 Welded Frames + 3 Electric Motors (supply) + 4 Drive Belts (supply) + 5 Fiber Bundles (supply) + 5 Wooden Boards (supply) |
| Vacuum Forming Machine | 5 Welded Frames + 4 Prototypes + 4 Electric Motors (supply) + 5 Heating Elements (supply) + 5 Metal Sheets (supply) |
| Acoustic Levitation Rig | 5 Prototypes + 6 Speaker Cones (supply) + 4 Microcontrollers (supply) + 5 Aluminum Profiles (supply) + 5 Circuit Boards (supply) |
| Laboratory Centrifuge | 5 CNC Parts + 5 Electric Motors (supply) + 5 Ball Bearings (supply) + 5 Plastic Casings (supply) + 4 Microcontrollers (supply) |
| Benchtop Spectrometer | 5 Prototypes + 6 Optical Lenses (supply) + 5 LED Arrays (supply) + 5 Circuit Boards (supply) + 5 Metal Sheets (supply) |
| Thermal Imaging Camera | 5 Prototypes + 4 CNC Parts + 5 Optical Lenses (supply) + 4 Display Panels (supply) + 5 Battery Cells (supply) |
| Underwater Inspection ROV | 5 Prototypes + 6 Electric Motors (supply) + 4 Optical Lenses (supply) + 6 Wire Spools (supply) + 6 Plastic Casings (supply) |
| Tilt-Rotor Airship | 5 Prototypes + 6 Electric Motors (supply) + 6 Solar Cells (supply) + 6 Fiber Bundles (supply) + 5 Resin (supply) |
| Electric Cargo Tricycle | 6 Welded Frames + 5 Electric Motors (supply) + 6 Battery Cells (supply) + 6 Rubber Sheets (supply) + 5 Machined Bolts |
| Cable Camera Gondola | 5 Prototypes + 5 Servo Motors (supply) + 4 Optical Lenses (supply) + 5 Aluminum Profiles (supply) + 5 Drive Belts (supply) |
| Portable Electric Winch | 5 Steel Brackets + 5 CNC Parts + 5 Electric Motors (supply) + 6 Fiber Bundles (supply) + 6 Battery Cells (supply) |
| Folding Electric Scooter | 5 Welded Frames + 6 Battery Cells (supply) + 4 Electric Motors (supply) + 5 Rubber Sheets (supply) + 5 CNC Parts |
| Programmable Vending Machine | 5 CNC Parts + 5 Servo Motors (supply) + 5 Microcontrollers (supply) + 6 Glass Panels (supply) + 6 Canned Goods |
| Magnetic Stirring Hotplate | 5 Prototypes + 5 Permanent Magnets (supply) + 5 Heating Elements (supply) + 4 Temperature Probes (supply) + 5 Ceramic Pieces (supply) |
| Recirculating Water Chiller | 5 CNC Parts + 5 Electric Motors (supply) + 5 Water Pumps (supply) + 5 Temperature Probes (supply) + 6 Copper Stock (supply) |
| Pressure Test Chamber | 5 CNC Parts + 6 Pressure Valves (supply) + 5 Glass Panels (supply) + 6 Metal Sheets (supply) + 6 Sealant (supply) |
| Mechanical Seismograph | 5 CNC Parts + 6 Springs (supply) + 5 Permanent Magnets (supply) + 6 Paper Sheets (supply) + 5 Clockwork Gears (supply) |
| Portable Geiger Counter | 5 Prototypes + 5 Circuit Boards (supply) + 5 Battery Cells (supply) + 4 Display Panels (supply) + 5 Plastic Casings (supply) |
| Radio Direction Finder | 5 Bandwidth (service) + 5 CNC Parts + 6 Copper Stock (supply) + 5 Circuit Boards (supply) + 4 Display Panels (supply) |
| Optical Sorting Conveyor | 6 CNC Parts + 6 Drive Belts (supply) + 5 Optical Lenses (supply) + 5 Servo Motors (supply) + 5 Microcontrollers (supply) |
| Electric Grain Mill | 5 CNC Parts + 5 Electric Motors (supply) + 6 Stainless Mesh (supply) + 5 Steel Tubing (supply) + 5 Ceramic Pieces (supply) |
| Articulated Desk Magnifier | 5 Steel Brackets + 5 Springs (supply) + 5 Optical Lenses (supply) + 5 LED Arrays (supply) + 5 Steel Tubing (supply) |
| Battery Spot Welder | 5 Custom Mods + 6 Battery Cells (supply) + 4 Power Inverters (supply) + 6 Copper Stock (supply) + 5 Circuit Boards (supply) |
| Induction Melting Crucible | 5 Prototypes + 6 Copper Stock (supply) + 6 Ceramic Pieces (supply) + 5 Power Inverters (supply) + 6 Insulation (supply) |
| Instrumented Fermentation Vat | 5 Welded Frames + 5 Temperature Probes (supply) + 5 Pressure Valves (supply) + 6 Metal Sheets (supply) + 5 Microcontrollers (supply) |
| Automatic Coffee Brewer | 6 Roasted Beans + 5 Water Pumps (supply) + 5 Heating Elements (supply) + 6 Copper Stock (supply) + 5 Microcontrollers (supply) |
| Electric Food Mixer | 5 Spare Parts + 5 Steel Brackets + 5 Electric Motors (supply) + 6 Metal Sheets (supply) + 5 Food-Safe Containers (supply) |
| Automatic Label Applicator | 6 CNC Parts + 5 Servo Motors (supply) + 6 Paper Sheets (supply) + 5 Drive Belts (supply) + 5 Microcontrollers (supply) |
| Music Roll Puncher | 5 CNC Parts + 5 Servo Motors (supply) + 6 Paper Sheets (supply) + 5 Clockwork Gears (supply) + 5 Metal Sheets (supply) |
| Miniature Automaton Theater | 5 Prototypes + 6 Servo Motors (supply) + 6 Textile Cloth (supply) + 6 Wooden Boards (supply) + 5 LED Arrays (supply) |
| Desktop Jacquard Loom | 5 Tooling + 6 Servo Motors (supply) + 6 Textile Cloth (supply) + 6 Wooden Boards (supply) + 6 Fiber Bundles (supply) |
| Immersive Flight Simulator | 6 Prototypes + 6 Compute Hours (service) + 6 Display Panels (supply) + 6 Servo Motors (supply) + 6 Welded Frames |
| Quantum Computer Cabinet | 6 Compute Hours (service) + 8 Quantum Cores (supply) + 8 Cryogenic Coolant (supply) + 6 Superconducting Coils (supply) |
| Fusion Containment Torus | 6 Peak Power (energy) + 8 Superconducting Coils (supply) + 6 Plasma Igniters (supply) + 6 Radiation Shields (supply) |
| Cryogenic Electron Microscope | 6 Prototypes + 8 Cryogenic Coolant (supply) + 6 Superconducting Coils (supply) + 4 Radiation Shields (supply) |
| Photonic Supercomputer | 6 Compute Hours (service) + 12 Photonic Processors (supply) + 8 Metamaterial Tiles (supply) + 6 Cryogenic Coolant (supply) |
| Ion Thruster Assembly | 6 Prototypes + 8 Plasma Igniters (supply) + 6 Superconducting Coils (supply) + 6 Radiation Shields (supply) |
| Magnetic Levitation Sled | 6 CNC Parts + 6 Superconducting Coils (supply) + 4 Cryogenic Coolant (supply) + 4 Precision Gyroscopes (supply) |
| Orbital Laser Communications Terminal | 6 Satellite Bandwidth (service) + 6 Photonic Processors (supply) + 6 Optical Lenses (supply) + 4 Precision Gyroscopes (supply) |
| Planetary Radar Array | 6 Telemetry (service) + 4 Superconducting Coils (supply) + 6 Photonic Processors (supply) + 12 Metal Sheets (supply) |
| Solar Sail Probe | 6 Ground Time (service) + 12 Metamaterial Tiles (supply) + 6 Precision Gyroscopes (supply) + 4 Photonic Processors (supply) |
| Deep-Space Navigation Core | 6 Telemetry (service) + 6 Quantum Cores (supply) + 8 Precision Gyroscopes (supply) + 6 Radiation Shields (supply) |
| Cryogenic Sample Vault | 6 Cold Storage (service) + 12 Cryogenic Coolant (supply) + 6 Radiation Shields (supply) + 12 Metal Sheets (supply) |
| Robotic Exoskeleton | 6 Prototypes + 12 Linear Actuators (supply) + 6 Precision Gyroscopes (supply) + 8 Metamaterial Tiles (supply) |
| Orbital Docking Collar | 6 Ground Time (service) + 12 Linear Actuators (supply) + 6 Precision Gyroscopes (supply) + 8 Radiation Shields (supply) |
| Plasma Glass Furnace | 6 Peak Power (energy) + 8 Plasma Igniters (supply) + 6 Radiation Shields (supply) + 12 Ceramic Pieces (supply) |
| Vacuum Deposition Chamber | 6 Prototypes + 4 Superconducting Coils (supply) + 6 Cryogenic Coolant (supply) + 6 Metamaterial Tiles (supply) |
| Atomic Frequency Standard | 6 Compute Hours (service) + 4 Quantum Cores (supply) + 4 Superconducting Coils (supply) + 6 Cryogenic Coolant (supply) |
| Gravitational Wave Interferometer | 6 Prototypes + 6 Photonic Processors (supply) + 12 Optical Lenses (supply) + 8 Metamaterial Tiles (supply) |
| Particle Beam Injector | 6 Prototypes + 8 Superconducting Coils (supply) + 6 Plasma Igniters (supply) + 8 Radiation Shields (supply) |
| Neutrino Detector Vessel | 6 Compute Hours (service) + 6 Photonic Processors (supply) + 8 Cryogenic Coolant (supply) + 8 Radiation Shields (supply) |
| Aerogel Capture Capsule | 6 Ground Time (service) + 8 Metamaterial Tiles (supply) + 6 Radiation Shields (supply) + 4 Precision Gyroscopes (supply) |
| Superconducting Power Buffer | 6 Utility kWh (energy) + 8 Superconducting Coils (supply) + 8 Cryogenic Coolant (supply) + 12 Power Inverters (supply) |
| Quantum Entanglement Bench | 6 API Calls (service) + 8 Quantum Cores (supply) + 6 Photonic Processors (supply) + 12 Optical Lenses (supply) |
| Adaptive Optics Mirror | 6 Telemetry (service) + 10 Metamaterial Tiles (supply) + 12 Linear Actuators (supply) + 4 Photonic Processors (supply) |
| Rotating Space Habitat | 6 Ground Time (service) + 8 Precision Gyroscopes (supply) + 12 Radiation Shields (supply) + 10 Metamaterial Tiles (supply) |
| Autonomous Cargo Capsule | 6 Container Slots (service) + 6 Precision Gyroscopes (supply) + 8 Radiation Shields (supply) + 4 Photonic Processors (supply) |
| Ocean-Floor Observatory | 6 Bandwidth (service) + 8 Metamaterial Tiles (supply) + 6 Photonic Processors (supply) + 4 Precision Gyroscopes (supply) |
| Precision Wind Tunnel | 6 Wind kWh (energy) + 6 Metamaterial Tiles (supply) + 8 Linear Actuators (supply) + 4 Photonic Processors (supply) |
| Photonic Encryption Router | 6 API Calls (service) + 8 Photonic Processors (supply) + 4 Quantum Cores (supply) + 6 Metamaterial Tiles (supply) |
| Space Elevator Climber | 6 Prototypes + 10 Metamaterial Tiles (supply) + 12 Servo Motors (supply) + 6 Precision Gyroscopes (supply) |
| Deep-Space Observatory Satellite | 6 Satellite Bandwidth (service) + 8 Photonic Processors (supply) + 10 Radiation Shields (supply) + 8 Precision Gyroscopes (supply) |

## Crafting supplies

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
| Ball Bearings | 14 YM |
| Electric Motors | 32 YM |
| Motion Sensors | 26 YM |
| Optical Lenses | 22 YM |
| Microcontrollers | 38 YM |
| Permanent Magnets | 12 YM |
| Water Pumps | 30 YM |
| Pressure Valves | 16 YM |
| Flexible Hoses | 8 YM |
| Wire Spools | 10 YM |
| Ceramic Pieces | 8 YM |
| Filter Cartridges | 14 YM |
| Textile Cloth | 7 YM |
| Hinges | 9 YM |
| LED Arrays | 18 YM |
| Speaker Cones | 14 YM |
| Display Panels | 30 YM |
| Clockwork Gears | 20 YM |
| Paper Sheets | 3 YM |
| Leather Straps | 10 YM |
| Heating Elements | 24 YM |
| Foam Padding | 5 YM |
| Sealant | 6 YM |
| Resin | 11 YM |
| Steel Tubing | 18 YM |
| Aluminum Profiles | 16 YM |
| Stainless Mesh | 12 YM |
| Cork Sheets | 7 YM |
| Bamboo Slats | 8 YM |
| Felt Sheets | 6 YM |
| Silicone Molds | 10 YM |
| Food-Safe Containers | 9 YM |
| Pigments | 8 YM |
| Adhesive Tape | 5 YM |
| Zippers | 7 YM |
| Buckles | 9 YM |
| Springs | 12 YM |
| Drive Belts | 14 YM |
| Servo Motors | 120 YM |
| Linear Actuators | 180 YM |
| Temperature Probes | 55 YM |
| Humidity Sensors | 48 YM |
| Solar Charge Controllers | 160 YM |
| Power Inverters | 240 YM |
| Superconducting Coils | 4500 YM |
| Cryogenic Coolant | 2500 YM |
| Photonic Processors | 5000 YM |
| Quantum Cores | 5000 YM |
| Precision Gyroscopes | 2200 YM |
| Metamaterial Tiles | 1800 YM |
| Plasma Igniters | 3500 YM |
| Radiation Shields | 3000 YM |

## Art and verification

Existing artwork is retained. Five additional 30-item sheets and new supply sheets extend the catalog to 300 items and 64 supplies. `craft-art.js` maps stable icon indices to their sheet and display bounds. Art provenance is documented in [assets/craft/ART.md](assets/craft/ART.md).

The latest append order and appearance descriptions are recorded in `previews/craft_expansion_300_catalog.json`, its five batch files, and `previews/craft_expansion_64_supplies.json`. Earlier expansion manifests are retained. These are authoring manifests, not runtime dependencies.

`tests/test_crafting.py` checks all 300 recipes, business/supply coverage, original 150-item and 36-supply compatibility, migration with existing ownership, advanced supply costs, reservations, value conservation, validation, authentication, class pause, and duplicate/stale requests. `tests/ui_craft.cjs` exercises the ingredient dialog, supply purchases, crafting, and the one-screen responsive catalog through the real preview API.
