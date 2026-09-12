"""Workshop access, town isolation, and lasting recipe choices through real rules."""
import copy
import json

import pytest

import breakfast_event as B
import production_economy as E


def town(roastery=False):
    cfg = E.load_config()
    st = E.new_state(cfg)
    if roastery:
        ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == 'roastery')
        st['b'].append(E._building(ti))
        st['tierOf'].append(ti)
    return cfg, st


def call(cfg, st, now, action, **kwargs):
    result = B.act(st, now, dict(action=action, **kwargs), cfg=cfg)
    assert result['ok'], result
    return result


def test_farm_cannot_start_workshop_or_bypass_gate_with_browser_fields():
    cfg, st = town()
    before = copy.deepcopy(st)
    p = B.payload(st, 0, cfg=cfg)
    assert p['status'] == 'new' and p['locked']
    assert 'roastery' in p['unlockText']
    for request in ({'action': 'start'}, {'action': 'start', 'locked': False, 'tierOf': [2]}):
        result = B.act(st, 0, request, cfg=cfg)
        assert not result['ok'] and result['why'] == p['unlockText']
    assert st == before


def test_queued_or_unfinished_roastery_does_not_unlock_workshop():
    cfg, st = town()
    ti = next(i for i, tier in enumerate(cfg['tiers']) if tier['id'] == 'roastery')
    st['queue'] = [ti]
    assert B.payload(st, 0, cfg=cfg)['locked']
    st['queue'] = []
    st['build'] = dict(i=ti, t=12)
    assert not B.act(st, 0, {'action': 'start'}, cfg=cfg)['ok']
    E.finish_build(cfg, st, 12)
    assert not B.payload(st, 180, cfg=cfg)['locked']
    call(cfg, st, 180, 'start')
    assert st['breakfastEvent']['started'] == 180


def test_roastery_is_resolved_by_id_in_the_class_configuration():
    cfg, st = town()
    cfg['tiers'][1], cfg['tiers'][2] = cfg['tiers'][2], cfg['tiers'][1]
    st['b'].append(E._building(2))
    st['tierOf'].append(2)
    assert B.payload(st, 0, cfg=cfg)['locked'], 'Tier two is now the fish stall.'
    st['b'].append(E._building(1))
    st['tierOf'].append(1)
    assert not B.payload(st, 0, cfg=cfg)['locked']
    call(cfg, st, 0, 'start')


def test_missing_config_cannot_bypass_a_town_gate_but_standalone_workshop_remains_supported():
    _, st = town(roastery=True)
    assert B.payload(st, 0)['locked']
    assert not B.act(st, 0, {'action': 'start'})['ok']
    standalone = dict(materials=0)
    assert B.act(standalone, 0, {'action': 'start'})['ok']
    assert not B.payload(standalone, 0)['locked']


def test_workshop_describes_its_separate_resources_and_unselected_reward():
    cfg, st = town(roastery=True)
    p = B.payload(st, 0, cfg=cfg)
    assert p['suppliesLabel'] == 'Workshop supplies'
    assert p['coinsLabel'] == 'Practice coins'
    assert 'queued batch' in p['purpose']
    assert p['reward'] == 5 and 'four orders' in p['rewardDescription']
    assert p['townPerk'].startswith('Choose espresso or pastries')
    assert p['specializations']['coffee']['goodId'] == 'roastery_espresso_shots'
    assert p['specializations']['pastry']['goodId'] == 'roastery_pastries'
    assert all('ingredients' in v['workshopPerk'] for v in p['specializations'].values())


@pytest.mark.parametrize('specialization', ['coffee', 'pastry'])
def test_complete_workshop_preserves_town_resources_and_improves_only_chosen_recipe(specialization):
    cfg, st = town(roastery=True)
    st['cash'] = 1000
    st['materials'] = 7
    st['inventory'] = {'farm_eggs': 20, 'farm_honey': 10}
    before_inventory = copy.deepcopy(st['inventory'])
    call(cfg, st, 0, 'start')
    now = 0
    for order_id in ('first', specialization, 'mixed', 'final'):
        if order_id == 'final':
            call(cfg, st, now, 'upgrade', recipe=specialization)
            roastery = st['b'][1]
            assert all(E.product_speed(cfg, st, roastery, good) == 100
                       for good in cfg['tiers'][roastery['tier']]['goods'])
        order = next(o for o in B.payload(st, now, cfg=cfg)['orders'] if o['id'] == order_id)
        for name, quantity in order['needs'].items():
            while st['breakfastEvent']['stock'][name] < quantity:
                call(cfg, st, now, 'make', recipe=name)
                while st['breakfastEvent']['active'] or st['breakfastEvent']['queued']:
                    now += 15
                    B.advance(st, now)
                    assert now <= 900
        call(cfg, st, now, 'deliver', orderId=order_id)
    assert st['cash'] == 1000 and st['inventory'] == before_inventory
    assert st['materials'] == 12
    p = B.payload(st, now, cfg=cfg)
    assert p['status'] == 'done' and not p['locked']
    assert p['coins'] == 0 and p['rewardDescription'].startswith('Earned once:')
    selected_id = p['specializations'][specialization]['goodId']
    roastery = st['b'][1]
    for good in cfg['tiers'][roastery['tier']]['goods']:
        assert E.product_speed(cfg, st, roastery, good) == (125 if good['id'] == selected_id else 100)
    restored = E.State(json.loads(json.dumps(st)))
    saved = copy.deepcopy(restored)
    call(cfg, restored, now + 86400, 'start')
    B.advance(restored, now + 86400)
    assert restored == saved


def test_old_started_workshop_keeps_progress_without_roastery_and_rewards_once():
    cfg, st = town()
    old_workshop = dict(materials=0)
    assert B.act(old_workshop, 100, {'action': 'start'})['ok']
    st['breakfastEvent'] = old_workshop['breakfastEvent']
    st['breakfastEvent'].update(stage=4, upgrade='coffee', coins=40)
    st['breakfastEvent']['stock'].update(coffee=4, pastry=4)
    before = copy.deepcopy(st)
    call(cfg, st, 100, 'start')
    assert st == before
    assert not B.payload(st, 100, cfg=cfg)['locked']
    call(cfg, st, 100, 'deliver', orderId='final')
    assert st['materials'] == 5
    restored = E.State(json.loads(json.dumps(st)))
    saved = copy.deepcopy(restored)
    call(cfg, restored, 200, 'start')
    assert not B.act(restored, 200, dict(action='deliver', orderId='final'), cfg=cfg)['ok']
    assert restored == saved and not B.payload(restored, 200, cfg=cfg)['locked']
