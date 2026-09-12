# YoMama Game Design Review

## 1. The design decision

**Build the game around running a small business that can reliably serve its customers.** Its strongest idea is already present: the same goods can be sold, promised to a buyer, or used by another business. Choosing where those goods go, seeing the result, and improving the limiting part of the operation can support both satisfying play and economic thinking.

The current game has enough systems to develop that idea. Its immediate problem is coherence. A beginner must discover the important decisions across several screens, distinguish overlapping customer systems, interpret income figures with different meanings, and find a reason to progress beyond buying the next affordable improvement. Additional content would not resolve those problems.

The recommended player promise is: **“Grow a business you understand. Choose whom to supply, improve your operation, and turn a small farm into a connected neighborhood.”** A lesson should end with an accomplishment the player can explain, rather than an arbitrary cash total or access to an unrelated terminal.

The five most consequential proposals are:

1. Make production, allocation, and earnings visible together. A good choice must produce understandable feedback.
2. Replace unlimited jackpot hunting with a small set of economically different opportunities.
3. Build a deliberate first session around the farm, fish stall, and roastery. Each introduces a different problem.
4. Consolidate the overlapping breakfast systems. Use real town customers and goods for the main breakfast challenge; remove its separate event coins and supply system from the required opening.
5. Move the finance terminal, paper trading, analyst demos, and obsolete chat outside the beginner town experience. Investing can remain a separate, explicitly introduced lesson.

This is a design proposal. No game-code changes are part of this review. The working assumption is secondary-school learners in a 35–45 minute lesson, with later visits. If the intended audience is instead experienced players seeking a long-running idle empire, the timing and progression structure should change; the feedback and incentive problems still apply.

**“Everything has a purpose” should include emotional purpose.** The pixel art, evolving buildings, recognizable customers, humor, and arcade standings can create identity, anticipation, and pride. MDA explicitly treats experienced qualities such as expression, fantasy, fellowship, and sensory pleasure as legitimate design objectives.[^1] Keep the personality. Remove rules, panels, and chores whose attention cost exceeds what players gain from them.

The strongest evidence here is about what the rules do and what information the interface provides. Enjoyment and learning remain hypotheses until representative students play. Published research guides the choices; it does not certify this particular game as fun.

Measurements refer to the preserved audit baseline. Concurrent order-catalog changes arrived before delivery; the appendix distinguishes those additions from the rules that produced the reported timing and strategy results.

## 2. What is actually playable now

The current town starts with one farm, no cash, and automatic production. Tomatoes, eggs, and honey have different production cadences. Walk-in demand initially buys less than the farm can produce, so some stock accumulates. Players can improve production, customers, or storage; direct goods toward orders; sign recurring customers; and buy additional businesses. Some businesses consume other products as ingredients. Prices are fixed. There is no ordinary operating-cost, bankruptcy, or dynamic market-price system in the v4 town. (C1)

That creates two loops:

| Loop | Actual sequence | Design implication |
| --- | --- | --- |
| Automatic economy | Produce goods → consume recipe inputs → supply due regular customers → sell available goods to walk-ins → accumulate cash and inventory | This is the simulation. It removes collection chores but does not itself provide a player decision. |
| Player activity | Inspect status → buy an improvement or expansion → manage an order/customer → wait or visit another screen → inspect again | This becomes a game when the choice is understandable and alternatives have different consequences. |

The first two businesses already offer a useful contrast. The farm makes raw goods. The fish stall introduces a recipe within one business: fresh catch becomes smoked fish. The roastery then introduces a connection between businesses: farm eggs and honey become pastries, while roasted beans become espresso. These are three teaching opportunities with a natural sequence. (C1)

The town also has three different systems that sound related: **Breakfast regulars** on the one-time order board, **Regular customers** with automatic repeat shipments, and **Breakfast Club**, a separate manual cooking activity. They have different inventories, timing, rewards, and controls. A beginner can reasonably confuse them. The cooking event teaches “press Make,” while the town makes goods automatically. (C2, C3)

The licence requires three buildings, a production milestone, a customer upgrade, a quiz, and either three manual deliveries or 100 goods sold to walk-in customers. Automatic regular-customer shipments do not count toward either experience requirement. Its reward leads to a separate practice portfolio. It does not reinvest town earnings into the displayed trading desk. The disclosure is present, but the progression still changes the player's activity and economic context abruptly. (C4)

Direct joining normally lands on Build. Entering through the site root can return the player to the finance-heavy Dash after sign-in. The surrounding navigation exposes several surfaces that do not influence town production. In the current town, prices remain fixed and the economic event/news payload is empty; ordinary financial news does not change egg demand or pastry prices. (C1, C5)

The intended introductory learning should therefore be specific: **production capacity, customer demand, inventory allocation, opportunity cost, processing, and investment timing.** Do not imply that the current model teaches market price formation, realistic profit accounting, or portfolio performance simply because those words and screens exist elsewhere.

## 3. What the evidence revealed

### A beneficial decision can look harmful

The main income calculation adds recent walk-in retail receipts. It excludes recurring-customer receipts. The individual business labels do say “Shop income · last minute,” but the town-level figure and upgrade estimates do not explain the complete business outcome. Accepting a useful regular customer can reduce the displayed shop income while increasing actual total cash earned. (C1, C2)

The following controlled experiment held the farm at its initial production, customer, and storage levels. It used 120 minutes of warm-up followed by a 120-minute measurement window. Larger contracts were taken only after their actual three-delivery unlock. These are fixed-configuration measurements, not a claim about a novice's first two hours.

| Farm arrangement | Walk-in receipts, YM/min | Regular receipts, YM/min | Total receipts, YM/min |
| --- | ---: | ---: | ---: |
| No regular customers | 15.60 | 0.00 | 15.60 |
| Corner Grocer and Sunrise Diner | 9.87 | 14.17 | 24.03 |
| Same customers with larger orders | 5.20 | 22.00 | 27.20 |

The more productive arrangement can make the visible shop-sales component much smaller. This is a priority design defect: the feedback can teach the opposite of the actual result. Capacity forecasts also omit regular-customer allocation. Exact short-window income additionally fluctuates because goods and payments arrive in whole batches. (E1)

### The opening does not reliably reach its most interesting problem

In a continuous 45-minute simulation, using the existing seed-7 rules and transparent policies, saving for expansion opened the fish stall at minute 9.5 and the roastery at minute 25. The policy that repeatedly selected affordable upgrades with positive estimated retail benefit opened the fish stall at minute 21 and had only two businesses at minute 45. Neither policy used recurring customers, specialties, or the cooking event. (E2)

| 45-minute policy | Businesses | Upgrade purchases | Manual deliveries | End cash | Engine net worth |
| --- | ---: | ---: | ---: | ---: | ---: |
| Save for expansion | 3 | 2 | 4 | 1,480 YM | 3,026 YM |
| Favor beneficial upgrades | 2 | 21 | 4 | 304 YM | 3,352 YM |
| Favor supply deliveries and upgrades | 2 | 23 | 17 | 187 YM | 4,040 YM |

There is no universally correct policy established by this table. It shows that the interface can support long sequences of purchases without reliably reaching the cross-business lesson. A natural-looking choice can delay the intended learning for an entire class.

A simpler comparison makes the bottleneck clear. Over 45 minutes, the idle farm earned 698 YM from retail. Buying only its first production upgrade still produced 698 YM of retail receipts; buying only its first customer upgrade produced 922 YM. More production created more inventory, which has value, but did not increase these sales. The distinction must be visible before purchase. (E2)

### Later activity can become poorly rewarded repetition

The existing 14-day simulation gives players a ten-minute initial visit and five-minute visits every two hours; its casual policy visits every twelve hours. It does not use the new regular customers, specialties, cooking event, or reroll hunting. In the upgrade-versus-supply-delivery comparison, both policies ended with eleven businesses and 206 upgrades. The delivery policy performed 676 manual deliveries versus one, for approximately 83.29 million versus 81.85 million engine net worth: about **1.76% more for 675 additional deliveries**. (E3)

This is not proof that orders are always weak. It is evidence that this particular repeated task can become a poor use of player attention as progression advances. Orders should remain useful because they advance a chosen plan, rather than requiring hundreds of nearly identical confirmations.

### Rerolls change the incentive to play

Orders have nominal rarity probabilities of 65% standard, 25% large, 8% rare, and 2% jackpot. Replacements cost nothing and have no cooldown. Rare tiers increase quantities and the reward premium. Goods still must be produced and delivered; the issue is the strategy the replacement rule encourages. (C1)

Across twenty paired starting seeds, a matched 45-minute comparison held purchasing, fulfillment, and order commitment behavior constant. Allowing at most one replacement every 15 seconds increased mean engine net worth by **8.9%**, with an average of **138 replacements**; it outperformed the no-replacement plan in 15 of 20 seeds. Allowing four increased mean net worth by **37.7%**, averaging **377 replacements**, and won 19 of 20 comparisons. The higher rate is a search-intensity test, not a recommended human workload. (E4)

Earlier illustrative comparisons also changed reservation behavior; their larger combined gains are not used to attribute the effect of rerolling. The matched experiment isolates the replacement rule. It does not prove that every replacement helps or that this is globally optimal play.

The design concern exists even without a universal optimum: attention can shift from selecting a production plan to advancing an offer sequence. Soren Johnson's account of efficient but tedious Civilization strategies provides a relevant developer precedent for treating this as a rules problem.[^2]

## 4. The recommended main loop

**Notice a customer need → choose a plan → allocate goods → see the result → improve the bottleneck → take on a new challenge.**

The automatic make–sell cycle should keep the town alive underneath that loop. The player should spend attention on a changing decision, not on repeatedly authorizing the same sale.

| Step | Concrete player question | What the game must reveal |
| --- | --- | --- |
| Notice | “What is my business trying to achieve?” | One current outcome: serve a buyer, open a business, or resolve a named shortage. |
| Choose | “Which of these useful options fits my plan?” | Comparable goods, timing, payout, and effect on other buyers. |
| Allocate | “Where should these eggs go?” | Available stock and what will be reserved or diverted. |
| Observe | “Did my choice work?” | Cash and stock changes, delivery outcome, and the cause of a delay. |
| Improve | “What is limiting this plan now?” | Production, demand, or storage constraint tied to a specific product. |
| Extend | “What can I do now that I could not do before?” | A new buyer, recipe relationship, or meaningful specialty. |

A good recurring example is a roastery that needs honey. The player can improve the farm, favor bakery supplies, serve a smaller pastry order, choose a coffee-oriented customer, or temporarily sell ingredients. The game should make at least two reasonable responses understandable. The correct response depends on the player's goal and constraints.

The choice needs a consequence, not necessarily a punishment. A customer who waits can still create opportunity cost by occupying a slot and tying up goods. Keep forgiving behavior while testing whether customer selection really changes with the state of the town. Avoid adding fines merely to make the system appear strategic.

Use three rhythms:

- **Immediate:** a button responds, stock moves, and the purchase or reservation is explained.
- **Short:** a shipment, improvement, or small construction project pays off while the player can still remember the decision.
- **Session:** the town gains a capability and the player can explain what they achieved.

Do not require constant clicking. Time spent comparing options, noticing a problem, or anticipating a visible delivery can be worthwhile. Valve's published pacing work supports alternating demands and recovery as a design pattern, but supplies no universal classroom timer.[^3] The timing targets below are proposals for testing.

The educational logic should live inside the decisions. Research on intrinsic integration found advantages when the taught mathematics was part of playing a particular educational game rather than attached as separate questions; that result is relevant guidance, not a guarantee for economic simulations.[^4] In YoMama, success should require recognizing the bottleneck, allocating scarce goods, or comparing investments.

## 5. A concrete first 45 minutes

The first-session goal should be **“Open your neighborhood breakfast business and keep a customer supplied.”** For a 35-minute lesson, the explicit completion is a working farm-to-roastery chain and one completed customer shipment, followed by a short explanation. Defer the larger breakfast challenge and alternate-plan experiment. If the fish lesson crowds that shorter opening, make it an optional route or a later example rather than rushing every beat.

The opening should reveal complexity by demonstrated understanding. It should not force a tour of all five management pages. Contextual tutorials helped in a complex game in Andersen and colleagues' large tutorial study, while simpler games did not show the same benefits.[^5] Use brief help at the point of difficulty, with an option to skip instruction.

| Target time | Playable beat | Decision and visible outcome |
| --- | --- | --- |
| 0:00–1:00 | Meet the farm and one neighbor | Show tomatoes appearing and a real sale. Explain automatic production. Present one small, feasible order and a session goal. The player directs the first goods; no long introduction. |
| 1:00–4:00 | Fix the first bottleneck | Show goods accumulating because customer capacity is lower than output. Compare a customer improvement with more production. Make the useful first improvement affordable through the opening sale or explicit starter capital. Show why it helps. |
| 4:00–7:00 | Choose a use for stock | Offer a quick small payout and a larger supply commitment with a different payoff. Save only the chosen quantities. Show walk-in earnings continuing on unreserved goods. |
| 7:00–11:00 | Open the fish stall | Show what it produces and its one internal recipe before construction. Give a short build interval that can overlap the order already underway. Reveal the relationship between fresh and smoked fish. |
| 11:00–17:00 | Choose growth or a steady customer | Offer a real tradeoff between improving the current operation and saving toward the roastery. Introduce one recurring-customer slot after a manual shipment is understood. Explain the first interval and show the first automatic payout. |
| 17:00–24:00 | Open the roastery and connect suppliers | Show beans → espresso and eggs + honey → pastries. Name the limiting ingredient. Let the player change the supplier, product focus, or buyer instead of blindly upgrading the roastery. |
| 24:00–34:00 | Run the breakfast challenge | Use real town stock and a small set of customer needs. Finish a few distinct decisions, not a quota of identical deliveries. Reward a lasting capability in the town. |
| 34:00–40:00 | Try a different operating plan | Compare coffee and pastry emphasis or small and large recurring orders. Give a reversible choice and enough time to observe at least one consequence. |
| 40:00–45:00 | Finish, explain, and plan | Show the completed neighborhood goal, earnings by source, and one decision that mattered. Ask a short transfer question. Offer optional LEAD comparison and one clear next-session objective. |

These timings require a revised opening economy or a carefully prepared lesson scenario. They are **not** what the current prices guarantee. In particular, the current ordinary expansion policy reaches the roastery near minute 25, while some upgrade paths do not reach it during the lesson. Change the affordability and milestone sequence before multiplying every production rate or accelerating the entire class clock.

Different viable investment branches must still reach the lesson goal within the shared window, or earn an equally valid operating accomplishment. Otherwise the timetable would penalize the agency it is meant to create. Observe alternative paths before making a particular building the only definition of success.

An integrated breakfast challenge must respect existing recipe buffers, saved orders, and regular buyers. Before starting, show which goods are already promised and let the player release or pause conflicting commitments. A shortage should name its cause and offer a safe recovery. Moving the challenge into the town must not create another opaque reservation system.

The first order should be authored and feasible. Randomly starting with a large honey demand can make “Quick cash” mean prolonged waiting. First-time success should demonstrate the normal rules, using an explicitly introduced starter order or capital rather than hidden free goods or silent rule changes.

Help should respond to the misconception. If the player buys production while demand is limiting sales, show the extra inventory and explain why receipts did not rise. Allow a recovery through the next useful choice. Do not turn the opening into a sequence where only the highlighted button is permitted.

Three moments should feel different: **I earned something; I understood something; I built something new.** Repeating a cash animation cannot substitute for all three.

## 6. Later sessions and the endgame

The fifteen-business collection can remain a long-term aspiration, but the required progression should be organized around new decisions. Current later businesses mostly retain the same three-product, three-upgrade structure. Different names and larger numbers can support collection, yet they do not automatically create another lesson. (C1)

| Stage | Existing businesses to draw from | New decision that would justify the stage |
| --- | --- | --- |
| Neighborhood | Farm, fish stall, roastery | Distinguish supply and demand; convert goods; allocate inputs between buyers. |
| Workshop district | Garage, workshop, cannery, machine works | Choose between improving a supply chain and opening a parallel source of income; share an input between useful outputs. |
| Utilities | Solar co-op, turbine field, generator, solar array | Allocate a common input across business customers. Keep only distinct roles; do not imply weather, outages, or time-of-day rules that are absent. |
| Connected services | Relay station, freight terminal, data center, uplink center | Plan a multi-business dependency and satisfy a finite district objective. Avoid merely repeating the early purchase routine at higher prices. |

This is a proposed progression structure, not a description of fully distinct current district mechanics. Several existing recipes only weakly express the proposed roles. Prototype one district after the opening works; do not build four new feature sets at once.

After the first lesson, increase the interaction between known rules before introducing more rules. A new buyer can compete for honey previously used by pastries. A larger customer can need more than the farm currently produces. A new business can use an existing surplus. These situations generate different decisions without adding debt, a second currency, or a new interface.

A later lesson should have a finite objective with more than one solution. For example: “Maintain two regular customers while completing one neighborhood order.” Define the measurement interval visibly. The player might expand production, change the buyer mix, or choose a different order. Completion should acknowledge the strategy, reveal a useful next capability, and allow continued sandbox play.

Long construction timers make sense only when there is useful parallel planning and an understandable return. Current late construction reaches several hours, and baseline incremental retail payback rises from minutes for the fish stall to hundreds of active production hours for late businesses. Those estimates exclude upgrades, regular customers, orders, and changing bottlenecks; they diagnose a long-horizon structure, not the optimal investment path. (E5)

For classroom mode, use chapter-scale milestones and visible progress within the lesson. Long-term sandbox progress can persist between classes, but should not be required for that lesson's success. Do not add a prestige reset or endless level ladder merely because the town eventually finishes. A satisfying ending is a feature.

Factorio's developers describe routine late-game maintenance and short-lived investments as causes of stagnation, and discuss shifting effort toward durable infrastructure.[^6] Apply the principle here by letting a mastered delivery relationship automate itself. Later play should ask a new planning question rather than ask the player to reconfirm yesterday's answer.

## 7. What stays, changes, or leaves

“Remove” below means a proposed product decision, not a deletion performed during this review. A feature can leave the beginner experience while remaining available as a separate lesson or developer tool.

| Feature | Decision | Purpose and proposed treatment |
| --- | --- | --- |
| Automatic production and walk-in sales | Keep | Provides a stable baseline and removes collection chores. Show named goods and actual outcomes. |
| Different production cadences | Keep | Makes supply planning matter. Reveal product rates when needed. |
| Processing chains | Keep and strengthen | Creates opportunity cost and bottlenecks. Display inputs, output, timing, and affected buyers together. |
| Production upgrades | Keep | Useful when supply limits a chosen plan. Reveal effects on customers and recipes before purchase. |
| Customer-capacity upgrades | Keep; clarify name | Call them “Walk-in customers” or equivalent so they are distinct from recurring buyers. |
| Storage upgrades | Defer in the opening | Useful for capacity and commitments, often weak as a first purchase. Introduce when a named shelf or planned order needs room. |
| Building expansion | Keep; stage the choices | Preview outputs, dependencies, cost, and the decision it unlocks. Remove unexplained early access to distant branches. |
| One-time orders | Keep; simplify | Useful tactical choices about stock and timing. Start with one feasible order, then a few distinct alternatives. |
| Free unlimited rarity rerolls | Replace | Remove the incentive to search repeatedly for a superior multiplier. Present comparable jobs; refresh on meaningful progress or a clear schedule. |
| Rare-order presentation | Optional flavor | Surprise and spectacle can stay if availability is not earned through repetitive clicking. Do not make rarity the main reason to choose a job. |
| Order-specific saving | Keep | Bounded allocation is a strong central action. Show what it affects and how to release it. |
| Regular customers | Keep; introduce later | Turns an understood shipment into useful automation. Show sustainable supply, expected earnings, and alternative uses of stock. |
| Larger recurring orders | Change the decision support | Show expected actual cadence at current output, not only the requested interval. A bigger promise need not always be the right plan. |
| Whole-business Hold goods | Move to advanced controls | It behaves differently from saving for an order. Label it “Pause walk-in sales”; explain that recipes can still use ingredients. |
| Sell surplus at a discount | Keep as secondary | Provides liquidity and frees space. Show the amount received and retail value given up; avoid turning it into routine collection. |
| Materials as a permanent currency | Remove from the preferred design | Currently behaves as a fixed-value construction coupon and an automatically purchased surcharge. Use a transparent cash cost; pay supply jobs in cash. Keep a named project requirement only when it creates a distinct decision. |
| Breakfast regulars order slot | Merge into customer progression | A recurring relationship should be understandable as one customer, rather than a third similarly named system. Preserve earned rewards in any eventual transition. |
| Separate Breakfast Club economy | Replace in the main path | Keep its finite challenge and upgrade choice, but use the town's goods and customer logic. Remove event coins and duplicate ingredient generation from the required opening. |
| Existing cooking activity as an elective | Conditional | It can remain a later optional minigame if players value manual scheduling for its own sake. Introduce it explicitly as a different activity and give it a distinct name. |
| Coffee/pastry and farm specialties | Keep; improve explanation | Reversible specialization supports agency. Show which outputs and customers benefit and which lose capacity. |
| Licence checklist | Replace with chapter goals | Buying a prescribed level does not demonstrate understanding. Recognize an operating accomplishment and a brief explanation. |
| Business concept questions | Keep; improve feedback | Ask about a played decision and revisit the concept. Explain errors; do not use one score as proof of mastery. |
| Town-to-PORT unlock | Remove as the main reward | The separate practice portfolio does not use town wealth. Introduce investing as a deliberate later module with its own purpose and progress. |
| Pixel art and visible building upgrades | Keep | Supports identity and visible achievement. Make art progression readable without adding unnecessary rules. |
| Original arcade LEAD page | Keep | Real class standings provide optional social context. Retain its established appearance and visible navigation. Put personal achievement elsewhere. |
| Finance-heavy Dash and market tickers | Move out of the beginner game | They do not change town decisions. A return dashboard should explain the town; the finance terminal can serve a separate research lesson. |
| Analysts with implied economy powers | Defer or label cosmetic | Current selection is not an authoritative v4 economic strategy. Character flavor is legitimate; unsupported promises are not. |
| Current CHAT | Remove from the town path | It reads obsolete local state and presents simulated social activity. It cannot reliably explain the current town. |
| Student-facing TEACH/demo dashboards | Remove from student primary navigation | Distinguish sample classroom tools from the actual teacher console. Coordinate any later change with the access/hosting owner. |
| Retired Produce, Collect, Focus tree and labs | Keep outside ordinary play | Preserve useful tools and old-link compatibility; stop presenting inactive mechanics as progression. |

The preferred materials cut is deliberately stronger than a label fix. When one token always substitutes for 15 YM and missing tokens are bought automatically during construction, the player is learning a conversion and bookkeeping rule without gaining much agency. Removing it also removes the board's current cash-versus-construction-saving distinction. Give supply jobs a distinct project purpose or merge them with ordinary orders; simply relabeling the reward would preserve redundant content. Do not replace materials with several new currencies.

Optional does not automatically mean harmless. A large study of secondary goals found that goals away from the main solution reduced progress in two games; the return-rate differences were not significant, and playtime effects varied.[^7] This supports testing whether a side activity strengthens the core experience, not banning side activities generally.

## 8. Economy rules that support good play

**Balance plans, not buttons.** A production upgrade, customer contract, and new business must be evaluated against the player's current constraints and time horizon. An individually attractive action can damage a chain or postpone the intended milestone.

Use three sale channels with plainly different roles: walk-ins for effortless baseline income; one-time orders for an active stock commitment; recurring customers for an ongoing operating plan. Once a player understands the distinction, managing those channels should replace repeated sale clicks.

For each offer, show the goods required, total payout, expected completion time under the current plan, and what those goods would otherwise do. “More than retail” is incomplete when the ingredients could create a more useful processed good or keep another customer supplied. Estimates should state their assumptions and update when the player changes allocation.

The early customer choices are currently close in value. With two larger farm contracts, the tested pairs all converged to 27.20 YM/min in the fixed farm configuration. That can be acceptable as a forgiving first choice or a preference between characters. It should not be presented as a deep economic puzzle. Later, the useful buyer should depend on the town's capacity, suppliers, and objective. (E1)

Keep waiting customers and reversible specialties. A shortage can cause a delayed payment and an opportunity to revise the plan without a fine. In the current rules, the larger tomato contract requests twelve tomatoes every two minutes while a level-one farm makes eight during that interval. It can still pay more by shipping later. Show the likely three-minute supply cadence alongside the buyer's two-minute request. The issue is understandable consequence, not the absence of punishment. (C1, E1)

Replace the jackpot search with a small deliberate choice set. A useful prototype offers a fast, small order and a larger commitment, with pricing based on the actual goods and production burden. Free skipping can remain, but repeatedly skipping should not be the best way to obtain an unusually favorable premium. A cooldown alone would turn the same search into waiting.

Make upgrades produce readable milestones. Retain quantitative improvement between milestones where useful, but do not require dozens of nearly identical purchases to reach the next interesting choice. Unlock a specialty or capacity decision at the point where the player can use it. Avoid a checklist that requires an economically unhelpful purchase merely to prove participation.

Treat net worth as a game metric with a stated definition. It currently equals cash plus retail-valued inventory plus book value, which includes the gifted farm's initial 100 YM and recorded purchase costs; materials are excluded. Unsold inventory can increase the score without increasing cash, and recorded spending remains in book value. That is not a realistic valuation model. If net worth remains the standings metric, explain it consistently and do not present it as a measure of learning or liquidation proceeds. (C1, C6)

Do not add price volatility, loans, taxes, staff wages, breakdowns, energy meters, or production tapping to solve the current boredom risk. Each would introduce new rules before the existing choices are legible. Add a system only when a specific player problem remains after the focused loop has been tested.

## 9. Information and feedback

Preserve the established three-column Build layout: business selection on the left, selected business in the center, and improvement/expansion controls on the right. The current composition can support the proposed loop. It does not require a town-tile replacement. (C2)

The center should answer four questions: **What am I making? Where is it going? What is limiting my plan? What did my last decision change?** It can show a compact product summary without duplicating every Warehouse control or moving the general order board onto Build.

| Current ambiguity | Proposed player-facing explanation |
| --- | --- |
| “Income” mixes an overall impression with shop-only receipts | “Earned in the last 5 minutes: walk-ins 52 YM, regular buyers 90 YM, one-time orders 0 YM.” Keep capacity forecasts separate. Numbers here are illustrative. |
| “Storage full” may mean one product shelf | “Honey shelf full: 60/60. Eggs and tomatoes still have room.” Show whether this blocks the chosen plan. |
| Warehouse stock differs from order “Have” | “10 eggs in stock: 6 saved for another order, 4 available.” Label order counts Available / needed. |
| “Customers” means an upgrade and a contract system | “Walk-in customers” and “Regular buyers.” Use the same names on mobile tabs. |
| Faster output is presented as an income improvement | “More eggs available; current buyers already receive enough. Useful for the pastry order.” |
| A recipe is waiting without an actionable cause | “Pastries need honey. Farm supply is below your planned use.” Show rates and a direct link to the supplier. |
| A larger contract quotes its requested interval | “Buyer requests every 2 min; your current supply supports about every 3 min.” |
| A new business is mostly a price and timer | “Produces espresso and pastries. Pastries use farm eggs and honey. Opening this business changes where those goods go.” |

These are wording and information-design examples, not proposed final numbers or promises that a forecast can be exact under changing reservations. A useful estimate is honest about its horizon and constraints.

Consolidate guidance. The engine supplies a first-farm “Upgrade customers” goal, while the interface has a separate heuristic that can recommend production merely because it is affordable. One consistent explanation should follow the chosen plan and real bottleneck. Guidance should say why, and show alternatives when appropriate. (C1, C2)

Mobile is a comprehension constraint as well as a layout constraint. The settled 390×844 layouts exposed their controls through panel tabs and pagination without document overflow in the inspected states. That solves fit, but a player may still need to remember an order while switching to inventory and recipes. Keep the selected task and relevant goods available across those transitions. Do not confuse “fits on screen” with “easy to understand.” (E6)

The finance wall should not act as ambient game feedback. Some panels use live or fetched values, others seeded or simulated values, and they are not the town's market. The issue is mixed provenance and relevance, not a claim that every financial figure is fabricated. Replace the beginner return view with completed construction, shipments, the current bottleneck, and the next chosen objective. (C5)

## 10. Classroom pacing, competition, and learning

The class clock and the learning session are different. Production uses a twelve-hour absence allowance, and construction follows class elapsed time. Longer or more frequent attendance can therefore affect the economy. Whether a class is paused between lessons also changes what players return to. The current live classes may retain different saved configurations. (C7)

For the recommended classroom mode, define a common lesson window and a clear completion condition. Give students a useful state at the start of the planned activity and enough shared time to observe its consequences. Do not make checking the game overnight a requirement for doing well in class. Optional persistent play can coexist with a lesson, but cumulative wealth should not determine the student's learning result.

Retain LEAD's arcade presentation and real-seat standings. Add a personal result on the town or lesson summary: a problem solved, a chain supplied, a before/after result, and a concept understood. A lower-ranked player should still have an achievable next success. Do not redesign the protected standings page or secretly change its metric as part of a general cleanup.

Points and leaderboards can change output without demonstrating intrinsic motivation. One controlled annotation-task study found greater output from gamification elements without a significant change in intrinsic motivation.[^8] That does not mean all competition is harmful. It means click count, wealth, and rank cannot stand in for enjoyment or understanding.

Use short questions with feedback at natural pauses. The current quiz covers relevant business concepts, but reports a total score rather than an explanation of each misconception. Ask the learner to predict an effect, observe it, and explain a similar situation with different goods. Later revisit the concept. Classroom retrieval-practice research supports low-stakes quizzing with feedback for retention; it does not validate this game's one-time licence gate.[^9]

Do not erase the investment curriculum if it is important to the course. Make the transition explicit: “You have completed the business-management lesson. The next lesson introduces a separate practice portfolio.” Give that module an honest starting state, separate objectives, and reliable per-student persistence. The current PORT is a browser-local demonstration with manually controllable trading values, not the town's authoritative competitive endgame. (C4)

## 11. How to determine whether it works

Treat the redesign as a set of testable hypotheses. Valve's published playtesting approach combines observation, questions, and behavioral data rather than relying on a single aggregate metric.[^10] Use the same discipline here: simulations reveal economic behavior; students reveal comprehension, frustration, pride, and interest.

First observe approximately six to eight representative beginners individually, including students with little gaming experience. This is a practical diagnostic starting point, not a statistically validated sample size. Use the devices and lesson conditions that matter. Let them try the opening without a narrated walkthrough; record where they ask for help and why.

| Question | Proposed acceptance target | What to record |
| --- | --- | --- |
| Do they understand the activity? | At least 80% can describe how goods become cash within 90 seconds. | Their explanation, not merely whether a sale occurred. |
| Can they make the first complete decision? | At least 80% complete one allocation-and-reward loop within 5 minutes without a direct instruction. | Time, wrong-screen visits, and help given. |
| Can they diagnose a bottleneck? | At least 80% choose and explain a useful response in two different examples. | Reasoning before clicking and whether the prediction was correct. |
| Do they understand reservations? | At least 80% distinguish in-stock, saved, and available goods in a simple conflicting-stock example. | Accidental holds, stalled recipes, and corrective actions. |
| Is the opening paced? | The intended chain becomes usable during the lesson; avoid repeated unplanned intervals over 60 seconds with no useful choice or observation. | Longest idle stretch and what the player believed they were waiting for. |
| Is there agency? | Observe at least two viable plans that learners can explain. | Different buyer/upgrade choices and their actual consequences. |
| Is the session satisfying? | Every learner can identify one achievement and a next plan; investigate those who cannot. | Enjoyment, boredom moments, and voluntary interest in another round. |

These percentages and timings are proposed product targets, not research constants. With eight participants, report individual counts and paths as well as percentages. Do not declare success from a tiny sample. Revise obvious failures, then repeat with a broader classroom cohort and compare groups with similar prior exposure.

Test three specific alternatives before expanding content:

1. Current opening versus the staged farm–fish–roastery opening, measuring explanation and unaided completion.
2. Unlimited rarity rerolls versus a small board of distinct opportunities, measuring search behavior, economic results, and stated enjoyment.
3. Early separate Breakfast Club versus a later or integrated town challenge, measuring whether it strengthens or confuses understanding of the main loop.

Check learning transfer after the session and again later: change eggs to spare parts, the bakery to a workshop, and the quantities. A player who can only repeat a highlighted sequence has not yet demonstrated understanding of the economic concept.

Use simulations to compare outcomes under matched active time, different attendance schedules, and different choices. Audit low-action strategies, heavy-click strategies, and recovery from a poor purchase. Test total receipts and chosen objectives as well as engine net worth. A strategy should not become superior chiefly because it generates more meaningless requests.

## 12. Recommended work order

**First, establish truthful feedback.** Include recurring receipts in the appropriate overall earnings summary; distinguish history from forecasts; expose product-level bottlenecks and reservation reasons; unify the next-step guidance. This is foundational because the player cannot learn a system whose feedback is incomplete.

**Second, prove a focused opening.** Prototype only the farm, fish stall, roastery, one manual order choice, one recurring relationship, and one finite breakfast objective. Retain the current art and three-column Build composition. Remove unrelated navigation from that beginner path. Tune its affordability and timing against a real lesson.

**Third, remove incentives for repetitive work.** Replace rarity searching, reduce repetitive confirmations, simplify materials, and consolidate breakfast progression. Compare complete strategies rather than individual reward multipliers. Preserve existing earned benefits when an implementation is eventually planned.

**Fourth, test the experience with learners.** Stop adding systems until the opening is understandable and produces choices learners want to revisit. Then add one later district that changes the planning problem. Give the investment module its own review before reconnecting it to the curriculum.

The first implementation should be a small coherent slice, not a simultaneous rewrite of fifteen businesses and every page. The larger design direction can be bold while the delivery remains reviewable.

Any eventual rule changes must account for class snapshots and saved-state migration. Deployment needs Manual Deploy between classes. Changes intended for existing classes require an explicitly planned migration or reset; a config edit alone is not evidence that the live class is using those rules. No deployment or reset is proposed as an action in this review. (C7)

## Evidence appendix

### Scope and validation

This report describes the local v4 baseline inspected on 13 September 2026, including changes already present when the audit began. It does not claim to describe the live database or every existing class snapshot. The repository ownership and existing visual preferences in AGENTS.md and GAME_UI.md were respected.

The tested Python baseline passed **189 tests**. Syntax checks passed for econ.js, econ-nav.js, teacher-econ.js, account.js, and yomama-net.js. Browser inspection covered the five management pages in starter and simulated day-14 towns, the starter Dash, compact management views, and the cooking-event start/queue interaction. The recurring-customer interaction check passed signup, pause/resume, persistence, release, switching, four viewport sizes, and a real automatic shipment worth 15 YM. These results do not certify later concurrent additions.

The local browser inspection blocked external requests to focus on the town interface. Finance-chart load failures under that restriction were not counted as game defects. Initial resize screenshots were superseded by settled compact-layout checks. Customer-art work continued in the shared workspace during the review; the UI observations refer to the captured states. Technical checks do not establish enjoyment or learning.

### Concurrent order changes

After the simulations and review, another process added delivery_recipes.py and changed order generation to select authored bundles with named purposes, supply-chain eligibility, and saved rotation history. This partially addresses the proposal for more coherent jobs. The inspected addition retains free rarity replacement and its reward multipliers; it has not been evaluated by the reported multi-seed experiment. The exact first-session timings, order counts, and reroll effect sizes must be remeasured for that version.

The tested production_economy.py is preserved under .checks/game-design-audit/audited-source/, together with its configuration, cooking event, and existing simulation source. Its SHA256 is 3ccbce1771cdd567b999cc1293529fd70d6003c09b98c9d3e7aa568e61b92f32, matching the original experiment provenance in economy-methods.json. No numerical result in this report should be transferred silently to a different engine. The broader feedback, customer-model, classroom-pacing, and product-scope findings remain design recommendations to assess against subsequent work.

### Local code references

- **C1 — Authoritative economy:** production_economy.py:17 (rarities), :26 (customer catalog), :85 (initial state), :180 (upgrade estimates), :200 (order reservations), :254 (production), :281 (retail), :330 (offline replay), :363 (net worth), :425 (expansion), :430 (materials), :609 (regular shipments), :656 (order generation), :756 (licence), :763 (flow estimate), :793 (payload). Configuration: config/economy.v4.json.
- **C2 — Town interface:** econ.js:312 (selection), :366 (construction), :392 (Build composition), :456 (income and flow display), :472 (guidance), :484 (specialties), :509 (upgrades), :520 (recipes), :550 (orders), :639 (regular customers), :670 (Warehouse), :686 (licence), :714 (Dash summary). Compact views: game-fit.js:58.
- **C3 — Cooking activity:** breakfast_event.py:8 (supplies), :9 (recipes), :13 (orders), :48 (time advancement), :89 (actions); econ.js:403 (event introduction).
- **C4 — Licence and practice portfolio:** game_api.py:887 (quiz loading), :892 (grading), :934 (v4 allocation refusal); econ-nav.js:9 (PORT visibility); port_trading.html:1482 (shared local portfolio key), :1785 (persistence), :1874 (demo setup), :2581 (manual fills/marks), :2624 (reset); engine/paper-engine.js:6 (starting portfolio settings).
- **C5 — Surrounding surfaces:** join.html:79 (return target); buildings.html:40 (navigation); index.html:157 (finance panels), :288 (town summary); app.js:1918 and :2018 (demo market behavior), :2254 (quote refresh); flow.html:51 and app.js:1467 (analysts); chat.html:59 (room labels), :269 (persona), :531 (obsolete state); teach.html:454 (sample dashboard).
- **C6 — Standings:** game_api.py:598 and memos-bars.js describe the real-seat board. Its appearance and ownership remain governed by AGENTS.md section 5b.
- **C7 — Runtime boundaries:** AGENTS.md sections 1, 4, 5, and 7; game_api.py:174 (class time), :215 (ticks), :265 (advance/load behavior); production_economy.py:330 (absence allowance).

Line references identify the inspected working copy and can move with later changes. Historical progression notes were not treated as authoritative when they disagreed with current code.

### Reproducible local evidence

- **E1:** .checks/game-design-audit/economy-experiments.json and economy-experiments-summary.json, regular-customer fixed-configuration benchmarks.
- **E2:** The same experiment files, continuous first-45-minute trajectories and one-purchase comparisons. These use earned resources and explicit policies; they are not observations of human players.
- **E3:** .checks/game-design-audit/production-balance-14d.json, generated by tests/sim_production.py. The policy and visit assumptions are embedded in the result. The upgrade/delivery comparison uses identical visit schedules.
- **E4:** .checks/game-design-audit/intro-20-seeds.json and the matched reroll evidence summarized below. Single-seed illustrative paths should not be interpreted as universal advantages.
- **E5:** Building-quote and incremental retail-capacity estimates in economy-experiments-summary.json. All comparison businesses are at baseline levels; the result excludes buyer contracts and order income.
- **E6:** .checks/game-design-audit/ui-observations.json, mobile-observations.json, and settled screenshots. The day-14 town follows the existing expansion simulation policy, not an actual student save.

### Matched reroll comparison

The comparison uses twenty paired deterministic seeds, numbered 1–20, and 45 continuous minutes. Every policy commits its current quick-cash offer, fulfills ready offers, and uses the same purchase heuristic. The varied factor is zero, one, or four free replacements per 15-second decision step, stopping replacements when a jackpot is present. It is a strategy experiment, not a forecast of student behavior or a claim of a globally optimal policy.

| Replacement allowance | Mean net worth | Median net worth | Range | Mean replacements | Paired wins versus none |
| --- | ---: | ---: | --- | ---: | ---: |
| None | 4,940.55 YM | 4,806.50 YM | 4,144–5,787 | 0 | — |
| At most 1 per step | 5,380.50 YM | 5,498.50 YM | 3,685–6,509 | 138.00 | 15/20 |
| At most 4 per step | 6,804.70 YM | 6,961.00 YM | 4,684–7,839 | 377.25 | 19/20 |

The median paired improvement is 361 YM for one replacement and 1,938.50 YM for four. Results are in .checks/game-design-audit/intro-20-seeds.json; the driver is audit_twenty_seeds.py, using audit_economy.py in the same directory. economy-methods.json records assumptions and source hashes. This design assessment uses effect sizes and individual paired outcomes, not a claim of statistical significance or representative human behavior.

## Sources

[^1]: Robin Hunicke, Marc LeBlanc, and Robert Zubek. [MDA: A Formal Approach to Game Design and Game Research](https://www.cs.northwestern.edu/~hunicke/MDA.pdf). 2004. Conceptual framework; supports distinguishing mechanics from intended player experience, including expressive and social value.

[^2]: Soren Johnson. [Water Finds a Crack](https://www.designer-notes.com/game-developer-column-17-water-finds-a-crack/). Game Developer column, March 2011; author publication, 12 June 2011. Designer account of efficient but tedious strategies; not a controlled experiment.

[^3]: Michael Booth, Valve. [Replayable Cooperative Game Design: Left 4 Dead](https://cdn.akamai.steamstatic.com/apps/valve/2009/GDC2009_ReplayableCooperativeGameDesign_Left4Dead.pdf). GDC, March 2009. Developer account of pacing and constrained variation in an action game; no direct classroom timing claim.

[^4]: M. P. Jacob Habgood and Shaaron E. Ainsworth. [Motivating Children to Learn Effectively: Exploring the Value of Intrinsic Integration in Educational Games](https://tca2.education.illinois.edu/docs/librariesprovider23/default-document-library/j-of-the-learning-sc-2011-habgood.pdf?sfvrsn=c838d23d_2). Journal of the Learning Sciences, 2011. A teacher-supported study of 58 children aged 7–11 and a separate free-choice study of 16 children, using one mathematics game. Findings cannot be generalized automatically to business games.

[^5]: Erik Andersen and colleagues. [The Impact of Tutorials on Games of Varying Complexity](https://www.khoury.northeastern.edu/home/scooper/index_files/pub/andersen2012impact.pdf). CHI, 2012. More than 45,000 players across three games. Contextual guidance benefited the complex game; effects were not universal across games or measures.

[^6]: Kovarex, Wube Software. [Friday Facts #129: The Late Game](https://www.factorio.com/blog/post/fff-129). 11 March 2016. Developer diagnosis and proposed solutions for repetitive maintenance and late-game progression; not an experiment establishing a universal rule.

[^7]: Erik Andersen and colleagues. [On the Harmfulness of Secondary Game Objectives](https://grail.cs.washington.edu/projects/game-abtesting/fdg2011/fdg2011.pdf). Foundations of Digital Games, 2011. More than 27,000 players in two games; effects differed by metric and player group. Off-path versus no-coins return-rate differences were not significant.

[^8]: Elisa D. Mekler, Florian Brühlmann, Alexandre N. Tuch, and Klaus Opwis. [Towards Understanding the Effects of Individual Gamification Elements on Intrinsic Motivation and Performance](https://edoc.unibas.ch/entities/publication/ccec8ccc-aa54-417d-b205-334b518d6eed). Computers in Human Behavior, 2017; DOI 10.1016/j.chb.2015.08.048. Authors' abstract and university record; limited here to the reported output/motivation findings from an image-annotation task.

[^9]: Henry L. Roediger III, Pooja K. Agarwal, Mark A. McDaniel, and Kathleen B. McDermott. [Test-Enhanced Learning in the Classroom: Long-Term Improvements From Quizzing](https://www.researchgate.net/publication/51797070_Test-Enhanced_Learning_in_the_Classroom_Long-Term_Improvements_From_Quizzing). Journal of Experimental Psychology: Applied, 2011. Authors' full-text copy; three sixth-grade social-studies experiments. Supports retrieval practice with feedback, not this game's specific gate.

[^10]: Mike Ambinder, Valve. [Valve's Approach to Playtesting: The Application of Empiricism](https://cdn.akamai.steamstatic.com/apps/valve/2009/GDC2009_ValvesApproachToPlaytesting.pdf). GDC, March 2009. Published developer methodology for combining observation, self-report, and game data.
