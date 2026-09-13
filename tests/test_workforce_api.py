"""Permanent recruitment shares the authenticated, atomic class transaction."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import game_api as A
import production_economy as E
import server
from test_production_api import town, state, edit  # noqa: F401


def class_rules(teacher, change):
    """Re-stamp the class rules: these contracts cover a mechanic the shipped
    testing rules switch off (research) or pin (worker head count)."""
    with A.connect() as conn:
        s = A._session_of(conn, teacher['code'])
        cfg = A.econ_config(s)
        change(cfg)
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?', (json.dumps(cfg), teacher['code']))
    A._book_cache.clear()


def saved_economy(token):
    with A.connect() as conn:
        player = A._player_by_token(conn, token)
        st = json.loads(player['econ'])
    return {key: copy.deepcopy(st.get(key)) for key in
            ('cash', 'inventory', 'workforce', 'workerPopulation', 'businessProgression')}


def ready_business(token):
    def prepare(cfg, st):
        st['cash'] = 100000
        st['b'][0]['lv'] = 3
    edit(token, prepare)
    identity = state(token)['buildings'][0]['buildingId']
    A.econ_workforce(dict(token=token, action='focus',
                         buildingId=identity, nodeId='orientation'))
    return identity


def test_workforce_route_authenticates_before_reading_intentions(town):
    handler = server.NewsProxyHandler.GAME_POST_ROUTES['/api/game/workforce']
    assert hasattr(handler, '__wrapped__'), 'Workforce must use the class lock.'
    for body in ({}, {'token': 'bogus'}, {'token': [], 'action': []}):
        with pytest.raises(A.ApiError) as exc:
            handler(body)
        assert exc.value.status == 401


def test_simultaneous_permanent_hires_charge_once_and_survive_reload(town):
    _, _, players = town
    token, other = [player['token'] for player in players]
    identity = ready_business(token)
    quoted_cost = state(token)['workforce']['teams'][0]['hire']['cost']
    before = saved_economy(token)
    other_before = saved_economy(other)

    def hire(_):
        try:
            return A.econ_workforce(dict(token=token, action='hire',
                                        buildingId=identity))
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(hire, range(2)))
    successes = [result for result in results if result is not None]
    assert len(successes) == 1
    after = saved_economy(token)
    assert after['cash'] == before['cash'] - quoted_cost
    team = after['workforce']['teams']['farm']
    assert team['hires'] == team['trainers'] == 1
    assert team['workers'] == 0
    assert after['workerPopulation'] == before['workerPopulation']
    assert after['workforce'] != before['workforce']
    A._book_cache.clear()
    state(token)
    assert saved_economy(token) == after
    assert saved_economy(other) == other_before
    assert hire(0) is None, 'A reload must not clear the recruitment cooldown.'
    assert saved_economy(token) == after


def test_malformed_and_stale_workforce_intentions_are_atomic(town):
    _, _, players = town
    token = players[0]['token']
    identity = ready_business(token)
    before = saved_economy(token)
    malformed = (
        {'action': []},
        {'action': 'focus', 'nodeId': []},
        {'action': 'focus', 'nodeId': 'free_money'},
        {'action': 'allocate', 'allocation': []},
        {'action': 'allocate', 'allocation': {'production': True, 'sales': 0, 'efficiency': 0}},
        {'action': 'allocate', 'allocation': {'production': -1, 'sales': 0, 'efficiency': 0}},
        {'action': 'allocate', 'allocation': {'production': .5, 'sales': 0, 'efficiency': 0}},
        {'action': 'allocate', 'allocation': {'production': 999999, 'sales': 0, 'efficiency': 0}},
        {'action': 'allocate', 'allocation': {'unknown': 1}},
        {'action': 'allocate', 'allocation': {'production': 0, 'sales': 0, 'efficiency': 0},
         'trainingBranch': []},
        {'action': 'hire', 'buildingId': []},
        {'action': 'hire', 'buildingId': 'removed-instance'},
        {'action': 'hq_assign', 'enabled': 'false'},
    )
    for intention in malformed:
        body = dict(token=token, buildingId=identity)
        body.update(intention)
        with pytest.raises(A.ApiError):
            A.econ_workforce(body)
        assert saved_economy(token) == before, intention
    with pytest.raises(A.ApiError) as exc:
        A.econ_workforce(dict(token=token, action='hire', slot=0,
                             buildingId='removed-instance'))
    assert exc.value.status == 409
    assert saved_economy(token) == before


def test_class_pause_blocks_recruitment_focus_allocation_and_hq(town):
    now, teacher, players = town
    token = players[0]['token']
    identity = ready_business(token)
    A.econ_workforce(dict(token=token, action='hire', buildingId=identity))
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    before = saved_economy(token)
    now[0] += 3600
    for intention in (
            dict(action='hire'), dict(action='focus', nodeId='sales'),
            dict(action='allocate', allocation={'production': 0, 'sales': 0, 'efficiency': 0}),
            dict(action='hq_upgrade'), dict(action='hq_assign', enabled=True)):
        with pytest.raises(A.ApiError):
            A.econ_workforce(dict(token=token, buildingId=identity, **intention))
    A._book_cache.clear()
    state(token)
    assert saved_economy(token) == before


def test_new_rules_reject_temporary_staff_hiring(town):
    _, _, players = town
    token = players[0]['token']
    identity = ready_business(token)
    before = saved_economy(token)
    with pytest.raises(A.ApiError):
        A.econ_business(dict(token=token, action='hire',
                             buildingId=identity, staffId='assistant'))
    assert saved_economy(token) == before


def test_worker_population_and_hq_support_persist_in_the_correct_seat(town):
    now, teacher, players = town
    class_rules(teacher, lambda cfg: cfg['workforce'].pop('populationFixedTotal', None))
    token, other = [player['token'] for player in players]
    identity = ready_business(token)
    edit(token, lambda cfg, st: st['businessProgression'].update(prestige=1, prestigeEarned=1))
    A.econ_workforce(dict(token=token, action='hire', buildingId=identity))
    A.econ_workforce(dict(token=token, action='focus', buildingId=identity, nodeId='sales'))

    def expand(cfg, st):
        st['tierOf'].extend([1, 2])
        st['b'].extend([E._building(1), E._building(2)])
    edit(token, expand)
    now[0] += 300
    before = state(token)
    assert before['workforce']['teams'][0]['workers'] == 0
    assert before['workforce']['population']['total'] == 17
    allocation = dict(production=0, sales=1, efficiency=0)
    with pytest.raises(A.ApiError):
        A.econ_workforce(dict(token=token, action='allocate', buildingId=identity,
                             allocation=allocation, trainingBranch='sales'))
    before_hq = state(token)
    upgraded = A.econ_workforce(dict(token=token, action='hq_upgrade'))
    assert upgraded['cash'] == before_hq['cash'] - before_hq['workforce']['hq']['upgrade']['cost']
    A.econ_workforce(dict(token=token, action='hq_assign', buildingId=identity, enabled=True))
    A._book_cache.clear()
    after = state(token)['workforce']
    assert after['teams'][0]['allocation'] == dict(production=0, sales=0, efficiency=0)
    assert after['population']['total'] == 17
    assert after['population']['purposeEnabled'] is False
    assert after['hq']['level'] == 1
    assert after['hq']['targets'] == ['farm']
    assert after['teams'][0]['hqSupported']
    untouched = state(other)['workforce']
    assert untouched['hq']['level'] == 0
    assert untouched['hq']['targets'] == []
    assert untouched['population']['total'] == 5
    assert all(team['hires'] == team['workers'] == 0 for team in untouched['teams'])


def test_population_rejects_all_assignments_without_mutation(town):
    _, teacher, players = town
    class_rules(teacher, lambda cfg: cfg['workforce'].pop('populationFixedTotal', None))
    token, other = [player['token'] for player in players]
    ready_business(token)

    def expand(cfg, st):
        st['tierOf'].append(1)
        st['b'].append(E._building(1))
    edit(token, expand)
    payload = state(token)
    assert payload['workforce']['population']['total'] == 12
    identities = [row['buildingId'] for row in payload['workforce']['teams']]
    before = saved_economy(token)
    other_before = saved_economy(other)

    def assign(identity):
        try:
            return A.econ_workforce(dict(token=token, action='allocate',
                buildingId=identity, allocation=dict(production=8, sales=0, efficiency=0)))
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(assign, identities))
    assert results == [None, None]
    A._book_cache.clear()
    assert state(token)['workforce']['population']['total'] == 12
    assert saved_economy(token) == before
    assert saved_economy(other) == other_before


def test_existing_snapshot_without_workforce_keeps_its_rules(town):
    _, _, players = town
    token = players[0]['token']
    identity = state(token)['buildings'][0]['buildingId']
    with A.connect() as conn:
        player = A._player_by_token(conn, token)
        session = A._session_of(conn, player['code'])
        cfg = A.econ_config(session)
        cfg.pop('workforce', None)
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',
                     (json.dumps(cfg), player['code']))
    A._book_cache.clear()
    before = state(token)
    assert not before.get('workforce', {}).get('enabled')
    snapshot = saved_economy(token)
    for action in ('hire', 'focus', 'allocate', 'hq_upgrade', 'hq_assign'):
        with pytest.raises(A.ApiError):
            A.econ_workforce(dict(token=token, action=action, buildingId=identity,
                                 nodeId='orientation', allocation={}, enabled=True))
        assert saved_economy(token) == snapshot
