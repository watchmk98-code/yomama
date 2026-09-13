# Worker population — display only

The user explicitly deferred the purpose of workers. Under the default rules, workers are **only a visible population count**. They have no assignments, staffing requirements, bonuses, costs, training, production effects, customer effects or unlock effects. Sector labor requirements are future design work.

The top Workers counter uses a pixel worker icon and opens a population overview in Operations. The ordinary population is separate from Advanced HQ specialists. Prestige remains visible beside the Operations title on every tab.

## Arrivals and persistence

The user chose automatic arrivals through business growth rather than hiring. Current adjustable starting values are 5 workers on the first opening of a business type and 1 for each new highest production level, capped at 20 earned per business type. Customer/storage upgrades and elapsed time do not generate workers. Construction must finish before arrivals count.

Closing a business retains the population. Rebuilding or repeating an already reached level grants no duplicate arrivals. `worker_population.py` records the total and permanent per-type growth milestones in `st.workerPopulation`.

A save explicitly adopting population rules imports its existing crew count once, including people retained at closed businesses. The initial total is the greater of the existing crew count and current growth entitlement. Cash, goods, owned focus nodes, Prestige and HQ specialists are preserved. Legacy crew assignments have no effect under population rules. Worker assignment API commands are rejected.

## Existing focus and HQ

Focus purchases and their approved 0/1/2 Prestige costs remain. Worker-dependent effects are inactive and described as such. Existing focus ownership is retained. No expertise mechanic is added.

Advanced HQ retains its existing specialist recruitment and bounded trainer-development rules, separately from ordinary population. Its team cannot create ordinary workers. Specialist recruitment is accessible under Advanced HQ's training programs.

The latest user direction also defers the request that less capital-intensive sectors need more workers. No active sector staffing targets or requirements are implemented.

## Release and validation

The feature is enabled by `workforce.populationEnabled` alongside the existing workforce and business-design flags. Existing class snapshots without it retain their old crew behavior. New classes use the default population rules. An existing class needs an explicit reset to adopt the current default configuration through the existing admin workflow; no live reset has been performed.

Publishing **needs Manual Deploy**. Deployment alone does not replace existing class snapshots.

Tests verify one-time arrivals, migration before business instance IDs exist, closure/rebuild safeguards, exact production/cash/stock parity across different population counts, rejected assignments, separate HQ development and responsive display. No worker purpose is assumed or activated.
