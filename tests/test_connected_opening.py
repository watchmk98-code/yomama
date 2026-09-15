"""The connected opening must work through ordinary orders and real production."""
from __future__ import annotations

import copy
import json

import pytest

import production_economy as E
import town_projects as P


def run_connected_opening(seed):
    """Use each Market slot for one milestone, without gifts or forced rarity."""
    cfg = E.load_config()
    cfg['businessDesign']['groupProjectsEnabled'] = True
    assert P.connected(cfg), 'This scenario covers the default connected rules.'
    st = E.new_state(cfg, seed=seed)
    cls = E.new_class(cfg)
    limit = int(60 * 60 / cfg['global']['tick'])
    shipments, claims, rerolls = [], [], 0

    def view():
        payload = E.payload(cfg, st, cls, {'paused': False})
        cards = payload['contracts']['offers']
        assert len(cards) == 3 and all(not card.get('project') for card in cards)
        assert len({card['id'] for card in cards}) == 3
        return payload

    def tick():
        assert st['tick'] < limit, 'Connected opening did not finish within one simulated hour.'
        E.player_tick(cfg, cls, st, st['tick'])
        assert st['cash'] >= 0 and all(quantity >= 0 for quantity in st['inventory'].values())

    for slot, project in enumerate(P.PROJECTS):
        payload = view()
        assert payload['groupProjects']['current']['projectId'] == project['id']
        wanted = {gid for gid, _ in project['goods']}
        # Offer rotation is part of the actual game. Find a producible bundle
        # covering this stage, accepting its actual rarity, quantities and pay.
        for _ in range(600):
            order = st['offers'][slot]
            if wanted <= {need['goodId'] for need in order['requirements']}:
                break
            result = E.replace_order(cfg, st, slot, order['id'])
            assert result['ok'], result
            rerolls += 1
        else:
            pytest.fail('The ordinary board never offered the current group-project goods.')
        order = copy.deepcopy(st['offers'][slot])
        result = E.commit_order(cfg, st, slot, order['id'], True)
        assert result['ok'], result
        while not view()['contracts']['offers'][slot]['canFulfill']:
            tick()
        before_cash = st['cash']
        before_inventory = copy.deepcopy(st['inventory'])
        result = E.fulfill_order(cfg, st, slot, order['id'])
        assert result['ok'], result
        assert st['cash'] == before_cash + order['reward']
        for need in order['requirements']:
            before_inventory[need['goodId']] -= need['quantity']
        assert st['inventory'] == before_inventory, 'The group observer must not consume a second shipment.'
        shipments.append(dict(slot=slot, orderId=order['id'], rarity=order['rarity'], tick=st['tick']))
        payload = view()
        assert payload['groupProjects']['current']['canClaim']
        assert payload['groupProjects']['completed'] == slot, 'A ready achievement still requires an explicit claim.'
        if slot == 2:
            assert st.get('regularDeliveries', 0) == 0, 'The third ordinary slot must not award legacy loyalty credit.'

        before_cash = st['cash']
        before_inventory = copy.deepcopy(st['inventory'])
        result = E.claim_group_project(cfg, st, project['id'])
        assert result['ok'], result
        assert st['cash'] == before_cash + result['cashReward']
        assert st['inventory'] == before_inventory
        claims.append(dict(projectId=project['id'], reward=result['cashReward'], tick=st['tick']))
        settled = copy.deepcopy(st)
        assert not E.claim_group_project(cfg, st, project['id'])['ok']
        assert st == settled

        if project['grant']:
            tier = next(i for i, item in enumerate(cfg['tiers']) if item['id'] == project['grant'])
            quote = E.expansion_quote(cfg, st, tier)
            assert quote['constructionGrant'] and quote['cost'] == 0
            before = st['cash'], st['materials']
            result = E.expand(cfg, st, tier, st['tick'])
            assert result['ok'], result
            assert (st['cash'], st['materials']) == before
            assert P.construction_grant(cfg, st, tier) is None
            while st['build'] is not None:
                tick()
            assert tier in st['tierOf']
        # Rejoining between goals must preserve completed milestones and their
        # spent grants, without supplying goods or awarding rewards on load.
        saved = copy.deepcopy(st)
        st = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
        assert st['cash'] == saved['cash'] and st['inventory'] == saved['inventory']
        assert st[P.STATE_KEY] == saved[P.STATE_KEY]

    payload = view()
    assert payload['groupProjects']['completed'] == 3 and payload['groupProjects']['current'] is None
    assert {shipment['slot'] for shipment in shipments} == {0, 1, 2}
    assert len(shipments) == st['cStats']['done'] == 3
    assert [claim['reward'] for claim in claims] == [15, 55, 85]
    assert st['regularDeliveries'] == 3
    assert len(st['b']) == 3 and st['report']['builds'] == 2
    assert st['businessOperations']['totalOperatingCosts'] > 0
    return dict(seed=seed, minutes=st['tick'] * cfg['global']['tick'] / 60,
                rerolls=rerolls, shipments=shipments, claims=claims)


@pytest.mark.parametrize('seed', [7, 31, 97])
def test_connected_opening_runs_on_real_goods_and_all_three_order_slots(seed):
    run_connected_opening(seed)
