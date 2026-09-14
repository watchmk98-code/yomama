"""Real opening transactions, grants, stock conflicts and bounded play policies."""
from __future__ import annotations

import copy
import json
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest

import game_api as A
import production_economy as E
import town_projects as P


def legacy_config():
    """Keep these fixed-project tests on their original saved v4 rules."""
    cfg = E.load_config()
    cfg.setdefault('businessDesign', {}).pop('connectedProgression', None)
    return cfg


def tier(cfg, building_id):
    return next(i for i, item in enumerate(cfg['tiers']) if item['id'] == building_id)


def view(cfg, st):
    return E.payload(cfg, st, E.new_class(cfg), {'paused': False})


def run_opening(seed=0, policy='baseline', decision_ticks=4, limit_minutes=60):
    """Follow actual guide/transactions; every decision_ticks uses one goal action.

    No free cash, stock, time advances, or direct progress edits are used. The
    optional upgrade policy spends all affordable cash before the goal action.
    Other-job reservations are intentionally left parked to expose interference.
    """
    cfg = legacy_config()
    st = E.new_state(cfg, seed=seed)
    cls = E.new_class(cfg)
    events, errors, opened = [], [], set(st['tierOf'])
    if policy in ('buyers', 'buyers_upgrades', 'buyers_pause'):
        for slot, name in enumerate(('corner_grocer', 'sunrise_diner')):
            assert E.manage_customer_contract(cfg, st, slot, 'accept', customer_id=name)['ok']
    if policy in ('other_orders', 'other_orders_recover'):
        for index in (0, 1):
            result = E.commit_order(cfg, st, index, st['offers'][index]['id'], True)
            if not result['ok']:
                errors.append(dict(tick=0, action='commit_other', reason=result['why']))
    total_ticks = int(limit_minutes * 60 / cfg['global']['tick'])
    for tick in range(total_ticks + 1):
        if tick % decision_ticks == 0:
            state = view(cfg, st)
            if state['townProjects']['status'] == 'complete':
                break
            if policy in ('upgrades', 'buyers_upgrades'):
                while True:
                    options = [(E.upgrade_cost(cfg, st, slot, kind), slot, kind)
                               for slot in range(len(st['b'])) for kind in ('production', 'sales', 'storage')]
                    options = sorted(x for x in options if x[0] is not None and x[0] <= st['cash'])
                    if not options:
                        break
                    _, slot, kind = options[0]
                    assert E.buy_upgrade(cfg, st, slot, kind)['ok']
                    events.append(dict(tick=st['tick'], action='upgrade', slot=slot, kind=kind))
                state = view(cfg, st)
            step = state.get('nextStep') or {}
            if str(step.get('action', '')).startswith('expand:'):
                target = int(step['action'].split(':')[1])
                before = st['cash'], st['materials']
                result = E.expand(cfg, st, target, st['tick'])
                assert result['ok'], result
                assert (st['cash'], st['materials']) == before
                events.append(dict(tick=st['tick'], action='build', building=cfg['tiers'][target]['id']))
            else:
                order = state['contracts']['offers'][2]
                if order.get('project') and not order.get('locked'):
                    if policy == 'buyers_pause' and not order['canFulfill']:
                        for customer in st['customerContracts']['active']:
                            if not customer['paused']:
                                assert E.manage_customer_contract(cfg,st,customer['slot'],'pause',
                                                                  contract_id=customer['id'])['ok']
                                events.append(dict(tick=st['tick'],action='pause_buyer',slot=customer['slot']))
                        order=view(cfg,st)['contracts']['offers'][2]
                    if order['canFulfill']:
                        assert E.fulfill_order(cfg, st, 2, order['id'])['ok']
                        events.append(dict(tick=st['tick'], action='deliver_project', project=order['projectId']))
                    elif not order.get('committed'):
                        result = E.commit_order(cfg, st, 2, order['id'], True)
                        if result['ok']:
                            events.append(dict(tick=st['tick'], action='save_project', project=order['projectId']))
                        else:
                            errors.append(dict(tick=st['tick'], action='save_project', reason=result['why']))
                            if policy == 'other_orders_recover':
                                held = next((i for i in (0, 1) if st['offers'][i].get('committed')), None)
                                if held is not None:
                                    assert E.commit_order(cfg, st, held, st['offers'][held]['id'], False)['ok']
                                    events.append(dict(tick=st['tick'], action='release_other', slot=held))
            # Replay a save between decisions to exercise persistent grant use.
            st = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
            if st[P.STATE_KEY]['completed'] >= P.TOTAL:
                break
        if tick == total_ticks:
            break
        E.player_tick(cfg, cls, st, st['tick'])
        for target in set(st['tierOf']) - opened:
            events.append(dict(tick=st['tick'], action='opened', building=cfg['tiers'][target]['id']))
        opened.update(st['tierOf'])
    final = view(cfg, st)
    return dict(seed=seed, policy=policy, decisionSeconds=decision_ticks * cfg['global']['tick'],
                completed=final['townProjects']['status'] == 'complete',
                minutes=st['tick'] * cfg['global']['tick'] / 60,
                projectCount=final['townProjects']['completed'], cash=st['cash'], materials=st['materials'],
                upgrades=sum(e['action'] == 'upgrade' for e in events),
                shipments=st['customerContracts']['deliveries'], events=events, errors=errors,
                guide=final.get('nextStep'))


@pytest.mark.parametrize('policy', ['baseline', 'upgrades', 'buyers_upgrades'])
def test_opening_finishes_with_normal_tick_production_and_discretionary_spending(policy):
    result = run_opening(seed=7, policy=policy)
    assert result['completed'] and result['projectCount'] == 3
    assert result['minutes'] <= 20
    assert len([e for e in result['events'] if e['action'] == 'deliver_project']) == 3
    assert not result['errors']
    if 'upgrades' in policy:
        assert result['upgrades'] > 0


def test_prioritizing_regular_buyers_delays_projects_but_pausing_frees_their_goods():
    keeping=run_opening(seed=7,policy='buyers')
    pausing=run_opening(seed=7,policy='buyers_pause')
    assert keeping['completed'] and pausing['completed']
    # Regulars now take stock before projects. Keeping them active remains
    # viable, while deliberately pausing them restores the faster opening.
    assert pausing['minutes']<keeping['minutes']<=25
    assert pausing['minutes']<=20
    assert keeping['shipments']>pausing['shipments']
    assert any(event['action']=='pause_buyer' for event in pausing['events'])
    assert not keeping['errors'] and not pausing['errors']


def test_all_cash_can_go_to_an_upgrade_while_fish_construction_stays_fully_funded():
    cfg = legacy_config()
    st = E.new_state(cfg, seed=4)
    order = st['offers'][2]
    st['inventory']['farm_tomatoes'] = 6
    assert E.fulfill_order(cfg, st, 2, order['id'])['ok']
    st['cash'] = E.upgrade_cost(cfg, st, 0, 'production')
    st['materials'] = 19
    assert E.buy_upgrade(cfg, st, 0, 'production')['ok'] and st['cash'] == 0
    target = tier(cfg, 'fish_stall')
    quote = E.expansion_quote(cfg, st, target)
    assert quote['cost'] == quote['materialsUsed'] == quote['materialsMissing'] == 0
    assert quote['constructionGrant'] and quote['fundedValue'] > 0
    before = st['cash'], st['materials'], st['book']
    assert E.expand(cfg, st, target, st['tick'])['ok']
    assert (st['cash'], st['materials']) == before[:2]
    assert st['book'] == before[2] + quote['fundedValue']
    assert not E.expand(cfg, st, target, st['tick'])['ok']
    saved = E.migrate_state(cfg, E.State(json.loads(json.dumps(st))))
    assert P.construction_grant(cfg, saved, target) is None


def test_failed_queue_guard_does_not_consume_a_construction_grant():
    cfg = legacy_config()
    st = E.new_state(cfg, seed=3)
    st['inventory']['farm_tomatoes'] = 6
    assert E.fulfill_order(cfg, st, 2, st['offers'][2]['id'])['ok']
    target = tier(cfg, 'fish_stall')
    st['build'] = dict(i=tier(cfg, 'garage'), t=99)
    st['queue'] = [tier(cfg, 'workshop')]
    assert not E.expand(cfg, st, target, st['tick'])['ok']
    assert P.construction_grant(cfg, st, target)


def test_cash_purchase_supersedes_old_project_card_and_releases_only_its_hold():
    cfg = legacy_config()
    st = E.new_state(cfg, seed=9)
    first = st['offers'][2]['id']
    assert E.commit_order(cfg, st, 2, first, True)['ok']
    unrelated = copy.deepcopy(st['offers'][:2])
    st['cash'] = 1000
    target = tier(cfg, 'fish_stall')
    assert E.expand(cfg, st, target, st['tick'])['ok']
    state = view(cfg, st)
    assert state['contracts']['offers'][2]['id'] != first
    assert state['townProjects']['completed'] == 1
    assert not st['offers'][2]['committed']
    assert st['offers'][:2] == unrelated
    assert not E.fulfill_order(cfg, st, 2, first)['ok']
    assert P.construction_grant(cfg, st, target) is None


def test_overlapping_random_orders_can_be_released_to_make_room_for_project():
    cfg = legacy_config()
    st = E.new_state(cfg, seed=0)
    # These are the real maximum quantities of the two ordinary starter jobs.
    for i, quantity in enumerate((15, 40)):
        st['offers'][i] = dict(id='old-stock-' + str(i), name='Saved produce job',
                               requirements=[dict(goodId='farm_tomatoes', quantity=quantity)],
                               reward=50, materials=0, customer=None, committed=True)
    project_id = st['offers'][2]['id']
    assert not E.commit_order(cfg, st, 2, project_id, True)['ok']
    blocked = view(cfg, st)
    assert not blocked['contracts']['offers'][2]['canCommit']
    assert 'Release' in blocked['contracts']['offers'][2]['commitWhy']
    assert blocked['nextStep']['title'] == 'Make room for your town project'
    assert E.commit_order(cfg, st, 1, st['offers'][1]['id'], False)['ok']
    assert E.commit_order(cfg, st, 2, project_id, True)['ok']
    shared = view(cfg, st)
    assert shared['contracts']['offers'][2]['supplyConflicts'] == ['Saved produce job']
    assert 'shares saved supplies' in shared['nextStep']['title']
    for _ in range(24):
        E.player_tick(cfg, E.new_class(cfg), st, st['tick'])
        if view(cfg, st)['contracts']['offers'][2]['canFulfill']:
            break
    assert E.fulfill_order(cfg, st, 2, project_id)['ok']


@pytest.fixture
def api_town(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'project-race.db')
    monkeypatch.setattr(A, 'economy', E)
    monkeypatch.setattr(A, '_startup_config', legacy_config())
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    monkeypatch.setattr(A.time, 'time', lambda: 2_000_000_000.0)
    A._book_cache.clear()
    A.init_db()
    session = A.create_session({})
    # create_session snapshots the currently installed rules directly. Model
    # an existing class by restoring its original rules before its first join.
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',
                     (json.dumps(legacy_config()), session['code']))
    seat = A.join(dict(code=session['code'], name='PROJECT TEST',
                       pin=str(secrets.randbelow(10000)).zfill(4)))
    try:
        yield seat['token']
    finally:
        A._book_cache.clear()


def edit_api(token, fn):
    with A.connect() as conn:
        player = A._player_by_token(conn, token)
        session = A._session_of(conn, player['code'])
        cfg = A.econ_config(session)
        st = A._load_state(player, cfg, session)
        fn(cfg, st)
        E._sync_pools(cfg, st)
        A._save_state(conn, player['id'], cfg, st)
    A._book_cache.clear()


def test_concurrent_project_delivery_and_grant_redemption_each_succeed_once(api_town):
    token = api_town
    edit_api(token, lambda cfg, st: st['inventory'].update(farm_tomatoes=6))
    initial = A.econ_state({'token': [token]})
    order = initial['contracts']['offers'][2]
    def deliver(_):
        try:
            return A.econ_fulfill_order(dict(token=token, offerIndex=2, orderId=order['id']))
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deliver, range(2)))
    assert sum(result is not None for result in results) == 1
    paid = A.econ_state({'token': [token]})
    assert paid['cash'] == initial['cash'] + order['reward']
    assert paid['townProjects']['completed'] == 1
    def no_cash(cfg, st):
        st['cash'], st['materials'] = 0, 17
    edit_api(token, no_cash)
    target = tier(legacy_config(), 'fish_stall')
    def expand(_):
        try:
            return A.econ_expand(dict(token=token, tier=target))
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(expand, range(2)))
    assert sum(result is not None for result in results) == 1
    after = A.econ_state({'token': [token]})
    assert after['cash'] == 0 and after['materials'] == 17
    assert after['build']['tier'] == target and after['queue'] == []


def test_old_roastery_can_supply_its_project_without_former_ingredient_business():
    cfg = legacy_config()
    st = E.new_state(cfg)
    roastery = tier(cfg, 'roastery')
    st['tierOf'] = [roastery]
    st['b'] = [E._building(roastery)]
    payload = view(cfg, st)
    project = payload['contracts']['offers'][2]
    assert not project['locked'] and not project['canFulfill']
    assert 'Greenfield Farm' not in project['why']
    assert E.commit_order(cfg, st, 2, project['id'], True)['ok']
    before = st['cash'], copy.deepcopy(st['inventory'])
    assert not E.fulfill_order(cfg, st, 2, project['id'])['ok']
    assert (st['cash'], st['inventory']) == before
    for need in project['requirements']:
        assert E.catalog(cfg)[need['goodId']]['tier']==roastery
        st['inventory'][need['goodId']]=need['quantity']
    assert E.fulfill_order(cfg, st, 2, project['id'])['ok']
