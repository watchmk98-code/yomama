"""Only authenticated classmates appear in competition standings."""

import pytest

import economy as legacy
import game_api as A
import production_economy as production


@pytest.fixture(params=[production, legacy], ids=['production', 'legacy'])
def classroom(tmp_path, monkeypatch, request):
    model = request.param
    monkeypatch.setattr(A, 'DB_PATH', tmp_path / 'classroom.db')
    monkeypatch.setattr(A, 'economy', model)
    monkeypatch.setattr(A, '_startup_config', model.load_config())
    monkeypatch.setattr(A, 'AUTO_LOGIN', False)
    monkeypatch.setattr(A.time, 'time', lambda: 2_000_000_000.0)
    A._book_cache.clear()
    A.init_db()
    yield
    A._book_cache.clear()


def join_class(teacher, name):
    return A.join(dict(code=teacher['code'], name=name, pin='1234'))


def give_cash(player, cash):
    with A.connect() as conn:
        row = A._player_by_token(conn, player['token'])
        session = A._session_of(conn, row['code'])
        cfg = A.econ_config(session)
        state = A._load_state(row, cfg, session)
        state['cash'] = cash
        A._save_state(conn, row['id'], cfg, state)


def test_competition_ranks_only_real_players_from_the_same_class(classroom):
    teacher = A.create_session({})
    alice = join_class(teacher, 'Alice')
    bob = join_class(teacher, 'Bob')
    outsider = join_class(A.create_session({}), 'Other Class')
    give_cash(alice, 1000)
    give_cash(bob, 3000)
    give_cash(outsider, 10000)

    query = dict(token=alice['token'])
    for payload in (A.get_state(query), A.econ_state(query), A.econ_login(query)):
        board = payload['leaderboard']
        assert [(row['name'], row['rank'], row['you']) for row in board] == [
            ('BOB', 1, False),
            ('ALICE', 2, True),
        ]
        assert board[0]['net_worth'] - board[1]['net_worth'] == 2000
        if 'session' in payload:
            assert payload['session']['classCompetition'] is True
            assert payload['econ']['classCompetition'] is True
        else:
            assert payload['classCompetition'] is True


def test_solo_preview_never_returns_standings(classroom, monkeypatch):
    monkeypatch.setattr(A, 'AUTO_LOGIN', True)
    login = A.econ_login({})
    assert login['classCompetition'] is False
    assert login['leaderboard'] == []
    query = dict(token=login['token'])
    state = A.get_state(query)
    assert state['session']['classCompetition'] is False
    assert state['econ']['classCompetition'] is False
    assert state['leaderboard'] == []
    for payload in (A.econ_state(query), A.econ_login(query)):
        assert payload['classCompetition'] is False
        assert payload['leaderboard'] == []


def test_first_classmate_has_no_placeholder_opponents(classroom):
    player = join_class(A.create_session(dict(class_size=1)), 'First Student')
    payload = A.econ_state(dict(token=player['token']))
    assert payload['classCompetition'] is True
    [only] = payload['leaderboard']
    assert {k: only[k] for k in ('name', 'net_worth', 'you', 'rank')} == dict(
        name='FIRST STUDENT', net_worth=payload['netWorth'], you=True, rank=1)   # plus the gain fields


def test_class_standings_still_require_an_active_authenticated_seat(classroom):
    teacher = A.create_session({})
    player = join_class(teacher, 'Alice')
    for endpoint in (A.get_state, A.econ_state, A.econ_login):
        with pytest.raises(A.ApiError) as error:
            endpoint(dict(code=teacher['code'], classCompetition=True))
        assert error.value.status == 401

    with A.connect() as conn:
        conn.execute('UPDATE sessions SET active=0 WHERE code=?', (teacher['code'],))
    for endpoint in (A.get_state, A.econ_state, A.econ_login):
        with pytest.raises(A.ApiError) as error:
            endpoint(dict(token=player['token']))
        assert error.value.status == 403
