"""Paired real-play checks for sale settlement; never opens a database."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import business_operations as operations
import operating_margins as margins
import production_economy as economy
import rules_tables


ADDED_FIELDS = frozenset(('operatingMargins', 'operatingStatement', 'sellingTerms'))
LEVELS = {'base': (1, 1, 1), 'max': (12, 12, 12),
          'production-heavy': (4, 1, 1), 'sales-heavy': (1, 4, 1)}
ROSTER = ('copper_cafe', 'rally_crew', 'builders_union', 'neighborhood_grid')


def economic_state(value):
    """Ignore only added invoice accounting; retain all gameplay state."""
    if isinstance(value, dict):
        return {key: economic_state(item) for key, item in value.items() if key not in ADDED_FIELDS}
    if isinstance(value, list):
        return [economic_state(item) for item in value]
    return value


def prepare(enabled, tiers, level='base', seed=71, fresh=False):
    cfg = economy.load_config()
    cfg.setdefault('operatingMargins', {})['enabled'] = enabled
    state = economy.new_state(cfg, seed=seed)
    if not fresh:
        production, customers, storage = LEVELS[level]
        state['cash'] = 1_000_000
        state['tierOf'] = list(tiers)
        state['b'] = [economy._building(tier, lv=production, sales=customers, storage=storage) for tier in tiers]
        state['businessProgression']['grandfathered'] = [cfg['tiers'][tier]['id'] for tier in tiers]
        operations.ensure(cfg, state)
        margins.ensure(cfg, state)
        state['offers'] = None
        state['orderRecipeHistory'] = [[], [], []]
        economy.offer_contracts(cfg, state, state['tick'])
    return cfg, state


def _coverage(cfg, state, order):
    held = economy.delivery_reservations(cfg, state, exclude=order['id'])
    total = sum(need['quantity'] for need in order['requirements'])
    have = sum(min(need['quantity'], max(0, state['inventory'].get(need['goodId'], 0)
                                        - held.get(need['goodId'], 0))) for need in order['requirements'])
    return have / max(1, total)


def manual_visit(cfg, state):
    """One ordinary Market choice: deliver ready goods or save one offer."""
    ready = [(index, order) for index, order in enumerate(state['offers']) if _coverage(cfg, state, order) == 1]
    if ready:
        index, order = max(ready, key=lambda row: (row[1]['materials'], row[1]['reward']))
        result = economy.fulfill_order(cfg, state, index, order['id'])
        assert result['ok'], result
        return result
    if not any(order.get('committed') for order in state['offers']):
        ranked = sorted(enumerate(state['offers']),
                        key=lambda row: (_coverage(cfg, state, row[1]), row[1]['materials'], row[1]['reward']), reverse=True)
        for index, order in ranked:
            result = economy.commit_order(cfg, state, index, order['id'], True)
            if result['ok']:
                return result
        index, order = ranked[-1]
        return economy.replace_order(cfg, state, index, order['id'])
    return None


def _payment_totals(state):
    return state.get('operatingMargins', {}).get('totals', dict(takeHome=0, grossSales=0, sellingCosts=0))


def run_pair(tiers, level='base', seed=71, ticks=96, warm_ticks=0, policy='walkins', fresh=False, mature=False):
    pairs = [prepare(enabled, tiers, level, seed, fresh) for enabled in (False, True)]
    for cfg, state in pairs:
        with rules_tables.pinned(cfg):
            for building in state['b']:
                building['reserve'] = bool(warm_ticks)
            for _ in range(warm_ticks):
                economy.player_tick(cfg, {}, state, state['tick'])
            if mature:
                assert all(state['inventory'].get(good['id'], 0) == economy._good_capacity(cfg, state, slot, good['id'])
                           for slot, building in enumerate(state['b']) for good in cfg['tiers'][building['tier']]['goods'])
            for building in state['b']:
                building['reserve'] = False
            if policy == 'regulars-manual':
                eligible = {buyer['id']: buyer for buyer in economy._customer_catalog(cfg, state) if buyer['available']}
                selected = [buyer for buyer in ROSTER if buyer in eligible]
                if fresh:
                    selected = list(eligible)[:economy._customer_slots(state)]
                for slot, buyer_id in enumerate(selected):
                    result = economy.manage_customer_contract(cfg, state, slot, 'accept', buyer_id)
                    assert result['ok'], result
    assert economic_state(pairs[0][1]) == economic_state(pairs[1][1])
    opening = [copy.deepcopy(state) for _, state in pairs]
    manual_income = [0, 0]
    for tick in range(ticks):
        results = []
        for index, (cfg, state) in enumerate(pairs):
            with rules_tables.pinned(cfg):
                action = manual_visit(cfg, state) if policy == 'regulars-manual' and tick % 2 == 0 else None
                if action and action.get('ok'):
                    manual_income[index] += action.get('reward', 0)
                economy.player_tick(cfg, {}, state, state['tick'])
                if tick % 13 == 0:
                    # Affordability is part of progression, even if the policy
                    # does not spend its staged benchmark capital on upgrades.
                    costs = [(economy.upgrade_cost(cfg, state, slot, kind), state['cash'])
                             for slot in range(len(state['b'])) for kind in ('production', 'sales', 'storage')]
                else:
                    costs = None
            results.append((economic_state(action), costs))
        assert results[0] == results[1], ('actions/affordability', tiers, level, seed, tick)
        assert economic_state(pairs[0][1]) == economic_state(pairs[1][1]), ('state', tiers, level, seed, tick)
    reports = []
    for index, ((cfg, state), before) in enumerate(zip(pairs, opening)):
        walkins = state['report']['retailEarned'] - before['report']['retailEarned']
        regulars = state['report']['customerEarned'] - before['report']['customerEarned']
        production = state['businessOperations']['totalOperatingCosts'] - before['businessOperations']['totalOperatingCosts']
        gross = _payment_totals(state)['grossSales'] - _payment_totals(before)['grossSales']
        selling = _payment_totals(state)['sellingCosts'] - _payment_totals(before)['sellingCosts']
        take_home = _payment_totals(state)['takeHome'] - _payment_totals(before)['takeHome']
        net_cash = state['cash'] - before['cash']
        if margins.enabled(cfg):
            assert gross - selling == take_home
            assert gross - selling - production == net_cash
        assert net_cash == walkins + regulars + manual_income[index] - production
        activity, old_activity = state['businessProgression']['activity'], before['businessProgression']['activity']
        for gid in economy.catalog(cfg):
            made = activity['produced'].get(gid, 0) - old_activity['produced'].get(gid, 0)
            sold = activity['sold'].get(gid, 0) - old_activity['sold'].get(gid, 0)
            assert state['inventory'].get(gid, 0) == before['inventory'].get(gid, 0) + made - sold
        for totals in state.get('operatingMargins', {}).get('bySource', {}).values():
            assert totals['grossSales'] - totals['sellingCosts'] == totals['takeHome']
        reports.append(dict(netCash=net_cash, grossSales=gross, sellingCosts=selling,
                            productionCosts=production, walkinCash=walkins, regularCash=regulars,
                            completedOrders=state['cStats']['done'] - before['cStats']['done'],
                            materials=state['materials'] - before['materials'],
                            regularShipments=state['customerContracts']['deliveries'] - before['customerContracts']['deliveries'],
                            netWorth=economy.net_worth(cfg, state), endingStock=sum(state['inventory'].values()),
                            cashMarginPercent=net_cash / gross * 100 if gross else None,
                            conservationPassed=True))
    for key in ('netCash', 'productionCosts', 'walkinCash', 'regularCash', 'completedOrders',
                'materials', 'regularShipments', 'netWorth', 'endingStock'):
        assert reports[0][key] == reports[1][key], key
    return dict(tiers=list(tiers), level=level, seed=seed, ticks=ticks, warmTicks=warm_ticks,
                policy=policy, fresh=fresh, mature=mature,
                baseline=reports[0], changed=reports[1], identicalGameplay=True)


def mature_scenarios():
    for tier in range(15):
        cfg, state = prepare(True, [tier])
        warm_ticks = max(good['cycleTicks'] * economy._good_capacity(cfg, state, 0, good['id'])
                         for good in cfg['tiers'][tier]['goods']) + 8
        yield dict(tiers=[tier], warm_ticks=warm_ticks, mature=True)


def scenarios():
    for tier in range(15):
        for level in LEVELS:
            for warm in (0, 48):
                yield dict(tiers=[tier], level=level, warm_ticks=warm)
    for count in (6, 15):
        for seed in (7, 31, 71):
            for level in ('base', 'max'):
                for warm in (0, 48):
                    yield dict(tiers=list(range(count)), level=level, seed=seed,
                               warm_ticks=warm, policy='regulars-manual')
    for policy in ('walkins', 'regulars-manual'):
        yield dict(tiers=[0], policy=policy, fresh=True)
    yield from mature_scenarios()


def write_report(path, results):
    cfg = economy.load_config()
    lines = ['# Operating margin playtest', '',
             'Reproduce: `.venv/bin/python previews/playtest_operating_margins.py`.', '',
             '{} matched scenarios / {} runs. Each measured run covers 24 game minutes. Ordinary warm starts first earn stock through 12 minutes of production with walk-in sales held. Fifteen additional maturity checks fill the real shelves through 62–202 game minutes of ordinary production before measurement. No inventory is inserted.'.format(len(results), 2 * len(results)),
             'Established towns have identical 1,000,000 YM capital, installed levels and quest-unlocked products. Fresh cases use the real zero-cash starter farm. Base is level 1 throughout; maximum is level 12 throughout; production-heavy is Production 4 / Customers 1, sales-heavy is 1 / 4. Nonmaximum storage is level 1.', '',
             'Every paired tick retained identical gameplay state after excluding only the new invoice ledger, frozen selling terms and operating statement. Cash, production costs/carry, inventory, offers, reward amounts, timers, materials, quests, net receipts, affordability and net worth matched exactly. Each enabled run also reconciled gross invoices minus selling fees minus production spending to its cash change, and each product reconciled opening stock plus production minus sales to closing stock.', '',
             '## Targets and measured ordinary sales', '',
             'These are base-level targets with all output sold: game-rounded, industry-inspired reference margins, not empirical forecasts for individual real businesses or guaranteed ordinary-play results. A fixed product tariff is calibrated using the reference selling price and base production cost. Mature base production matching sales approaches the target; upgrades, buyer discounts and temporary spending on unsold stock still change the resulting margin.', '',
             '| Business | Base-level target (all output sold) | Base, empty stock | Base, 12-minute warm stock | Base, mature full shelves | Maximum levels, warm stock |',
             '|---|---|---|---|---|---|']
    for tier, building in enumerate(cfg['tiers']):
        values = []
        for level, warm in (('base', 0), ('base', 48), ('base', None), ('max', 48)):
            row = next(r for r in results if r['tiers'] == [tier] and not r['fresh'] and r['level'] == level
                       and (r.get('mature') if warm is None else r['warmTicks'] == warm))
            margin = row['changed']['cashMarginPercent']
            values.append('{:.2f}%'.format(margin) if margin is not None else '—')
        lines.append('| {} | {}% | {} |'.format(building['name'], margins.target_margin(cfg, building['id']), ' | '.join(values)))
    mature = [r for r in results if r.get('mature')]
    largest_error = max(abs(r['changed']['cashMarginPercent'] - margins.target_margin(cfg, cfg['tiers'][r['tiers'][0]]['id'])) for r in mature)
    lines += ['', 'After shelves have filled through real production, all fifteen base businesses remain within {:.2f} percentage points of their reference target over the 24-minute measurement. Earlier margins are lower because production is also funding stock accumulation. Maximum upgrades retain their existing cost tradeoff; the targets are not forced onto those configurations.'.format(largest_error)]
    lines += ['', '## Normal orders and regular buyers', '',
              'The policy visits the normal Market every 30 seconds, fulfills a ready offer (materials then net reward), or saves one reachable offer and waits. It uses real fulfill/commit/replace functions. Four eligible recurring buyers cover all three sectors in established towns. No prototype board is used in these simulations.', '',
              '| Town | Matched scenarios | Net cash before → after | Completed orders | Materials | Regular shipments |',
              '|---|---|---|---|---|---|']
    for count in (6, 15):
        rows = [r for r in results if len(r['tiers']) == count]
        values = []
        for key in ('netCash', 'completedOrders', 'materials', 'regularShipments'):
            values.append('{} → {}'.format(sum(r['baseline'][key] for r in rows), sum(r['changed'][key] for r in rows)))
        lines.append('| {} businesses | {} | {} |'.format(count, len(rows), ' | '.join(values)))
    lines += ['', '## Accounting scope and limits', '',
              'This adds a modeled product supply/selling charge reimbursed through the customer invoice and paid immediately from the same proceeds. Gross sales and expenses both increase; money left for the player and the original choices do not change. It is an accounting-model change, not evidence of a new tradeoff or better real-world market simulation.',
              'Statements remain on a cash basis. Production spending is charged when output is made, including unsold goods; no cost-of-goods-sold inventory accounting, fixed rent, financing, tax or depreciation model is introduced. Inventory and net worth keep their existing reference-retail valuation; that is not historical cost basis. The regular buyer still leaves 90% of the reference reward before production costs, while the reimbursed tariff makes its gross invoice discount smaller.',
              'Whole-YM settlement uses an independent fractional carry per business and sale channel. Tariffs do not rise with upgrades or follow a higher manual reward. Saved invoice tariffs survive reloads and configuration changes; old receipts never receive invented retroactive fees. New unit tests separately cover normal and goal deliveries, prototype delayed delivery, replay prevention, source accounting, zero-cash sales, paused/full shelves and removed-business reconciliation.',
              'The sample proves deterministic progression preservation for its tested paths. It does not prove every future rule interaction or that children understand the gross/net distinction; UI review remains necessary.', '',
              'Full paired output: `.checks/economy-playtest/operating-margins.json`.', '']
    path.write_text('\n'.join(lines), encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.checks/economy-playtest/operating-margins.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'OPERATING_MARGINS_PLAYTEST.md')
    args = parser.parse_args()
    results = []
    for spec in scenarios():
        results.append(run_pair(**spec))
        if len(results) % 20 == 0:
            print('{} exact matched scenarios complete'.format(len(results)), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf8')
    write_report(args.report, results)
    print('{} matched scenarios passed; report {}'.format(len(results), args.report), flush=True)


if __name__ == '__main__':
    main()
