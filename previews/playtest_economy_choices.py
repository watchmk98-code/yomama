"""Compare scripted choices using real ticks and the isolated three-card engine.

No database, balance edits, free stock, or simulated human enjoyment. Run:
    .venv/bin/python previews/playtest_economy_choices.py
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import order_engine as O
import production_economy as E
import rules_tables
from previews.order_classes_preview import sample_town


POLICIES = {
    'walkins': (False, 0, 'off'),
    'regulars': (False, 0, 'keep'),
    'patient_orders': (True, 0, 'off'),
    'refresh_orders': (True, 5, 'off'),
    'regulars_patient': (True, 0, 'keep'),
    'regulars_refresh': (True, 5, 'keep'),
    'keep_for_material_goal': (True, 5, 'keep_goal'),
    'pause_for_material_goal': (True, 5, 'goal'),
    'toggle_for_each_order': (True, 5, 'toggle'),
}
ROSTERS = {1: ('corner_grocer', 'sunrise_diner'),
           3: ('corner_grocer', 'harbor_bistro', 'copper_cafe'),
           6: ('copper_cafe', 'rally_crew', 'builders_union', 'neighborhood_grid')}


def ready(cfg, st, index, ignore_buyers=False):
    offer = st['offers'][index]
    if offer.get('inTransit'):
        return False
    if ignore_buyers:
        trial = copy.copy(st)
        trial['customerContracts'] = dict(st['customerContracts'], active=[])
    else:
        trial = st
    held = E.delivery_reservations(cfg, trial, exclude=offer['id'])
    return all(st['inventory'].get(n['goodId'], 0) - held.get(n['goodId'], 0) >= n['quantity']
               for n in offer['requirements'])


def set_buyers(cfg, st, paused, stats):
    for buyer in list(st['customerContracts']['active']):
        if buyer['paused'] != paused:
            result = E.manage_customer_contract(cfg, st, buyer['slot'], 'pause' if paused else 'resume',
                                               contract_id=buyer['id'])
            assert result['ok'], result
            stats['actions'] += 1
            stats['buyerToggles'] += 1


def decide(cfg, st, policy, stats, visit):
    enabled, rolls, buyer_mode = POLICIES[policy]
    if not enabled:
        return
    stats['visits'] += 1
    if buyer_mode == 'goal':
        set_buyers(cfg, st, st['materials'] < 10, stats)

    def choose():
        candidates = [i for i in range(3) if ready(cfg, st, i)]
        stats['readyChecks'] += 1
        stats['readyCards'] += len(candidates)
        stats['allThreeReadyChecks'] += len(candidates) == 3
        if not candidates:
            blocked = [i for i in range(3) if ready(cfg, st, i, ignore_buyers=True)]
            if blocked:
                stats['buyerBlockedChecks'] += 1
                if buyer_mode == 'toggle':
                    set_buyers(cfg, st, True, stats)
                    candidates = [i for i in range(3) if ready(cfg, st, i)]
        if not candidates:
            return None
        # A material goal explicitly favors the sector card; otherwise cash.
        if buyer_mode in ('goal', 'keep_goal') and st['materials'] < 10 and 1 in candidates:
            return 1
        return max(candidates, key=lambda i: (st['offers'][i]['reward'], -i))

    chosen = choose()
    for attempt in range(rolls):
        if chosen is not None:
            break
        available = [i for i, offer in enumerate(st['offers'])
                     if not offer.get('inTransit') and not offer.get('committed')]
        if not available:
            break
        index = available[(visit + attempt) % len(available)]
        before = st['cash'], st['materials'], copy.deepcopy(st['inventory'])
        result = O.apply_action(cfg, st, index, 'replace')
        assert result['ok'], result
        assert (st['cash'], st['materials'], st['inventory']) == before
        stats['refreshes'] += 1
        stats['actions'] += 1
        chosen = choose()
    if chosen is not None:
        result = O.apply_action(cfg, st, chosen, 'fulfill')
        assert result['ok'], result
        stats['actions'] += 1
        stats['startsByCard'][chosen] += 1
        if result['kind'] != 'order_dispatch':
            stats['manualCash'] += result['reward']
    elif not any(o.get('committed') and not o.get('inTransit') for o in st['offers']):
        # Save one reachable job instead of waiting while its goods auto-sell.
        def shortage(index):
            offer = st['offers'][index]
            return sum(max(0, n['quantity'] - st['inventory'].get(n['goodId'], 0))
                       * E.catalog(cfg)[n['goodId']]['cycleTicks'] for n in offer['requirements'])
        candidates = [i for i, offer in enumerate(st['offers']) if not offer.get('inTransit')]
        if buyer_mode in ('goal', 'keep_goal') and st['materials'] < 10 and 1 in candidates:
            candidates = [1]
        for index in sorted(candidates, key=shortage):
            result = O.apply_action(cfg, st, index, 'commit', st['offers'][index]['id'])
            if result['ok']:
                stats['actions'] += 1
                stats['savedOrders'] += 1
                break
    if buyer_mode == 'toggle':
        set_buyers(cfg, st, False, stats)


def run(cfg, count, level, seed, policy, minutes):
    st = sample_town(cfg, count, seed)
    st['cash'] = 1000000
    for b in st['b']:
        b.update(lv=level, sales=1, auto=1, storage=1, reserve=False)
    stats = dict(actions=0, visits=0, buyerToggles=0, refreshes=0, savedOrders=0,
                 startsByCard=[0, 0, 0], manualCash=0, readyChecks=0, readyCards=0,
                 allThreeReadyChecks=0, buyerBlockedChecks=0, storageBlockedTicks=0,
                 transitTicks=0, transitStorageBlockedTicks=0, timedCash=0)
    if POLICIES[policy][2] != 'off':
        for slot, customer in enumerate(ROSTERS[count]):
            assert E.manage_customer_contract(cfg, st, slot, 'accept', customer_id=customer)['ok']
            stats['actions'] += 1
    warmup_ticks = round(10 * 60 / cfg['global']['tick'])
    with rules_tables.pinned(cfg):
        for _ in range(warmup_ticks):
            E.player_tick(cfg, {}, st, st['tick'])
        st = O.create_board(cfg, st)
        before = copy.deepcopy(st)
        start = st['tick']
        first_material_goal = None
        for offset in range(round(minutes * 60 / cfg['global']['tick'])):
            if offset % 2 == 0:
                decide(cfg, st, policy, stats, offset // 2)
            in_transit = bool(st['offers'][0].get('inTransit'))
            E.player_tick(cfg, {}, st, st['tick'])
            storage_blocked = any(b['reason'] == 'storage' for b in st.get('productionBlocked', {}).values())
            stats['storageBlockedTicks'] += storage_blocked
            stats['transitTicks'] += in_transit
            stats['transitStorageBlockedTicks'] += in_transit and storage_blocked
            previous = copy.deepcopy(st['orderEngine']['lastDelivery'])
            O.refresh_board(cfg, st)
            latest = st['orderEngine']['lastDelivery']
            if latest != previous:
                stats['manualCash'] += latest['reward']
                stats['timedCash'] += latest['reward']
            if first_material_goal is None and st['materials'] >= 10:
                first_material_goal = (st['tick'] - start) * cfg['global']['tick'] / 60
    walkins = st['report']['retailEarned'] - before['report']['retailEarned']
    regulars = st['report']['customerEarned'] - before['report']['customerEarned']
    costs = st['businessOperations']['totalOperatingCosts'] - before['businessOperations']['totalOperatingCosts']
    assert st['cash'] - before['cash'] == walkins + regulars + stats['manualCash'] - costs
    goods = E.catalog(cfg)
    # Conservation includes items still physically present in timed shipments.
    produced = st['businessProgression']['activity']['produced']
    sold = st['businessProgression']['activity']['sold']
    old_activity = before['businessProgression']['activity']
    inputs = {}
    for gid, quantity in produced.items():
        quantity -= old_activity['produced'].get(gid, 0)
        for need in goods[gid].get('inputs', []):
            inputs[need['goodId']] = inputs.get(need['goodId'], 0) + quantity // goods[gid]['quantity'] * need['quantity']
    for gid in goods:
        expected = (before['inventory'].get(gid, 0) + produced.get(gid, 0) - old_activity['produced'].get(gid, 0)
                    - sold.get(gid, 0) + old_activity['sold'].get(gid, 0) - inputs.get(gid, 0))
        assert st['inventory'].get(gid, 0) == expected and expected >= 0
    return dict(stats, buildings=count, productionLevel=level, seed=seed, policy=policy,
                netCash=st['cash'] - before['cash'], walkinCash=walkins, regularCash=regulars, operatingCost=costs,
                materials=st['materials'] - before['materials'], materialGoalMinutes=first_material_goal,
                regularShipments=st['customerContracts']['deliveries'] - before['customerContracts']['deliveries'],
                completedOrders=st['cStats']['done'] - before['cStats']['done'],
                stockRetailChange=sum(goods[g]['unitPrice'] * (st['inventory'].get(g, 0) - before['inventory'].get(g, 0)) for g in goods),
                outstandingTimedCash=st['offers'][0]['reward'] if st['offers'][0].get('inTransit') else 0,
                conservationPassed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=int, default=60)
    parser.add_argument('--output', type=Path, default=ROOT / '.checks/economy-playtest/choices.json')
    args = parser.parse_args()
    cfg = E.load_config()
    results = []
    for count, level in ((1, 1), (3, 1), (6, 1), (6, 3)):
        for policy in POLICIES:
            for seed in (7, 31, 71):
                result = run(cfg, count, level, seed, policy, args.minutes)
                results.append(result)
            print(count, level, policy, 'complete', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(setup=dict(minutes=args.minutes, warmupMinutes=10,
        visits='every 30 seconds, at most one manual delivery/start per visit',
        refresh='up to five per visit, stop when a deliverable offer is found; retain one saved job',
        goal='10 materials; a benchmark, not an actual building purchase',
        stages='owned/unlocked recipes, empty initial inventory, no staff or purchased upgrades; level3 is a capacity stress case',
        money='ample operating float; net cash excludes stock value and setup purchase costs',
        limitations='scripted policies, not optimal play or evidence of human enjoyment; no rarity fishing in this experiment'),
        cases=results), indent=2) + '\n', encoding='utf8')
    print('Saved', len(results), 'cases to', args.output)


if __name__ == '__main__':
    main()
