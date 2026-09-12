"""Current economic rules through real SQLite transactions; never the live save."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import game_api as A
import economy as legacy
import production_economy as E


@pytest.fixture
def town(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'town.db')
    monkeypatch.setattr(A, 'economy', E)
    monkeypatch.setattr(A, '_startup_config', E.load_config())
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    now = [2_000_000_000.0]
    monkeypatch.setattr(A.time, 'time', lambda: now[0])
    A._book_cache.clear()
    A.init_db()
    teacher = A.create_session({})
    players = [A.join(dict(code=teacher['code'], name=n, pin='1234')) for n in ('ALICE', 'BOB')]
    return now, teacher, players


def edit(token, fn):
    with A.connect() as conn:
        p = A._player_by_token(conn, token)
        s = A._session_of(conn, p['code'])
        cfg = A.econ_config(s)
        st = A._load_state(p, cfg, s)
        fn(cfg, st)
        A._save_state(conn, p['id'], cfg, st)


def state(token):
    return A.econ_state({'token': [token]})


def test_breakfast_persists_isolated_and_awards_only_once(town):
    now, _, players = town
    token = players[0]['token']
    assert state(token)['breakfastEvent']['status'] == 'new'
    def event(action, **kw):
        return A.econ_breakfast(dict(token=token, action=action, **kw))
    assert state(token)['breakfastEvent']['locked']
    with pytest.raises(A.ApiError):
        event('start')
    def open_roastery(cfg, st):
        st['tierOf'].append(2)
        st['b'].append(E._building(2))
    edit(token, open_roastery)
    assert not state(token)['breakfastEvent']['locked']
    event('start')
    event('make', recipe='coffee')
    now[0] += 30
    A._book_cache.clear()
    assert state(token)['breakfastEvent']['stock']['coffee'] == 2
    event('deliver', orderId='first')
    with pytest.raises(A.ApiError):
        event('deliver', orderId='first')
    assert state(players[1]['token'])['breakfastEvent']['status'] == 'new'
    def final(cfg, st):
        st['breakfastEvent']['stage'] = 4
        st['breakfastEvent']['stock'].update(coffee=4, pastry=4)
    edit(token, final)
    before = state(token)['materials']
    def deliver(_):
        try:
            return event('deliver', orderId='final')
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deliver, range(2)))
    assert sum(r is not None for r in results) == 1
    assert state(token)['materials'] == before + 5
    event('start')
    assert state(token)['breakfastEvent']['status'] == 'done'


def test_cold_start_customer_income_and_request_validation(town):
    now, _, players = town
    token = players[0]['token']
    first = state(token)
    assert first['modelVersion'] == 4
    now[0] += 60
    after = state(token)
    assert after['cash'] > first['cash']
    assert all(isinstance(g['quantity'], int) and g['quantity'] >= 0 for g in after['board'])
    for body in ({'slot': -1, 'kind': 'production'}, {'slot': '0', 'kind': 'sales'},
                 {'slot': True, 'kind': 'storage'}, {'slot': 0, 'kind': 'free_money'}):
        with pytest.raises(A.ApiError):
            A.econ_upgrade(dict(token=token, **body))
    with pytest.raises(A.ApiError):
        A.econ_reserve(dict(token=token, slot=0, reserve='false'))
    assert state(token)['cash'] == after['cash']


def test_upgrade_persists_and_reserve_survives_reloading(town):
    _, _, players = town
    token = players[0]['token']
    edit(token, lambda cfg, st: st.update(cash=10000))
    before = state(token)
    cost = before['buildings'][0]['upgrades']['sales']['cost']
    after = A.econ_upgrade(dict(token=token, slot=0, kind='sales'))
    assert after['cash'] == before['cash'] - cost
    assert after['buildings'][0]['upgrades']['sales']['level'] == before['buildings'][0]['upgrades']['sales']['level'] + 1
    A.econ_reserve(dict(token=token, slot=0, reserve=True))
    A._book_cache.clear()
    assert state(token)['buildings'][0]['reserve'] is True


def test_orders_reject_shortages_and_stale_double_fulfillment(town):
    _, _, players = town
    token = players[0]['token']
    before = state(token)
    offer = before['contracts']['offers'][0]
    action = dict(token=token, offerIndex=0, orderId=offer['id'])
    with pytest.raises(A.ApiError):
        A.econ_fulfill_order(action)
    assert state(token)['cash'] == before['cash']
    def supply(cfg, st):
        for req in offer['requirements']:
            st['inventory'][req['goodId']] = req['quantity']
    edit(token, supply)
    stocked = state(token)
    def fulfill(_):
        try:
            return A.econ_fulfill_order(action)
        except A.ApiError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fulfill, range(2)))
    assert sum(r is not None for r in results) == 1
    after = state(token)
    assert after['cash'] == stocked['cash'] + offer['reward']
    assert after['materials'] == stocked['materials'] + offer['materials']
    assert after['contracts']['offers'][0]['id'] != offer['id']
    with pytest.raises(A.ApiError):
        A.econ_replace_order(action)
    with pytest.raises(A.ApiError):
        A.econ_fulfill_order(dict(token=token, offerIndex=0))


def test_absent_player_cap_not_extended_by_classmates(town):
    now, _, players = town
    absent, active = [p['token'] for p in players]
    # Leave Alice alone while Bob keeps visiting for 24 hours.
    state(absent)
    for _ in range(24):
        now[0] += 3600
        state(active)
    a = state(absent)
    b = state(active)
    assert b['cash'] > a['cash'] > 0
    frozen = a['cash']
    assert state(absent)['cash'] == frozen  # no second payment for capped time
    now[0] += 60
    assert state(absent)['cash'] > frozen  # returning renews future production


def test_long_absence_repeated_requests_and_pause(town):
    now, teacher, players = town
    token = players[0]['token']
    state(token)
    now[0] += 7 * 86400
    first = state(token)
    assert not first['behind']
    assert first['tick'] == 7 * E.ticks_per_day(E.load_config())
    assert state(token)['cash'] == first['cash']
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    now[0] += 3600
    paused = state(token)
    assert paused['cash'] == first['cash'] and paused['tick'] == first['tick']
    with pytest.raises(A.ApiError):
        A.econ_reserve(dict(token=token, slot=0, reserve=True))


def test_new_join_receives_no_class_history(town):
    now, teacher, _ = town
    now[0] += 86400
    late = A.join(dict(code=teacher['code'], name='LATE', pin='1234'))
    first = state(late['token'])
    assert first['cash'] == E.new_state(E.load_config())['cash']
    assert sum(g['quantity'] for g in first['board']) == 0


def test_v3_migration_preserves_value_and_paid_builds_once(town):
    now, teacher, players = town
    token = players[0]['token']
    old_cfg = legacy.load_config()
    old = legacy.new_state(old_cfg)
    old.update(cash=1000, book=5000, pend={'0': 123}, tick=40,
               build={'i': 1, 't': 6000}, queue=[2])
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET econ_config=?, econ_tick=40 WHERE code=?',
                     (json.dumps(old_cfg), teacher['code']))
        conn.execute('UPDATE players SET econ=?, econ_meta=? WHERE token=?',
                     (json.dumps(old), '{}', token))
    now[0] += 86400
    migrated = state(token)
    assert migrated['cash'] == 1123
    assert migrated['netWorth'] == 6123
    assert migrated['buildings'][0]['id'] == 'farm'
    assert migrated['build']['tier'] == 1 and migrated['build']['remainingSec'] == (6000-5760) * 15
    assert migrated['queue'][0]['tier'] == 2
    assert sum(g['quantity'] for g in migrated['board']) == 0
    assert state(token)['cash'] == migrated['cash']
    with A.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ledger WHERE kind='v4_migration'").fetchone()[0] == 1
        audit = json.loads(conn.execute("SELECT detail FROM ledger WHERE kind='v4_migration'").fetchone()[0])
        assert audit['config'] == old_cfg


def test_current_class_config_is_snapshotted(town, monkeypatch):
    _, _, players = town
    token = players[0]['token']
    before = state(token)
    changed = copy.deepcopy(A._startup_config)
    changed['tiers'][0]['baseCost'] *= 100
    monkeypatch.setattr(A, '_startup_config', changed)
    assert state(token)['buildings'][0]['upgrades'] == before['buildings'][0]['upgrades']


def test_reset_replaces_replay_metadata_and_gate_stays_authoritative(town):
    now, teacher, players = town
    token = players[0]['token']
    now[0] += 3600
    state(token)
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='reset_player', name='ALICE'))
    fresh = state(token)
    assert fresh['cash'] == 0 and fresh['tick'] == 240
    with pytest.raises(A.ApiError):
        A.econ_keep(dict(token=token, percent=50))
    with pytest.raises(A.ApiError):
        A.trade_equity(dict(token=token, symbol='AAPL', side='buy', shares=1))
    now[0] += 60
    assert state(token)['cash'] > 0


def test_single_building_legacy_migration_and_overdue_construction(town):
    now, teacher, players = town
    token = players[0]['token']
    old = dict(cash=500, book=1000, tier=0, lv=4, auto=2, pend={'0': 30, '1': 20},
               tick=0, build={'finishTick': 40, 'from': 0}, queue=[],
               lastLogin=0, catchupUntil=-1,
               checklist=dict(lv25=False, auto=True, goodSales=0, quiz=False), keepPercent=None)
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',
                     (json.dumps({'global': {'seed': 7}}), teacher['code']))
        conn.execute('UPDATE players SET econ=?,econ_meta=? WHERE token=?', (json.dumps(old), '{}', token))
    now[0] += 3600
    after = state(token)
    assert after['cash'] == 550
    assert after['netWorth'] == 1550
    assert after['buildingsOwned'] == 2 and after['build'] is None
    assert after['buildings'][0]['upgrades']['sales']['level'] == 2
    assert after['warehouseStored'] == 0
    assert state(token)['cash'] == 550
