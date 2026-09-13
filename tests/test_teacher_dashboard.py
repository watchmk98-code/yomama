"""Teacher progress reflects the same current rules and stock as each town."""
import pytest

import game_api as A
import economy as legacy
import production_economy as E
from test_game_api import world  # noqa: F401
from test_production_api import town, edit, state  # noqa: F401


def dashboard(teacher):
    return A.teacher_econ({'teacher_token': [teacher['teacher_token']]})


def student(teacher, name='ALICE'):
    return next(p for p in dashboard(teacher)['students'] if p['name'] == name)


def test_completed_deliveries_do_not_stop_at_the_licence_target(town):
    _, teacher, players = town
    token = players[0]['token']
    target = E.load_config()['gate']['goodSalesNeeded']
    for _ in range(target + 2):
        offer = state(token)['contracts']['offers'][0]
        def supply(cfg, st):
            for need in offer['requirements']:
                st['inventory'][need['goodId']] = need['quantity']
        edit(token, supply)
        assert student(teacher)['readyDeliveries'] >= 1
        A.econ_fulfill_order(dict(token=token, offerIndex=0, orderId=offer['id']))
    result = student(teacher)
    own = state(token)
    assert result['checklist']['goodSales'] >= target
    assert result['deliveriesCompleted'] == target + 2
    assert result['cash'] == own['cash']
    assert result['materials'] == own['materials']
    assert result['deliverySlots'] == len(own['contracts']['offers'])
    if 'operations' in own:
        assert result['operations'] == own['operations']
    if 'progression' in own:
        progression = result['progression']
        assert progression['enabled'] == own['progression']['enabled']
        assert progression['knowHow'] == own['progression']['knowHow']
        assert progression['prestige'] == own['progression']['prestige']
        assert progression['questsCompleted'] == sum(q['status'] == 'done' for q in own['progression']['quests'])
        assert progression['questsReady'] == sum(bool(q['ready']) for q in own['progression']['quests'])
        assert progression['researchCompleted'] == sum(bool(r['owned']) for r in own['progression']['research'])
        assert progression['equipmentOwned'] == sum(e['quantity'] for e in own['progression']['equipment'])
    assert student(teacher, 'BOB')['deliveriesCompleted'] == 0


def test_regular_customer_summary_distinguishes_waiting_and_paused(town):
    now, teacher, players = town
    token = players[0]['token']
    options = [c for c in state(token)['customerContracts']['customers'] if c['available']]
    for slot, customer in enumerate(options[:2]):
        A.econ_customers(dict(token=token, action='accept', slot=slot, customerId=customer['id']))
    initial = student(teacher)['customerContracts']
    assert (initial['active'], initial['supplying'], initial['waiting'], initial['paused']) == (2, 2, 0, 0)
    now[0] += max(c['intervalSeconds'] for c in options[:2]) * 2
    own = state(token)
    assert own['customerContracts']['deliveries'] > 0
    second = own['customerContracts']['active'][1]
    A.econ_customers(dict(token=token, action='pause', slot=1, contractId=second['id']))
    def empty_due_customer(cfg, st):
        first = st['customerContracts']['active'][0]
        first['nextDeliveryTick'] = st['tick']
        for need in first['requirements']:
            st['inventory'][need['goodId']] = 0
    edit(token, empty_due_customer)
    actual = student(teacher)['customerContracts']
    assert (actual['active'], actual['supplying'], actual['waiting'], actual['paused']) == (2, 0, 1, 1)
    assert actual['deliveries'] == own['customerContracts']['deliveries']
    assert actual['earned'] == own['customerContracts']['earned']
    assert student(teacher, 'BOB')['customerContracts']['active'] == 0


def test_goods_sold_can_satisfy_licence_without_manual_deliveries(town):
    _, teacher, players = town
    token = players[0]['token']
    def prepare(cfg, st):
        st['tierOf'] = list(range(cfg['global']['gateTier']))
        st['b'] = [E._building(tier, cfg['gate']['levelNeeded'], 2) for tier in st['tierOf']]
        st['checklist'].update(lv25=True, auto=True)
        st['report']['unitsSold'] = 100
        first = cfg['tiers'][0]['goods'][0]['id']
        st['inventory'][first] = E._good_capacity(cfg, st, 0, first)
    edit(token, prepare)
    ready = student(teacher)
    assert ready['deliveriesCompleted'] == 0
    assert ready['customerUnitsSold'] == ready['customerUnitsNeeded']
    assert ready['checklist']['quiz'] is False and not ready['gateOpen']
    assert ready['buildings'][0]['status'] == 'Storage full'
    assert 0 < ready['warehouseStored'] < ready['warehouseCap']
    requirements = dashboard(teacher)['licenceRequirements']
    assert requirements['productionLevel'] == E.load_config()['gate']['levelNeeded']
    assert requirements['buildings'] == ready['tier']
    quiz = A._load_quiz()
    A.econ_quiz(dict(token=token, answers=[q['answer'] for q in quiz['questions']]))
    assert student(teacher)['gateOpen']
    assert not student(teacher, 'BOB')['gateOpen']


def test_dashboard_retains_legacy_class_support_and_authentication(world):
    _, teacher, _ = world
    with pytest.raises(A.ApiError):
        A.teacher_econ({})
    result = dashboard(teacher)
    assert result['modelVersion'] == 3
    assert result['count'] == 2
    assert result['licenceRequirements']['productionLevel'] == legacy.load_config()['gate']['levelNeeded']
    assert result['licenceRequirements']['buildings'] == legacy.load_config()['global']['gateTier']
    assert 'customerUnits' not in result['licenceRequirements']
    assert 'customerContracts' not in result['students'][0]
    assert result['students'][0]['rank'] == 1
    assert 'cash' in result['students'][0]
