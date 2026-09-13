"""A read-only poll that finds the class clock where the last pass left it
loads and saves the requesting town alone (game_api._fast_poll). These
contracts pin that the shortcut is invisible: the same requests in the same
order leave the same rows and answers with it on and off; a zero-tick poll
rewrites nobody else's town while a tick still moves every town; and each
case the shortcut must not take - a new day, undealt offers, a new or reset
seat, re-stamped rules, a rolled-back pass, a legacy class - falls through
to the full pass."""
import json
import sqlite3

import pytest

import economy as legacy
import game_api as A
import production_economy as E

TICK = E.load_config()['global']['tick']
SEQUENCE = ('ALICE', 'BOB', 'tick', 'ALICE', 'act', 'CARA', 'tick', 'tick', 'BOB')


@pytest.fixture
def klass(tmp_path, monkeypatch):
    """Three seats under the current rules, a few ticks in, time frozen, as a
    freshly started server sees it (no pass of this process on record)."""
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'class.db')
    monkeypatch.setattr(A, 'economy', E)
    monkeypatch.setattr(A, '_startup_config', E.load_config())
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    monkeypatch.setattr(A, 'FAST_POLL', True)
    now = [2_000_000_000.0]
    monkeypatch.setattr(A.time, 'time', lambda: now[0])
    A._book_cache.clear()
    A.init_db()
    teacher = A.create_session({})
    tokens = {n: A.join(dict(code=teacher['code'], name=n, pin='1234'))['token']
              for n in ('ALICE', 'BOB', 'CARA')}
    for _ in range(3):
        now[0] += TICK
        poll(tokens['ALICE'])
    A._settled.clear()
    return now, teacher, tokens


def poll(token):
    return A.econ_state({'token': [token]})


def rows():
    """Everything a pass writes: every town, the class clock, the openings."""
    with A.connect() as conn:
        players = {r['name']: (r['econ'], r['econ_meta'], r['econ_nw'])
                   for r in conn.execute('SELECT name, econ, econ_meta, econ_nw FROM players')}
        s = conn.execute('SELECT pressure, income_per_hour, econ_tick FROM sessions').fetchone()
        standings = sorted(tuple(r) for r in conn.execute('SELECT player_id, day, net_worth FROM standings'))
    return dict(players=players, pressure=s['pressure'], income=s['income_per_hour'],
                econ_tick=s['econ_tick'], standings=standings)


def passes(monkeypatch):
    """Counts full class passes: only they call the engine's advance_class."""
    calls = []
    real = E.advance_class

    def counted(*args, **kw):
        calls.append(1)
        return real(*args, **kw)
    monkeypatch.setattr(E, 'advance_class', counted)
    return calls


def traced(monkeypatch):
    """Every SQL statement the API runs from now on."""
    statements = []
    real = A.connect

    def connect():
        conn = real()
        conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(A, 'connect', connect)
    return statements


def copy_db(src, dst):
    with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
        a.backup(b)


def edit(token, change):
    """A row written outside any pass, the way other test files do it."""
    with A.connect() as conn:
        p = A._player_by_token(conn, token)
        s = A._session_of(conn, p['code'])
        cfg = A.econ_config(s)
        st = A._load_state(p, cfg, s)
        change(st)
        A._save_state(conn, p['id'], cfg, st)


def test_the_same_requests_leave_the_same_rows_and_answers_with_the_shortcut_off(klass, tmp_path, monkeypatch):
    now, teacher, tokens = klass
    start = now[0]
    base = tmp_path / 'base.db'
    copy_db(A.DB_PATH, base)

    def run(fast):
        path = tmp_path / ('fast.db' if fast else 'full.db')
        copy_db(base, path)
        monkeypatch.setattr(A, 'DB_PATH', path)
        monkeypatch.setattr(A, 'FAST_POLL', fast)
        A._book_cache.clear()
        A._settled.clear()
        now[0] = start
        trail = []
        for step in SEQUENCE:
            answer = None
            if step == 'tick':
                now[0] += TICK
            elif step == 'act':
                answer = A.econ_reserve(dict(token=tokens['ALICE'], slot=0, reserve=True))
            else:
                answer = poll(tokens[step])
            trail.append((step, answer, rows()))
        return trail

    calls = passes(monkeypatch)
    fast = run(True)
    shortcut_passes = len(calls)
    full = run(False)
    # off: every poll and the action replay the class; on: only the ones after a tick or an action do
    assert (shortcut_passes, len(calls) - shortcut_passes) == (5, 6)
    for (step, answer, saved), (_, expected_answer, expected) in zip(fast, full):
        assert answer == expected_answer, step
        assert saved == expected, step


def test_a_zero_tick_poll_rewrites_only_its_own_town_and_a_tick_moves_every_town(klass, monkeypatch):
    now, teacher, tokens = klass
    calls = passes(monkeypatch)
    statements = traced(monkeypatch)
    poll(tokens['ALICE'])                                  # the first request replays and settles the class
    assert calls == [1]
    before = rows()
    statements.clear()
    poll(tokens['BOB'])
    assert calls == [1]
    updates = [s for s in statements if s.startswith('UPDATE ')]
    assert len(updates) == 1 and updates[0].startswith('UPDATE players')
    after = rows()
    assert after['players']['ALICE'] == before['players']['ALICE']
    assert after['players']['CARA'] == before['players']['CARA']
    assert {k: v for k, v in after.items() if k != 'players'} == {k: v for k, v in before.items() if k != 'players'}
    was, is_ = (json.loads(before['players']['BOB'][0]), json.loads(after['players']['BOB'][0]))
    assert {k for k in was if was[k] != is_[k]} == {'lastActiveTick'} and is_['lastActiveTick'] == after['econ_tick']
    assert before['players']['BOB'][1:] == after['players']['BOB'][1:]

    now[0] += TICK                                         # one tick later everyone is replayed, whoever asks
    statements.clear()
    poll(tokens['CARA'])
    assert calls == [1, 1]
    assert sum(s.startswith('UPDATE players') for s in statements) == 4    # three towns, CARA's activity stamp again
    moved = rows()
    assert moved['econ_tick'] == before['econ_tick'] + 1
    assert all(json.loads(meta)['tick'] == moved['econ_tick'] for _, meta, _ in moved['players'].values())
    assert all(moved['players'][n] != after['players'][n] for n in ('ALICE', 'BOB', 'CARA'))


def test_ticker_and_dashboard_answers_match_the_full_pass_with_teacher_events(klass, monkeypatch):
    now, teacher, tokens = klass
    family = next(iter(E.load_config()['families']))
    event = dict(rumourTick=1, startTick=1, family=family, mag=1.3, real=True, holdTicks=400, headline='Bread boom')
    with A.connect() as conn:                              # a class migrated from v3 can still carry these
        conn.execute('UPDATE sessions SET custom_events=? WHERE code=?', (json.dumps([event]), teacher['code']))
    calls = passes(monkeypatch)
    query = {'token': [tokens['ALICE']]}
    monkeypatch.setattr(A, 'FAST_POLL', False)
    ticker, dashboard = A.econ_ticker(query), A.get_state(query)
    monkeypatch.setattr(A, 'FAST_POLL', True)
    assert (A.econ_ticker(query), A.get_state(query)) == (ticker, dashboard)
    assert calls == [1, 1]
    assert [line['headline'] for line in ticker['lines'] if line['kind'] == 'event'] == ['Bread boom']


def test_a_new_day_opens_every_seat_before_the_shortcut_resumes(klass, monkeypatch):
    now, teacher, tokens = klass
    calls = passes(monkeypatch)
    poll(tokens['ALICE'])
    A.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))    # the class clock stops: zero ticks from here
    poll(tokens['BOB'])
    assert calls == [1]
    tomorrow = int(now[0] // 86400) + 1
    now[0] += 86400

    def openings():
        with A.connect() as conn:
            return sorted((r['name'], r['net_worth'] == r['econ_nw']) for r in conn.execute(
                'SELECT p.name, s.net_worth, p.econ_nw FROM standings s JOIN players p ON p.id=s.player_id'
                ' WHERE s.day=?', (tomorrow,)))
    assert openings() == []
    poll(tokens['ALICE'])
    assert calls == [1, 1]
    assert openings() == [('ALICE', True), ('BOB', True), ('CARA', True)]
    board = poll(tokens['BOB'])['leaderboard']
    assert calls == [1, 1] and all(r['gain']['daily'] == 0 for r in board)
    with A.connect() as conn:                              # one seat's missing opening alone is enough
        conn.execute('DELETE FROM standings WHERE day=? AND player_id=(SELECT id FROM players WHERE name=?)',
                     (tomorrow, 'CARA'))
    poll(tokens['ALICE'])
    assert calls == [1, 1, 1]
    assert openings() == [('ALICE', True), ('BOB', True), ('CARA', True)]
    with pytest.raises(A.ApiError):                        # paused: actions are refused before any replay
        A.econ_reserve(dict(token=tokens['ALICE'], slot=0, reserve=True))
    assert calls == [1, 1, 1]


def test_a_seat_without_dealt_offers_takes_the_full_pass(klass, monkeypatch):
    now, teacher, tokens = klass
    calls = passes(monkeypatch)
    poll(tokens['ALICE'])
    assert calls == [1]

    def undeal(st):
        st['offers'] = None
    edit(tokens['BOB'], undeal)
    dealt = poll(tokens['BOB'])
    assert calls == [1, 1] and len(dealt['contracts']['offers']) == 3
    poll(tokens['BOB'])
    assert calls == [1, 1]


def test_a_refused_action_rolls_its_pass_back_and_the_next_poll_replays(klass, monkeypatch):
    now, teacher, tokens = klass
    calls = passes(monkeypatch)
    poll(tokens['ALICE'])
    assert calls == [1] and teacher['code'] in A._settled
    with pytest.raises(A.ApiError):                        # refused after the pass: the transaction rolls back
        A.econ_upgrade(dict(token=tokens['ALICE'], slot=9, kind='production'))
    assert calls == [1, 1] and teacher['code'] not in A._settled
    before = rows()
    poll(tokens['ALICE'])
    assert calls == [1, 1, 1]
    assert rows() == before                                # the rolled-back pass had nothing to change
    poll(tokens['ALICE'])
    assert calls == [1, 1, 1]


def test_actions_logins_new_seats_reset_seats_and_new_rules_take_the_full_pass(klass, monkeypatch):
    now, teacher, tokens = klass
    calls = passes(monkeypatch)
    poll(tokens['ALICE'])
    poll(tokens['BOB'])
    assert calls == [1]
    A.econ_reserve(dict(token=tokens['ALICE'], slot=0, reserve=True))
    poll(tokens['BOB'])                                    # ALICE's town changed since the last pass
    assert calls == [1, 1, 1]
    A.econ_login({'token': [tokens['CARA']]})
    poll(tokens['BOB'])
    assert calls == [1, 1, 1, 1, 1]
    poll(tokens['BOB'])
    assert calls == [1, 1, 1, 1, 1]

    A.join(dict(code=teacher['code'], name='DANA', pin='1234'))
    board = poll(tokens['ALICE'])['leaderboard']
    assert len(calls) == 6 and next(r for r in board if r['name'] == 'DANA')['gain'] == dict(daily=0, weekly=0, monthly=0)
    with A.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM standings s JOIN players p ON p.id=s.player_id'
                            ' WHERE p.name=?', ('DANA',)).fetchone()[0] == 1
    poll(tokens['ALICE'])
    assert len(calls) == 6

    A.teacher(dict(teacher_token=teacher['teacher_token'], action='reset_player', name='BOB'))
    poll(tokens['ALICE'])
    assert len(calls) == 7
    poll(tokens['ALICE'])
    assert len(calls) == 7

    with A.connect() as conn:                              # re-stamped rules, as the teacher console's tests do
        s = A._session_of(conn, teacher['code'])
        cfg = A.econ_config(s)
        cfg['runtime']['tickerLimit'] = 3
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?', (json.dumps(cfg), teacher['code']))
    A._book_cache.clear()
    poll(tokens['ALICE'])
    assert len(calls) == 8
    poll(tokens['ALICE'])
    assert len(calls) == 8


def test_unstamped_rules_are_stamped_by_a_full_pass_first(klass, monkeypatch):
    now, teacher, tokens = klass
    calls = passes(monkeypatch)
    poll(tokens['ALICE'])
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?', (json.dumps({'global': {'seed': 7}}), teacher['code']))
    poll(tokens['ALICE'])
    assert calls == [1, 1]
    with A.connect() as conn:
        stamped = json.loads(conn.execute('SELECT econ_config FROM sessions WHERE code=?', (teacher['code'],)).fetchone()[0])
    assert stamped['version'] == 4 and 'fun' in stamped
    poll(tokens['ALICE'])
    assert calls == [1, 1]


def test_a_legacy_class_never_takes_the_shortcut(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'legacy.db')
    monkeypatch.setattr(A, 'economy', legacy)
    monkeypatch.setattr(A, '_startup_config', legacy.load_config())
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    monkeypatch.setattr(A, 'FAST_POLL', True)
    monkeypatch.setattr(A.time, 'time', lambda: 2_000_000_000.0)
    A._book_cache.clear()
    A.init_db()
    calls = []
    real = legacy.advance_class
    monkeypatch.setattr(legacy, 'advance_class', lambda *a, **k: calls.append(1) or real(*a, **k))
    teacher = A.create_session({})
    token = A.join(dict(code=teacher['code'], name='ALICE', pin='1234'))['token']
    poll(token)
    poll(token)
    assert calls == [1, 1]
