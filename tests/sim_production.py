"""Reproducible player strategies for the v4 economy, never imported by server.

    python3 tests/sim_production.py --days 7 --output previews/production-balance.json

Bots are transparent heuristics, not optimal players or evidence of retention.
Only earned cash, actual inventory and recorded unlocks count in the results.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_economy as E

STRATEGIES = ('upgrades', 'expansion', 'deliveries', 'casual')


def nominal_sales(cfg, state):
    rates = E.flow_rates(cfg, state)
    catalog = E.catalog(cfg)
    return sum(rates[gid]['retail'] * catalog[gid]['unitPrice'] for gid in rates)


def upgrade_candidates(cfg, state):
    choices = []
    old = nominal_sales(cfg, state)
    for slot, owned in enumerate(state['b']):
        for kind, key in (('production', 'lv'), ('sales', 'sales')):
            cost = E.upgrade_cost(cfg, state, slot, kind)
            if cost is None:
                continue
            owned[key] += 1
            delta = nominal_sales(cfg, state) - old
            owned[key] -= 1
            if delta > 0:
                choices.append(dict(slot=slot, kind=kind, cost=cost, score=delta / cost))
    return sorted(choices, key=lambda c: c['score'], reverse=True)


def ready(state, order):
    return all(state['inventory'].get(n['goodId'], 0) >= n['quantity'] for n in order['requirements'])


def act(cfg, state, strategy, trace):
    """At most three deliveries and one purchase per decision tick."""
    for index, offer in enumerate(list(state['offers'])):
        if ready(state, offer):
            result = E.fulfill_order(cfg, state, index, offer['id'])
            if result['ok']:
                trace['actions']['deliveries'] += 1
                trace.setdefault('firstDeliverySec', state['tick'] * cfg['global']['tick'])
    if strategy == 'deliveries':
        # Use the same bounded order commitment offered by Market.
        order = state['offers'][1]
        if not order.get('committed'):
            E.commit_order(cfg,state,1,order['id'],True)
        for slot in range(len(state['b'])):
            E.set_reserve(cfg,state,slot,False)
    else:
        for slot in range(len(state['b'])):
            E.set_reserve(cfg, state, slot, False)

    frontier = E.expand_options(cfg, state)
    target = frontier[0] if frontier else None
    if strategy in ('expansion', 'casual') and target is not None:
        # Save for the next business; invest after buying it while it is built.
        if E.can_expand(cfg, state, target)['ok']:
            E.expand(cfg, state, target, state['tick'])
            trace['actions']['expansions'] += 1
            return
        if not state.get('build'):
            return

    candidates = upgrade_candidates(cfg, state)
    candidate = next((c for c in candidates if c['cost'] <= state['cash']), None)
    if candidate:
        # Upgraders pursue the best affordable nominal sales improvement. This
        # intentionally cannot see future supplier shortages or solve globally.
        E.buy_upgrade(cfg, state, candidate['slot'], candidate['kind'])
        trace['actions']['upgrades'] += 1
        trace.setdefault('firstUpgradeSec', state['tick'] * cfg['global']['tick'])
        return
    if target is not None and E.can_expand(cfg, state, target)['ok']:
        E.expand(cfg, state, target, state['tick'])
        trace['actions']['expansions'] += 1


def snapshot(cfg, state):
    catalog = E.catalog(cfg)
    return dict(cash=state['cash'], worth=E.net_worth(cfg, state),
                buildings=len(state['b']), materials=state['materials'],
                deliveries=state['cStats']['done'],
                automaticSales=state['report']['retailEarned'],
                storedValue=sum(catalog[gid]['unitPrice'] * q for gid, q in state['inventory'].items()),
                unitsStored=sum(state['inventory'].values()),
                levels=[dict(id=cfg['tiers'][b['tier']]['id'], production=b['lv'], sales=b['sales']) for b in state['b']],
                construction=cfg['tiers'][state['build']['i']]['id'] if state.get('build') else None)


def simulate(days=7, cfg=None):
    cfg = E.load_config() if cfg is None else copy.deepcopy(cfg)
    step_seconds = cfg['global']['tick']
    ticks_day = E.ticks_per_day(cfg)
    players = {}
    for name in STRATEGIES:
        players[name] = dict(state=E.new_state(cfg, seed=7),
                             trace=dict(strategy=name, actions=dict(upgrades=0, expansions=0, deliveries=0), snapshots={}))
    world = E.new_class(cfg, days * ticks_day)
    for k in range(days * ticks_day):
        for name, player in players.items():
            state, trace = player['state'], player['trace']
            seconds = k * step_seconds
            # Shared first ten minutes; later five-minute visits every 2h or 12h.
            interval = 12 * 3600 if name == 'casual' else 2 * 3600
            active = seconds < 600 or seconds % interval < 300
            if active:
                E.on_login(cfg, state, k)
            allowance = int(cfg['runtime']['offlineHours'] * E.ticks_per_hour(cfg))
            if k < state['lastActiveTick'] + allowance:
                E.player_tick(cfg, world, state, k)
            else:
                E.advance_class(cfg, world, [state], k, k + 1)
            if state['report']['retailEarned'] > 0:
                trace.setdefault('firstSaleSec', (k + 1) * step_seconds)
            if active:
                act(cfg, state, name, trace)
            if state['cash'] > 0:
                trace.setdefault('firstIncomeSec', (k + 1) * step_seconds)
            assert type(state['cash']) is int and state['cash'] >= 0
            assert all(type(q) is int and q >= 0 for q in state['inventory'].values())
            if (k + 1) * step_seconds in (600, 3600):
                trace['snapshots'][f'{(k + 1) * step_seconds // 60}min'] = snapshot(cfg, state)
            if (k + 1) % ticks_day == 0:
                trace['snapshots'][f'day{(k + 1) // ticks_day}'] = snapshot(cfg, state)
    results = []
    for name, player in players.items():
        state, trace = player['state'], player['trace']
        trace['unlocksMinutes'] = {cfg['tiers'][state['tierOf'][int(slot)]]['id']: round(day * 1440, 2)
                                   for slot, day in state['unlock'].items()}
        trace['offlineSecondsSkipped'] = state['report']['offlineTicksSkipped'] * step_seconds
        results.append(trace)
    return dict(modelVersion=4, days=days, seed=7,
                configSHA256=hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
                engineSHA256=hashlib.sha256(Path(E.__file__).read_bytes()).hexdigest(),
                assumptions='First visit 10 minutes; then 5 minutes every 2 hours, casual every 12 hours. '
                            'Upgrades use nominal sales improvement per price; expansion saves for earliest frontier; '
                            'deliveries commits only the middle offer quantities. No manual bulk sales, paid boosts or stock gifts.',
                results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = simulate(args.days)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    for strategy in report['results']:
        print(strategy['strategy'], 'firstsale', strategy.get('firstSaleSec'),
              'firstupgrade', strategy.get('firstUpgradeSec'), 'unlocks', strategy['unlocksMinutes'])
        for day in ('10min', '60min', 'day1', 'day3', f'day{args.days}'):
            if day in strategy['snapshots']:
                s = strategy['snapshots'][day]
                print(f'  {day}: {s["buildings"]} buildings; {s["cash"]:,} YM cash; '
                      f'{s["worth"]:,} worth; {s["deliveries"]} deliveries')


if __name__ == '__main__':
    main()
