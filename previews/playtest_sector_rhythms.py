"""Compare production rhythms with real ticks, real stock, and existing actions.

No database is opened. Established scenarios receive the same stated capital
and installed levels; warm stock is earned through ordinary production.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import business_operations as operations
import order_engine as orders
import production_economy as economy
import rules_tables
from previews.playtest_economy_choices import decide, POLICIES


LEVELS = {'base': (1, 1), 'production-heavy': (4, 1), 'sales-heavy': (1, 4)}


def counter():
    return dict(actions=0, visits=0, buyerToggles=0, refreshes=0, savedOrders=0,
                startsByCard=[0, 0, 0], manualCash=0, readyChecks=0, readyCards=0,
                allThreeReadyChecks=0, buyerBlockedChecks=0)


def prepare(enabled, tiers, level, warm_ticks, fresh=False, seed=71):
    cfg = economy.load_config()
    cfg['production']['sectorRhythms'] = enabled
    state = economy.new_state(cfg, seed=seed)
    if not fresh:
        state['cash'] = 1_000_000
        state['tierOf'] = list(tiers)
        production, sales = LEVELS[level]
        state['b'] = [economy._building(tier, lv=production, sales=sales) for tier in tiers]
        state['businessProgression']['grandfathered'] = [cfg['tiers'][tier]['id'] for tier in tiers]
        operations.ensure(cfg, state)
        state['offers'] = None
        state['orderRecipeHistory'] = [[], [], []]
        economy.offer_contracts(cfg, state, state['tick'])
    with rules_tables.pinned(cfg):
        if warm_ticks:
            for building in state['b']:
                building['reserve'] = True
            for _ in range(warm_ticks):
                economy.player_tick(cfg, {}, state, state['tick'])
            for building in state['b']:
                building['reserve'] = False
    return cfg, state


def run(enabled, tiers, level, warm_ticks, policy, ticks, fresh=False, seed=71, roster=None):
    cfg, state = prepare(enabled, tiers, level, warm_ticks, fresh, seed)
    stats = counter()
    if POLICIES[policy][2] != 'off':
        eligible = [buyer for buyer in economy._customer_catalog(cfg, state) if buyer['available']]
        if roster:
            eligible = [next(buyer for buyer in eligible if buyer['id'] == buyer_id) for buyer_id in roster]
        for slot, buyer in enumerate(eligible[:economy._customer_slots(state)]):
            result = economy.manage_customer_contract(cfg, state, slot, 'accept', buyer['id'])
            assert result['ok'], result
    if POLICIES[policy][0]:
        state = orders.create_board(cfg, state)
    before = copy.deepcopy(state)
    first_material_goal = None
    bursts = []
    with rules_tables.pinned(cfg):
        rates, regular_flow = economy._flows(cfg, state)
        forecast_sales = economy.town_income(cfg, state)
        forecast_cost = sum(operations.forecast_cost(cfg, state, slot, rates)
                            for slot in range(len(state['b'])))
        for tick in range(ticks):
            if POLICIES[policy][0] and tick % 2 == 0:
                decide(cfg, state, policy, stats, tick // 2)
            made = state['report']['unitsProduced']
            economy.player_tick(cfg, {}, state, state['tick'])
            bursts.append(state['report']['unitsProduced'] - made)
            if POLICIES[policy][0]:
                previous = state['orderEngine']['lastDelivery']
                orders.refresh_board(cfg, state)
                latest = state['orderEngine']['lastDelivery']
                if latest != previous:
                    stats['manualCash'] += latest['reward']
            if first_material_goal is None and state['materials'] >= 10:
                first_material_goal = (tick + 1) * cfg['global']['tick'] / 60
    walkins = state['report']['retailEarned'] - before['report']['retailEarned']
    regulars = state['report']['customerEarned'] - before['report']['customerEarned']
    costs = state['businessOperations']['totalOperatingCosts'] - before['businessOperations']['totalOperatingCosts']
    net_cash = state['cash'] - before['cash']
    assert net_cash == walkins + regulars + stats['manualCash'] - costs
    old_activity = before['businessProgression']['activity']
    activity = state['businessProgression']['activity']
    for gid in economy.catalog(cfg):
        produced = activity['produced'].get(gid, 0) - old_activity['produced'].get(gid, 0)
        sold = activity['sold'].get(gid, 0) - old_activity['sold'].get(gid, 0)
        assert state['inventory'].get(gid, 0) == before['inventory'].get(gid, 0) + produced - sold
    return dict(orderMode='prototype' if POLICIES[policy][0] else 'automatic-sales-only',
                netCash=net_cash, walkinCash=walkins, regularCash=regulars,
                manualCash=stats['manualCash'], operatingCost=costs,
                unitsProduced=state['report']['unitsProduced'] - before['report']['unitsProduced'],
                regularShipments=state['customerContracts']['deliveries'] - before['customerContracts']['deliveries'],
                completedOrders=state['cStats']['done'] - before['cStats']['done'],
                materials=state['materials'] - before['materials'], materialGoalMinutes=first_material_goal,
                emptyProductionTicks=bursts.count(0), largestProductionTick=max(bursts),
                productionPattern=bursts[:8], firstMinuteUnits=sum(bursts[:4]),
                forecastSalesPerMinute=round(forecast_sales, 6),
                forecastCostPerMinute=round(forecast_cost, 6),
                endingCash=state['cash'], endingStock=sum(state['inventory'].values()),
                startsByCard=stats['startsByCard'], actions=stats['actions'],
                refreshes=stats['refreshes'], conservationPassed=True)


def scenarios():
    cfg = economy.load_config()
    for tier, building in enumerate(cfg['tiers']):
        for level in LEVELS:
            for warm in (False, True):
                yield dict(layout=building['id'], tiers=[tier], level=level, warm=warm,
                           policy='walkins', fresh=False)
    for count in (1, 3, 6, 15):
        for level in LEVELS:
            for warm in (False, True):
                for policy in ('walkins', 'regulars_refresh'):
                    yield dict(layout='town-' + str(count), tiers=list(range(count)), level=level,
                               warm=warm, policy=policy, fresh=False)
    for policy in ('walkins', 'regulars_refresh'):
        yield dict(layout='fresh-opening', tiers=[0], level='base', warm=False, policy=policy, fresh=True)
    for policy in ('keep_for_material_goal', 'pause_for_material_goal'):
        yield dict(layout='town-6-goal', tiers=list(range(6)), level='base', warm=False,
                   policy=policy, fresh=False)
    seeds = (7, 11, 19, 23, 31, 43, 53, 61, 71, 97)
    for count, policy in ((6, 'regulars_refresh'), (15, 'regulars_refresh'),
                          (6, 'keep_for_material_goal'), (6, 'pause_for_material_goal')):
        for seed in seeds:
            yield dict(layout='town-{}-seed-check'.format(count), tiers=list(range(count)),
                       level='base', warm=False, policy=policy, fresh=False, seed=seed, sensitivity=True)
    # The general comparison selects the first eligible buyers. Also exercise
    # recurring demand in all three sectors without manual-order luck.
    for seed in seeds:
        yield dict(layout='town-6-cross-sector-buyers', tiers=list(range(6)), level='base',
                   warm=False, policy='regulars', fresh=False, seed=seed,
                   roster=['copper_cafe', 'rally_crew', 'builders_union', 'neighborhood_grid'])


def percent_change(before, after):
    return 100 * (after - before) / abs(before) if before else None


def write_report(path, results, ticks, warm_ticks):
    basic = [row for row in results if row['policy'] == 'walkins' and row['layout'] != 'fresh-opening']
    changes = [row['changed']['netCash'] - row['baseline']['netCash'] for row in basic]
    percentages = [percent_change(row['baseline']['netCash'], row['changed']['netCash']) for row in basic]
    percentages = [value for value in percentages if value is not None]
    affected = sum(row['baseline'] != row['changed'] for row in results)
    lines = ['# Sector rhythm playtest', '',
             'Reproduce: `.venv/bin/python previews/playtest_sector_rhythms.py`.', '',
             '{} matched scenarios ({} runs), {} minutes each; warm starts first produce for {} minutes with shop sales held.'.format(
                 len(results), len(results) * 2, ticks / 4, warm_ticks / 4),
             'Established scenarios have identical 1,000,000 YM starting capital, installed levels, quest-unlocked products, and actual empty shelves. No inventory is inserted. Fresh-opening cases start with the real zero-cash farm.',
             'Base levels are Production 1 / Customers 1; production-heavy is 4 / 1; sales-heavy is 1 / 4. Storage stays at level 1. The only rule difference is `production.sectorRhythms`.', '',
             'All runs passed exact cash and per-product stock conservation. Every matched pair retained identical displayed average sales and cost forecasts; actual receipts can differ through timing, full shelves, regular deliveries, and which offers are ready.', '',
             '**Average production rates are protected; actual player outcomes are not identical.** Prototype manual-order timing can change the offer sequence and produce large cash/material differences. The seed comparison below checks whether the initial large differences repeat consistently.', '',
             'Across {} automatic-sales scenarios, the median change in actual net cash was {} YM; range {} to {} YM over the measurement window. {} of {} matched scenarios changed at least one recorded timing or outcome measure.'.format(
                 len(basic), statistics.median(changes), min(changes), max(changes), affected, len(results)), '',
             'Automatic-sales paired percentage changes: median {:.2f}%, range {:.2f}% to {:.2f}%. These are actual net cash, including production expenses; they are not changes to quoted YM/min.'.format(
                 statistics.median(percentages), min(percentages), max(percentages)), '',
             '## Representative empty-stock patterns', '',
             '| Business, base levels | Before, first 8 ticks | After, first 8 ticks | Net cash before → after |',
             '|---|---|---|---|']
    for layout in ('farm', 'garage', 'solar_coop'):
        row = next(r for r in results if r['layout'] == layout and r['level'] == 'base' and not r['warm'])
        lines.append('| {} | {} | {} | {} → {} |'.format(layout, row['baseline']['productionPattern'],
                      row['changed']['productionPattern'], row['baseline']['netCash'], row['changed']['netCash']))
    lines += ['', '## Prototype orders and recurring buyers', '',
              'These manual-order policies use the separate `order_engine.py` prototype, not the normal Market order handler. They exercise real production, buyer reservations, inventory and cash changes. The scripted visitor checks every 30 seconds, refreshes at most five prototype offers, delivers one ready offer, or saves a reachable order. Regular buyers are selected from the actual eligible list; supplied stock always follows the real reservation rules. Both runs use the same seed. Different ready offers can lead to different later rewards, so this measures one policy path, not a guaranteed sector advantage.', '',
              '| Scenario | Net cash before → after | Regular shipments | Orders completed | Materials | First 10 materials, minutes |',
              '|---|---|---|---|---|---|']
    for row in results:
        if ((row['layout'] in ('town-1', 'town-3', 'town-6', 'town-15') and row['level'] == 'base'
             and not row['warm'] and row['policy'] != 'walkins') or row['layout'] in ('fresh-opening', 'town-6-goal')):
            a, b = row['baseline'], row['changed']
            values = ['{} → {}'.format(a[key], b[key]) for key in
                      ('netCash', 'regularShipments', 'completedOrders', 'materials', 'materialGoalMinutes')]
            lines.append('| {} / {} | {} |'.format(row['layout'], row['policy'], ' | '.join(values)))
    lines += ['', '## Ten-seed prototype sensitivity check', '',
              'Seeds: 7, 11, 19, 23, 31, 43, 53, 61, 71, 97. Each pair has identical installed levels, empty starting stock, capital and policy; only sector rhythms differ. Each policy runs for {} game minutes.'.format(ticks / 4), '',
              '| Town / policy | Aggregate cash before → after | Cash change | Median paired cash change | Aggregate orders | Aggregate materials | Paired cash range |',
              '|---|---|---|---|---|---|---|']
    for count, policy in ((6, 'regulars_refresh'), (15, 'regulars_refresh'),
                          (6, 'keep_for_material_goal'), (6, 'pause_for_material_goal')):
        selected = [r for r in results if r.get('sensitivity') and len(r['tiers']) == count and r['policy'] == policy]
        sums = {label: {key: sum(r[label][key] for r in selected) for key in
                        ('netCash', 'completedOrders', 'materials', 'regularShipments')} for label in ('baseline', 'changed')}
        deltas = [r['changed']['netCash'] - r['baseline']['netCash'] for r in selected]
        percentages = [percent_change(r['baseline']['netCash'], r['changed']['netCash']) for r in selected]
        a, b = sums['baseline'], sums['changed']
        lines.append('| {} / {} | {} → {} | {:+.2f}% | {:+g} YM | {} → {} | {} → {} | {:+.2f}% to {:+.2f}% |'.format(
            count, policy, a['netCash'], b['netCash'], percent_change(a['netCash'], b['netCash']), statistics.median(deltas),
            a['completedOrders'], b['completedOrders'], a['materials'], b['materials'],
            min(percentages), max(percentages)))
    lines += ['', '| Town / policy | Median paired orders change | Median paired materials change | Seeds with less cash |',
              '|---|---|---|---|']
    for count, policy in ((6, 'regulars_refresh'), (15, 'regulars_refresh'),
                          (6, 'keep_for_material_goal'), (6, 'pause_for_material_goal')):
        selected = [r for r in results if r.get('sensitivity') and len(r['tiers']) == count and r['policy'] == policy]
        median_orders = statistics.median(r['changed']['completedOrders'] - r['baseline']['completedOrders'] for r in selected)
        median_materials = statistics.median(r['changed']['materials'] - r['baseline']['materials'] for r in selected)
        lower_cash = sum(r['changed']['netCash'] < r['baseline']['netCash'] for r in selected)
        lines.append('| {} / {} | {:+g} | {:+g} | {}/10 |'.format(count, policy, median_orders, median_materials, lower_cash))
    lines += ['', 'The largest prototype cash loss was 20.98% in the 15-business town (seed 43). The 15-business regulars-and-refresh policy lost 7.88% aggregate cash, 10.99% orders, and 56.87% materials. Eight of ten seeds earned less cash; this is not explained by only the first unlucky seed. It remains a prototype-policy balance concern rather than evidence that all normal Market play has the same penalty.']
    lines += ['', 'Material-goal completion times (before → after, minutes):', '']
    for policy in ('keep_for_material_goal', 'pause_for_material_goal'):
        selected = [r for r in results if r.get('sensitivity') and r['policy'] == policy]
        times = {label: [r[label]['materialGoalMinutes'] for r in selected if r[label]['materialGoalMinutes'] is not None]
                 for label in ('baseline', 'changed')}
        medians = [statistics.median(times[label]) if times[label] else None for label in ('baseline', 'changed')]
        lines.append('- {}: median {} → {}; successes {}/10 → {}/10. Medians include successful runs only.'.format(
            policy, medians[0], medians[1], len(times['baseline']), len(times['changed'])))
    recurring = [r for r in results if r['layout'] == 'town-6-cross-sector-buyers']
    lines += ['', 'A separate ten-seed recurring-only check signs Copper Café (Food), Rally Crew and Builders Union (Industry), and Neighborhood Grid (Energy), covering all three sector rhythms without manual-order selection.',
              'Aggregate shipments: {} → {}; aggregate net cash: {} → {} YM.'.format(
                  sum(r['baseline']['regularShipments'] for r in recurring), sum(r['changed']['regularShipments'] for r in recurring),
                  sum(r['baseline']['netCash'] for r in recurring), sum(r['changed']['netCash'] for r in recurring))]
    lines += ['', '## Interpretation', '',
              'Food keeps its existing cadence. Industry releases goods in larger groups; it falls back to one affordable batch when cash or shelf headroom is tight, so an odd-capacity saved order can still finish. Energy adds one-time product startup delays, then preserves existing cycle lengths.',
             'The deterministic cadence change can have large indirect effects on a player who continually selects and refreshes prototype orders. Ten seeds are a sensitivity sample, not proof that all policies, progression stages, or long-run earnings are balanced. Scripted play cannot establish whether children notice or enjoy the distinction. Normal orders have separate fixed-quote regression coverage; these prototype simulations do not establish their realized earnings.',
              'Fractional cost carry can shift a whole YM across measurement boundaries; exact fixed-point costs are separately covered by the sector tests. The fresh-opening examples use the real zero-cash starter farm and, where applicable, prototype orders; they do not automate expansion purchases.', '',
              'Full per-scenario output is in `.checks/economy-playtest/sector-rhythms.json`.', '']
    path.write_text('\n'.join(lines), encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticks', type=int, default=96)
    parser.add_argument('--warmup-ticks', type=int, default=32)
    parser.add_argument('--output', type=Path, default=ROOT / '.checks/economy-playtest/sector-rhythms.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'SECTOR_RHYTHMS_PLAYTEST.md')
    args = parser.parse_args()
    if args.ticks < 8 or args.warmup_ticks < 0:
        parser.error('Use at least 8 ticks and a nonnegative warmup.')
    results = []
    for spec in scenarios():
        pair = dict(spec, seed=spec.get('seed', 71))
        for enabled, label in ((False, 'baseline'), (True, 'changed')):
            pair[label] = run(enabled, spec['tiers'], spec['level'], args.warmup_ticks if spec['warm'] else 0,
                              spec['policy'], args.ticks, spec['fresh'], pair['seed'], spec.get('roster'))
        for key in ('forecastSalesPerMinute', 'forecastCostPerMinute'):
            assert pair['baseline'][key] == pair['changed'][key], (spec, key)
        results.append(pair)
        if len(results) % 20 == 0:
            print('{} matched scenarios complete'.format(len(results)), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(ticks=args.ticks, warmupTicks=args.warmup_ticks,
                                          scenarios=results), indent=2), encoding='utf8')
    write_report(args.report, results, args.ticks, args.warmup_ticks)
    print('{} matched scenarios passed conservation; report: {}'.format(len(results), args.report), flush=True)


if __name__ == '__main__':
    main()
