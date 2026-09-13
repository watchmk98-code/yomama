"""Business design intentions are authenticated, isolated and atomic."""
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


@pytest.mark.parametrize('path', ['/api/game/business', '/api/game/progression'])
def test_design_routes_authenticate_before_reading_intentions(town, path):
    handler = server.NewsProxyHandler.GAME_POST_ROUTES[path]
    assert hasattr(handler, '__wrapped__')
    for body in ({}, {'token': 'bogus'}, {'token': [], 'action': []}):
        with pytest.raises(A.ApiError) as exc:
            handler(body)
        assert exc.value.status == 401


def test_business_pause_persists_and_does_not_change_another_seat(town):
    now, _, players = town
    token, other = [p['token'] for p in players]
    first = state(token)
    identity = first['buildings'][0]['buildingId']
    paused = A.econ_business(dict(token=token, action='pause', buildingId=identity))
    assert paused['buildings'][0]['paused']
    A._book_cache.clear()
    now[0] += 60
    after = state(token)
    assert after['cash'] == paused['cash']
    assert after['buildings'][0]['paused']
    assert not state(other)['buildings'][0]['paused']
    resumed = A.econ_business(dict(token=token, action='resume', buildingId=identity))
    assert not resumed['buildings'][0]['paused']


def test_malformed_business_and_stale_slot_actions_do_not_spend(town):
    _, _, players = town
    token = players[0]['token']
    edit(token, lambda cfg, st: st.update(cash=10000))
    before = state(token)
    identity = before['buildings'][0]['buildingId']
    for intention in ({'action': []}, {'action': 'hire', 'staffId': []},
                      {'action': 'pause', 'buildingId': []},
                      {'action': 'salvage', 'buildingId': 'removed-instance'}):
        with pytest.raises(A.ApiError):
            A.econ_business(dict({'token': token, 'buildingId': identity}, **intention))
    with pytest.raises(A.ApiError) as exc:
        A.econ_upgrade(dict(token=token, slot=0, kind='production', buildingId='removed-instance'))
    assert exc.value.status == 409
    after = state(token)
    assert after['cash'] == before['cash']
    assert after['buildings'][0]['lv'] == before['buildings'][0]['lv']


def test_quest_rewards_are_atomic_persistent_and_isolated(town):
    now, teacher, players = town
    class_rules(teacher, lambda cfg: cfg['businessDesign'].update(researchEnabled=True))
    token, other = [p['token'] for p in players]

    def action(name, **kw):
        return A.econ_progression(dict(token=token, action=name, questId='farm-plan', **kw))

    before = state(token)['progression']['knowHow']
    action('quest_plan', choice='regulars')
    now[0] += 600  # Real completed production and walk-in sales qualify the quest.
    A._book_cache.clear()
    assert next(q for q in state(token)['progression']['quests'] if q['id'] == 'farm-plan')['ready']

    def finish(_):
        try:
            return action('quest_finish')
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, range(2)))
    assert sum(r is not None for r in results) == 1
    A._book_cache.clear()
    assert state(token)['progression']['knowHow'] == before + 1
    assert state(other)['progression']['knowHow'] == before
    with pytest.raises(A.ApiError):
        action('quest_reset')
    assert state(token)['progression']['knowHow'] == before + 1


def test_simultaneous_hires_charge_for_only_one_permanent_trainer(town):
    _, _, players = town
    token = players[0]['token']
    def prepare(cfg, st):
        st['cash'] = 10000
        st['b'][0]['lv'] = 3
    edit(token, prepare)
    before = state(token)
    business = before['buildings'][0]
    before = A.econ_workforce(dict(token=token, action='focus',
                                  buildingId=business['buildingId'], nodeId='orientation'))
    quote = before['workforce']['teams'][0]['hire']

    def hire(_):
        try:
            return A.econ_workforce(dict(token=token, action='hire',
                                        buildingId=business['buildingId']))
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(hire, range(2)))
    assert sum(r is not None for r in results) == 1
    A._book_cache.clear()
    after = state(token)
    assert after['cash'] == before['cash'] - quote['cost']
    assert after['workforce']['teams'][0]['hires'] == 1
    assert after['buildings'][0]['staff'] is None


def test_closure_refund_is_atomic_and_old_identity_cannot_target_rebuild(town):
    now, _, players = town
    token = players[0]['token']

    def install(cfg, st):
        st['cash'] = 10000
        st['townProjects']['completed'] = 3
        assert E.expand(cfg, st, 1, st['tick'])['ok']
        E.finish_build(cfg, st, st['build']['t'])

    edit(token, install)
    before = state(token)
    business = next(b for b in before['buildings'] if b['id'] == 'fish_stall')
    quote = business['salvage']
    assert quote['canSalvage']

    def close(_):
        try:
            return A.econ_business(dict(token=token, action='salvage', buildingId=business['buildingId']))
        except A.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(close, range(2)))
    assert sum(r is not None for r in results) == 1
    A._book_cache.clear()
    after = state(token)
    assert len(after['buildings']) == 1
    assert after['cash'] == before['cash'] + quote['value']
    with pytest.raises(A.ApiError):
        A.econ_expand(dict(token=token, tier=1))
    now[0] += quote['cooldownSeconds']
    rebuilt = A.econ_expand(dict(token=token, tier=1))
    assert rebuilt['build']
    with pytest.raises(A.ApiError):
        A.econ_business(dict(token=token, action='pause', buildingId=business['buildingId']))


def test_new_actions_respect_teacher_pause(town):
    _, teacher, players = town
    token = players[0]['token']
    first = state(token)
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    for fn, body in ((A.econ_business, dict(action='pause', buildingId=first['buildings'][0]['buildingId'])),
                     (A.econ_progression, dict(action='quest_plan', questId='farm-plan', choice='regulars'))):
        with pytest.raises(A.ApiError):
            fn(dict(token=token, **body))


def test_existing_snapshot_without_design_flag_keeps_its_rules(town):
    _, _, players = town
    token = players[0]['token']
    import json
    with A.connect() as conn:
        player = A._player_by_token(conn, token)
        session = A._session_of(conn, player['code'])
        cfg = A.econ_config(session)
        cfg.pop('businessDesign', None)
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',
                     (json.dumps(cfg), player['code']))
    A._book_cache.clear()
    old = state(token)
    assert not old.get('progression', {}).get('enabled')
    for fn, body in ((A.econ_business, dict(action='pause', buildingId='farm')),
                     (A.econ_progression, dict(action='quest_plan', questId='farm-plan', choice='regulars'))):
        with pytest.raises(A.ApiError):
            fn(dict(token=token, **body))
