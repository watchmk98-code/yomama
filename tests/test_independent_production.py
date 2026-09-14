"""Automatic goods are independent; cash, storage and quest rules still apply."""
from __future__ import annotations

import copy
import json

import pytest

import business_operations as operations
import business_progression as progression
import game_api as api
import production_economy as economy
from test_access_integration import db, opened  # noqa: F401


def independent_town(cfg, tiers, unlock=True):
    state = economy.new_state(cfg, seed=37)
    state['cash'] = 1_000_000
    state['tierOf'] = list(tiers)
    state['b'] = [economy._building(tier) for tier in tiers]
    for building in state['b']:
        building['reserve'] = True
    if unlock:
        state['businessProgression']['grandfathered'] = [cfg['tiers'][tier]['id'] for tier in tiers]
    operations.ensure(cfg, state)
    return state


def make_batches(cfg, state, count=8):
    for _ in range(count):
        economy._produce(cfg, state)


def test_every_business_makes_all_unlocked_products_from_empty_stock():
    cfg = economy.load_config()
    config_before = copy.deepcopy(cfg)
    produced = set()
    for index, tier in enumerate(cfg['tiers']):
        state = independent_town(cfg, [index])
        assert not state['inventory']
        make_batches(cfg, state, max(g['cycleTicks'] for g in tier['goods']) * 2)
        expected = {good['id'] for good in tier['goods']}
        assert set(state['inventory']) == expected
        assert all(state['inventory'][good['id']] >= good['quantity'] for good in tier['goods'])
        produced.update(state['inventory'])
    assert produced == set(economy.catalog(cfg))
    assert cfg == config_before, 'Dormant recipe metadata remains available for future manual crafting.'


def test_production_never_consumes_same_business_or_other_business_goods():
    cfg = economy.load_config()
    state = independent_town(cfg, [0, 2])
    state['b'][0]['paused'] = True
    state['inventory'].update(farm_eggs=5, farm_honey=5, roastery_roasted_beans=5)
    make_batches(cfg, state, 4)
    assert state['inventory']['farm_eggs'] == 5
    assert state['inventory']['farm_honey'] == 5
    assert state['inventory']['roastery_roasted_beans'] == 9
    assert state['inventory']['roastery_espresso_shots'] == 2
    assert state['inventory']['roastery_pastries'] == 1
    assert economy.chain_reservations(cfg, state) == {}


@pytest.mark.parametrize('target,other', [(0, 2), (2, 0)])
def test_forecast_sales_costs_and_profit_ignore_former_supplier_relationship(target, other):
    cfg = economy.load_config()
    alone = independent_town(cfg, [target])
    together = independent_town(cfg, [target, other])
    for state in (alone, together):
        state['b'][0]['reserve'] = False

    def forecast(state):
        data = economy.payload(cfg, state, {}, {'paused': False})['buildings'][0]
        return (data['incomePerMinute'], data['potentialOperatingCostPerMinute'],
                data['potentialProfitPerMinute'], data['productionPerMinute'])

    expected = forecast(alone)
    assert forecast(together) == expected
    together['b'][1].update(lv=7, sales=8, storage=6)
    assert forecast(together) == expected
    together['b'][1]['paused'] = True
    assert forecast(together) == expected


def test_migration_retires_recipe_pause_and_warnings_without_repricing_saved_state():
    cfg = economy.load_config()
    state = economy.migrate_state(cfg, independent_town(cfg, [0, 2]))
    state.pop('productionMode')
    state['b'][1]['processing'] = False
    state['inventory'].update(farm_eggs=3, roastery_pastries=2)
    state['productionWork'].update(farm_eggs=175, roastery_pastries=375)
    state['productionBlocked'] = {'roastery_pastries': dict(reason='ingredient', goodId='farm_honey'),
                                  'farm_eggs': dict(reason='storage')}
    state['offers'][0]['committed'] = True
    state['offers'][0]['savedMarker'] = {'keep': [1, 2]}
    state['businessOperations']['totalOperatingCosts'] = 23
    state['businessOperations']['totalStaffCosts'] = 9
    state['b'][0]['costRemainder'] = 125_000
    expected = copy.deepcopy(state)
    expected['productionMode'] = 'independent'
    expected['b'][1]['processing'] = True
    expected['productionBlocked'].pop('roastery_pastries')
    migrated = economy.migrate_state(cfg, economy.State(json.loads(json.dumps(state))))
    assert migrated == expected
    assert economy.migrate_state(cfg, migrated) == expected


def test_payload_advertises_independent_production_without_automatic_recipe_controls():
    cfg = economy.load_config()
    state = independent_town(cfg, range(len(cfg['tiers'])))
    data = economy.payload(cfg, state, {}, {'paused': False})
    assert data['productionMode'] == 'independent'
    for building in data['buildings']:
        assert building['recipes'] == [] and building['recipe'] is None
        assert building['hasRecipes'] is False
        assert all(row['inputs'] == [] for row in building['goods'])
    assert any(good.get('inputs') for tier in cfg['tiers'] for good in tier['goods'])


def test_obsolete_processing_endpoint_rejects_toggle_without_changing_the_save(db, monkeypatch):
    monkeypatch.setattr(api, 'econ_clock_seconds', lambda session: 0)
    session = opened(db, label='INDEPENDENT PRODUCTION')
    seat = api.join(dict(code=session['code'], name='BUILDER', pin='1234'))
    before = api.econ_state({'token': seat['token']})
    with api.connect() as conn:
        saved = conn.execute('SELECT econ FROM players WHERE token=?', (seat['token'],)).fetchone()['econ']
    for enabled in (False, True):
        with pytest.raises(api.ApiError, match='Products are made independently') as caught:
            api.econ_processing(dict(token=seat['token'], slot=0, enabled=enabled))
        assert caught.value.status == 400
    after = api.econ_state({'token': seat['token']})
    assert after['cash'] == before['cash']
    assert after['buildings'][0]['processing'] is True
    with api.connect() as conn:
        assert conn.execute('SELECT econ FROM players WHERE token=?', (seat['token'],)).fetchone()['econ'] == saved


def test_cash_and_shelf_limits_still_block_independent_batches():
    cfg = economy.load_config()
    state = independent_town(cfg, [2])
    state['cash'] = 0
    make_batches(cfg, state)
    assert not state['inventory']
    assert all(reason['reason'] == 'cash' for reason in state['productionBlocked'].values())
    state['cash'] = 100
    for good in cfg['tiers'][2]['goods']:
        state['inventory'][good['id']] = economy._good_capacity(cfg, state, 0, good['id'])
    before = copy.deepcopy(state['inventory'])
    make_batches(cfg, state)
    assert state['inventory'] == before and state['cash'] == 100
    assert all(reason['reason'] == 'storage' for reason in state['productionBlocked'].values())


def test_quest_locks_and_business_pause_still_control_production():
    cfg = economy.load_config()
    state = independent_town(cfg, [3], unlock=False)
    make_batches(cfg, state)
    assert state['inventory']['garage_spare_parts'] > 0
    assert state['inventory'].get('garage_custom_mods', 0) == 0
    assert state['productionBlocked']['garage_custom_mods']['reason'] == 'quest'
    progression.ensure(cfg, state)['quests']['garage-plan'] = dict(completed=True)
    make_batches(cfg, state)
    assert state['inventory']['garage_custom_mods'] > 0
    state['b'][0]['paused'] = True
    before = (copy.deepcopy(state['inventory']), state['cash'], copy.deepcopy(state['productionWork']))
    make_batches(cfg, state)
    assert (state['inventory'], state['cash'], state['productionWork']) == before


def test_roastery_project_no_longer_requires_a_farm_or_lists_ingredient_suppliers():
    cfg = economy.load_config()
    state = independent_town(cfg, [2])
    state['townProjects']['completed'] = 2
    project = economy.town_projects.current_order(cfg, state)
    assert economy.town_projects.check(cfg, state, project['id'])['ok']
    suppliers = economy.town_projects.group_payload(cfg, state)['current']['suppliers']
    assert [supplier['buildingId'] for supplier in suppliers] == ['roastery']
