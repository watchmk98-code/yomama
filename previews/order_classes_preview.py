"""Preview the three fixed Market cards in memory, without a game database."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import business_progression as P
import order_engine
import production_economy as E


def sample_town(cfg, count, seed):
    state = E.new_state(cfg, seed=seed)
    state['tierOf'] = list(range(count))
    state['b'] = [E._building(tier) for tier in state['tierOf']]
    # Established sample businesses retain their unlocked products.
    state.pop('businessProgression', None)
    P.ensure(cfg, state, migrating=True)
    state['offers'] = None
    state['orderRecipeHistory'] = [[], [], []]
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--buildings', type=int, default=6)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--delivery-base-seconds', '--delivery-seconds', '--cooldown-seconds',
                        dest='cooldown_seconds', type=int, default=60,
                        help='delivery time at a 300 YM payout')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    cfg = E.load_config()
    if not 1 <= args.buildings <= len(cfg['tiers']):
        parser.error('--buildings must be between 1 and ' + str(len(cfg['tiers'])))
    if args.cooldown_seconds <= 0:
        parser.error('--delivery-base-seconds must be positive')
    state = sample_town(cfg, args.buildings, args.seed)
    board = order_engine.create_board(cfg, state, cooldown_seconds=args.cooldown_seconds)
    goods = E.catalog(cfg)
    report = dict(prototype=True, seed=args.seed,
                  assumptions='Established sample in memory; no live game changes.',
                  buildings=[cfg['tiers'][tier]['name'] for tier in state['tierOf']],
                  offers=copy.deepcopy(board['offers']))
    for profile in order_engine.class_profiles():
        index = profile['index']
        offer = board['offers'][index]
        requested = ', '.join(str(need['quantity']) + ' ' + goods[need['goodId']]['name']
                              for need in offer['requirements'])
        reward = str(offer['reward']) + ' YM'
        if offer['materials']:
            reward += ' + ' + str(offer['materials']) + ' materials'
        print('Card ' + str(index + 1) + ': ' + profile['label'] + ' — ' + offer['name'])
        if offer.get('sectorLabel'):
            print('  Sector: ' + offer['sectorLabel'])
        print('  ' + requested + ' → ' + reward)
        if index == 0:
            print('  Delivery time: ' + str(offer['deliverySeconds']) + ' seconds')
    if args.demo:
        for need in board['offers'][0]['requirements']:
            board['inventory'][need['goodId']] = need['quantity']
        cash_before = board['cash']
        payment_due = board['offers'][0]['reward']
        result = order_engine.apply_action(cfg, board, 0, 'fulfill', order_id=board['offers'][0]['id'])
        if not result['ok']:
            raise RuntimeError(result.get('why', 'Could not start sample delivery'))
        assert board['cash'] == cash_before, 'Payment must wait until arrival'
        remaining = order_engine.cooldown_remaining(cfg, board)
        print('Card 1: delivering in ' + str(remaining) + ' seconds; payment on arrival')
        report['demo'] = dict(deliverySeconds=remaining, paymentDue=payment_due,
                              sectors=[board['offers'][1]['sectorLabel']])
        for _ in range(3):
            result = order_engine.apply_action(cfg, board, 1, 'replace', order_id=board['offers'][1]['id'])
            if not result['ok']:
                raise RuntimeError(result.get('why', 'Could not replace sample sector order'))
            report['demo']['sectors'].append(board['offers'][1]['sectorLabel'])
        print('Card 2 automatic sectors: ' + ' → '.join(report['demo']['sectors']))
        board['tick'] += remaining // cfg['global']['tick']
        order_engine.refresh_board(cfg, board)
        assert board['cash'] == cash_before + payment_due, 'Delivery pays on arrival'
        report['demo']['nextDeliveryOrder'] = board['offers'][0]['name']
        print('Card 1 arrived: +' + str(payment_due) + ' YM; next order: ' + board['offers'][0]['name'])
        assert board['offers'][2] == report['offers'][2], 'The third card must stay unchanged'
        print('Card 3: original order preserved')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
