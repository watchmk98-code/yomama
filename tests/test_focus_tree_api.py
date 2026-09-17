"""Global focus decisions are authenticated, persisted, and timed by the class."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import game_api as api
import production_economy as economy
import server
from test_production_api import town, state, edit  # noqa: F401


def start(token, focus_id):
    return api.econ_focus_tree(dict(token=token, action='start', focusId=focus_id))


def saved_focus(token):
    with api.connect() as conn:
        player = api._player_by_token(conn, token)
        return json.loads(player['econ'])['focusTree']


def finish(now, token, result):
    now[0] += result['focusTree']['active']['remainingSeconds']
    api._book_cache.clear()
    return state(token)['focusTree']


def test_focus_route_authenticates_before_parsing_and_is_class_locked(town):
    handler = server.NewsProxyHandler.GAME_POST_ROUTES['/api/game/focus-tree']
    assert hasattr(handler, '__wrapped__')
    for body in ({}, {'token': 'bogus'}, {'token': [], 'action': [], 'focusId': []}):
        with pytest.raises(api.ApiError) as exc:
            handler(body)
        assert exc.value.status == 401


def test_concurrent_start_persists_only_one_timer_in_the_correct_seat(town):
    _, _, players = town
    token, other = [player['token'] for player in players]
    initial = state(token)['focusTree']
    other_before = state(other)['focusTree']
    assert initial['completed'] == []

    def attempt(_):
        try:
            return start(token, 'secure_harvest')
        except api.ApiError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    success = [result for result in results if result is not None]
    assert len(success) == 1
    assert success[0]['receipt']['focusId'] == 'secure_harvest'
    active = success[0]['focusTree']['active']
    assert active['id'] == 'secure_harvest'
    assert active['endsTick'] > active['startedTick']
    saved = saved_focus(token)
    api._book_cache.clear()
    assert state(token)['focusTree']['active'] == active
    assert saved_focus(token) == saved
    assert state(other)['focusTree'] == other_before


def test_focus_duration_uses_class_clock_and_completes_at_deadline(town):
    now, _, players = town
    token = players[0]['token']
    result = start(token, 'secure_harvest')
    remaining = result['focusTree']['active']['remainingSeconds']
    now[0] += remaining - 15
    before = state(token)['focusTree']
    assert before['active']['id'] == 'secure_harvest'
    assert before['completed'] == []
    now[0] += 15
    after = state(token)['focusTree']
    assert after['active'] is None
    assert after['completed'] == ['secure_harvest']
    assert next(node for node in after['nodes'] if node['id'] == 'reliable_supply')['canStart']
    api._book_cache.clear()
    assert state(token)['focusTree']['completed'] == ['secure_harvest']
    with pytest.raises(api.ApiError):
        start(token, 'secure_harvest')


def test_teacher_pause_freezes_timer_and_refuses_new_focus(town):
    now, teacher, players = town
    token = players[0]['token']
    start(token, 'secure_harvest')
    api.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    paused = state(token)['focusTree']
    now[0] += 2 * 86400
    assert state(token)['focusTree'] == paused
    with pytest.raises(api.ApiError) as exc:
        start(token, 'reliable_supply')
    assert exc.value.status == 409
    api.teacher(dict(teacher_token=teacher['teacher_token'], action='resume'))
    assert state(token)['focusTree']['active'] == paused['active']
    now[0] += paused['active']['remainingSeconds']
    assert state(token)['focusTree']['completed'] == ['secure_harvest']


def test_global_tree_keeps_both_routes_open_across_reload(town):
    now, _, players = town
    token = players[0]['token']

    def businesses(cfg, st):
        for name in ('roastery', 'cannery'):
            tier = next(index for index, row in enumerate(cfg['tiers']) if row['id'] == name)
            st['tierOf'].append(tier)
            st['b'].append(economy._building(tier))

    edit(token, businesses)
    for focus_id in ('secure_harvest', 'reliable_supply'):
        finish(now, token, start(token, focus_id))
    choices = {node['id']: node for node in state(token)['focusTree']['nodes']}
    assert choices['local_brand']['canStart']
    assert choices['preserve_surplus']['canStart']
    chosen = start(token, 'local_brand')['focusTree']
    assert chosen['branch'] is None
    assert next(node for node in chosen['nodes'] if node['id'] == 'preserve_surplus')['status'] == 'locked'
    with pytest.raises(api.ApiError):
        start(token, 'preserve_surplus')
    api._book_cache.clear()
    assert state(token)['focusTree']['branch'] is None
    now[0] += chosen['active']['remainingSeconds']
    assert next(node for node in state(token)['focusTree']['nodes'] if node['id'] == 'preserve_surplus')['canStart']
    assert state(players[1]['token'])['focusTree']['branch'] is None


def test_malformed_or_locked_focus_does_not_change_saved_progress(town):
    _, _, players = town
    token = players[0]['token']
    state(token)
    before = saved_focus(token)
    for intention in ({}, {'action': []}, {'action': 'start', 'focusId': []},
                      {'action': 'start', 'focusId': 'free_money'},
                      {'action': 'start', 'focusId': 'food_empire'}):
        with pytest.raises(api.ApiError):
            api.econ_focus_tree(dict(token=token, **intention))
        assert saved_focus(token) == before
