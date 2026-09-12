# Regular customer emotes

Seventeen original character sheets generated with the built-in ImageGen tool.
Every customer in `production_economy.CUSTOMER_CATALOG` has a matching
`<customer_id>_16f.png`. All sheets are 1254 × 1254 pixels; the game uses
proportional clipping, so the four columns and four rows remain aligned.

Portraits use larger responsive windows and measured framing for each emote.
Each framing includes all four poses in that row, keeps hands and props visible,
and stays inside a single sprite cell. The original PNGs remain unchanged.

Every unlocked slot has a portrait in the same roster, showing all four customers
together when the fourth slot is unlocked. Portraits select the details below;
each signed customer's emote follows their own shipment state. Open slots show
distinct candidates marked Preview, and signing still requires the Sign button.
The roster uses the space left after the shipment controls, with portraits sized
to their tiles. It uses two columns on desktop and phones, and four across on
tablets and short screens, preserving the terminal colors and pixel rendering.

| Row (zero based) | Meaning | In the game |
| --- | --- | --- |
| 0 | Signature work or greeting gesture | Customer chooser and active shipments |
| 1 | Patient waiting | A shipment is due and goods are missing |
| 2 | Thank-you celebration | Delivery count increases for the same contract; lasts 4.8 seconds |
| 3 | Resting, eyes closed | Customer or class paused; first resting frame stays still |

Each row has four distinct poses: facial expressions, hands and job-related
props change. Character gestures include inspecting tomatoes, whisking eggs,
toasting a coffee, testing a battery, packing cans and lifting a satellite.

The game never invents a shipment to show a celebration. First load, signing,
switching and changing order size do not replay historical deliveries.
The Motion control and reduced-motion preference stop playback. Existing
customer names, prices, requirements, controls and saved contracts are retained.

Exact initial and framing-correction prompts are preserved in:

- [Food and hospitality prompts](prompts-food.json)
- [Industry and community prompts](prompts-industry.json)
- [Technology and transport prompts](prompts-tech.json)

Run the isolated preview with every customer available:

```sh
python3 previews/customer_emotes_preview.py 3088
```

Open `http://127.0.0.1:3088/marketplace.html`. It uses a temporary town with
all businesses available; real saves are untouched. Choose a customer in an
open slot to preview their character, then sign them to try the real shipment,
pause and resume behavior. On a narrow screen, select the Contracts tab.

Validation: `node tests/ui_customer_emotes.cjs http://127.0.0.1:3088` checks all
17 sheets, actual frame clipping, four simultaneous portraits, independent
delivery-triggered thanks, persistent selection, motion preferences, missing-art
fallback and customer layouts without footer overlap at five sizes.
