# Image prompts for the 15 buildings

Paste these into ChatGPT (or any image model). The order matters: generate
`farm` first, then keep going **in the same chat** so the model holds the style.

Save each result as `assets/buildings/<id>.png` — the id is in the heading, and
the game looks for exactly that filename.

---

## 1. Paste this once, at the top of the chat

> You are making a matched set of 15 building icons for a children's economy
> game. All 15 must look like they came from the same artist on the same day.
>
> **Style, identical for every image in this set:**
> high-resolution pixel art game asset, 16-bit arcade style, crisp hard pixel
> edges, no anti-aliasing, no blur. Three-quarter isometric view from slightly
> above, camera angle identical in every image. Single building centred in frame,
> sitting on a small oval base. Chunky readable silhouette, thick dark outline,
> soft light from the upper left, one clear shadow to the lower right. Limited
> warm palette: amber and gold highlights, deep blue-grey shadows, one bright
> accent colour per building. Friendly and inviting, bright, made for 10-year-old
> players — not grim, not photorealistic, no gore, no weapons.
>
> **Every image must have:** square 1:1 canvas, 1024x1024, transparent
> background, no text, no letters, no numbers, no logos, no UI frame, no border,
> no people, no watermark. The building fills about 80% of the frame.
>
> Confirm you understand, then wait for each building one at a time.

Then send the 15 prompts below, one message each.

---

## 2. The 15 buildings

Each line is the whole prompt. Prefix with "Same style, same angle, same palette,
same light. Now:" every time — that one sentence is what keeps the set matched.

**1. `farm.png` — Greenfield Farm**
> A small friendly red barn with a white trim roof, a grey grain silo beside it,
> a golden haystack, green grass base. Makes tomatoes, eggs and honey. The
> smallest and humblest building in the set.

**2. `fish_stall.png` — Harbor Fish Stall**
> A little wooden harbour fish stall on a short pier, blue-and-white striped
> awning, crates of fish on ice, a coil of rope, water lapping at the base.

**3. `roastery.png` — Copper Kettle Roastery**
> A cosy brick coffee roastery with a big copper roasting drum visible through
> an arched window, a warm glow inside, sacks of coffee beans stacked outside,
> a thin curl of steam from a chimney.

**4. `garage.png` — Tinker's Garage**
> A small repair garage with its roller door half open, a warm work light
> inside, a tyre stack, a red toolbox, a wrench sign on the wall, oil-stained
> concrete base.

**5. `workshop.png` — Ironworks Shop**
> A metalworking workshop with a tall brick chimney, an open forge glowing
> orange inside, steel beams stacked outside, sparks in the air, an anvil by
> the door.

**6. `solar_coop.png` — Rooftop Solar Co-op**
> A neighbourhood building with a flat roof covered in tilted blue solar panels
> catching the sun, a small battery cabinet on the roof, potted plants along the
> edge, bright and clean and cheerful.

**7. `cannery.png` — Meridian Cannery**
> A tidy food cannery with a curved corrugated roof, stacks of labelled tin cans
> on pallets outside, a conveyor visible through a wide window, a small loading
> dock.

**8. `machine_works.png` — Bluecollar Machine Works**
> A precision machine shop, cool grey and steel blue, big windows showing CNC
> machines inside, a stack of freshly machined parts in a crate, a blue neon
> accent light over the door.

**9. `turbine_field.png` — Windward Turbine Field**
> Three tall white wind turbines on a green grassy hill, blades caught in
> motion, a small control hut at the base, a few clouds, breezy and open.

**10. `generator.png` — North Grid Plant**
> A serious power plant: concrete cooling towers with white steam, thick
> transmission pylons and cables, a humming transformer yard, amber warning
> lights glowing.

**11. `relay_station.png` — Signal Relay Station**
> A tall red-and-white signal relay tower with dish antennas at several heights,
> a small equipment shed at its foot, a blinking aircraft light at the top, a
> faint ring of signal waves.

**12. `freight_terminal.png` — Atlas Freight Terminal**
> A freight terminal with a gantry crane lifting a shipping container, colourful
> stacked containers, a refrigerated trailer, painted lane markings on the
> ground.

**13. `data_center.png` — Node-7 Data Hub**
> A windowless modern data centre, cool blue and teal, rows of server racks with
> tiny status lights glowing through a glass entrance, cooling fans on the roof,
> a soft blue ambient glow.

**14. `solar_array.png` — Helios Solar Array**
> A large utility solar farm: a wide field of angled mirror-blue panels in neat
> rows, a white inverter station with a sun emblem, warm golden sunlight
> reflecting off the whole array.

**15. `uplink_center.png` — Orbital Uplink Center**
> A futuristic satellite uplink centre: a huge white parabolic dish tilted at the
> sky, a sleek control building with teal lit panels, a lattice mast with a
> beacon, a faint beam of light rising from the dish. The grandest building in
> the set.

---

## 3. After each image

1. **Check the four rules**: square, transparent, no text, same angle as #1. Ask
   for a redo if any is off — "same building, same style, but transparent
   background and no text" usually fixes it in one go.
2. **Save as** `assets/buildings/<id>.png`, using the exact filename above.
3. The game picks it up on the next page refresh. No code change needed.

## 4. If transparency fails

Image models often ignore "transparent background" and give you white or a flat
colour. If that happens, ask instead for:

> flat solid magenta background, #FF00FF, absolutely no other magenta anywhere
> in the image

and say the word — there is a helper script ready to cut that colour out and
resize everything to 512x512 with crisp pixel edges.

## 5. Keeping the set consistent

The single biggest factor is staying in one chat and repeating "same style, same
angle, same palette, same light". If the model drifts after a few images, paste
the style block from section 1 again, or attach `farm.png` and say "match this
exactly".

The buildings should also **grow** through the list: #1 is a little barn, #15 is
a satellite complex. If an early building comes out looking too grand, it steals
the sense of progression — ask for "smaller, humbler, more modest".
