# Building art

## Animated Build page

Build uses the 15 supplied transparent sprite strips from
`animated_buildings_all.zip`. The filenames match every tier ID in
`config/economy.v1.json`:

```
assets/buildings/spritesheets/<tier id>_8f.png
```

Each strip is 4096 × 512 pixels: eight horizontal 512 × 512 frames, played
at 120 ms per frame. CSS displays one frame at a time without changing the
source artwork. The Animate toggle pauses or resumes the art; paused classes
and reduced-motion preferences also stop it. The transparent background keeps
Dash's black surface visible. Replace the matching strip to update a building.

The legacy PNG remains a loading fallback. Other economy pages still use those
PNGs. Missing artwork falls back to the building's initial.

## Legacy static images

One image per building. The game builds the path from the building's id in
`config/economy.v1.json`:

```
assets/buildings/<tier id>.png
```

Nothing needs to be registered anywhere. Drop the file in, refresh the page.
A building with no file shows a neutral placeholder instead of breaking.

| # | File | Building |
|---|---|---|
| 1 | `farm.png` | Greenfield Farm |
| 2 | `fish_stall.png` | Harbor Fish Stall |
| 3 | `roastery.png` | Copper Kettle Roastery |
| 4 | `garage.png` | Tinker's Garage |
| 5 | `workshop.png` | Ironworks Shop |
| 6 | `solar_coop.png` | Rooftop Solar Co-op |
| 7 | `cannery.png` | Meridian Cannery |
| 8 | `machine_works.png` | Bluecollar Machine Works |
| 9 | `turbine_field.png` | Windward Turbine Field |
| 10 | `generator.png` | North Grid Plant |
| 11 | `relay_station.png` | Signal Relay Station |
| 12 | `freight_terminal.png` | Atlas Freight Terminal |
| 13 | `data_center.png` | Node-7 Data Hub |
| 14 | `solar_array.png` | Helios Solar Array |
| 15 | `uplink_center.png` | Orbital Uplink Center |

**Format:** square PNG, transparent background, 512x512 or 1024x1024. The page
renders it at 168px, so anything above 512 is only useful for future zoom.

**Prompts to generate these:** see `PROMPTS.md` in this folder.

Four files are placeholders copied from `assets/buildings-icons/` so the screens
have something to show — `farm`, `workshop`, `generator`, `data_center`. They are
painted icons, not pixel art, so replace them along with the rest if you want one
consistent style.

## Farm and roastery improvements

The current game selects static `upgrades/<id>-level-3.png` and
`upgrades/<id>-level-6.png` for farm/roastery once the highest production, customer
or storage level reaches that threshold. Original animation strips are retained
for base-level buildings and other businesses. New images have black backgrounds
matching the game surface and are rendered with object-fit contain.

See [comparison gallery](../../previews/progression-art.html) and
[prompts](upgrades/prompts.json). These assets were created with built-in
image_gen and copied into this project; they do not depend on the generation
cache. The other thirteen buildings retain their existing artwork.
