"""Bank money conservation, class-clock settlement and atomic API receipts."""
import copy
import json
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest

import banking as bank
import game_api as api
import production_economy as economy


def town():
    cfg = economy.load_config()
    st = economy.new_state(cfg, seed=71)
    st['cash'] = 100000
    return cfg, st


def intent(st, action, amount):
    rev = bank.ensure(st)['revision']
    return dict(action=action, amount=amount, revision=rev, requestId='bank-test-{}'.format(rev))


def act(cfg, st, action, amount):
    out = bank.act(cfg, st, intent(st, action, amount))
    assert out['ok'], out
    return out


def advance(cfg, st, tick):
    bank.advance(cfg, st, tick)
    st['tick'] = tick


def test_deposits_and_withdrawals_conserve_net_worth():
    cfg, st = town()
    worth = economy.net_worth(st)
    act(cfg, st, 'deposit', 45000)
    assert st['cash'] == 55000 and st['bank']['savings'] == 45000
    assert economy.net_worth(st) == worth
    act(cfg, st, 'withdraw', 45000)
    assert st['cash'] == 100000 and economy.net_worth(st) == worth


def test_savings_pay_time_weighted_interest_only_at_midnight():
    cfg, st = town()
    day = bank.day_ticks(cfg)
    advance(cfg, st, day // 2)
    act(cfg, st, 'deposit', 10000)
    advance(cfg, st, day - 1)
    assert st['cash'] == 90000
    advance(cfg, st, day)
    assert st['cash'] == 90010
    act(cfg, st, 'withdraw', 10000)
    advance(cfg, st, day * 3)
    assert st['cash'] == 100010


def test_fractional_interest_survives_reload_and_poll_frequency():
    cfg, st = town()
    act(cfg, st, 'deposit', 100)
    batch = copy.deepcopy(st)
    day = bank.day_ticks(cfg)
    for tick in range(1, day * 5 + 1):
        advance(cfg, st, tick)
    advance(cfg, batch, day * 5)
    assert st['bank'] == batch['bank']
    assert st['cash'] == batch['cash'] == 99901
    loaded = economy.migrate_state(cfg, json.loads(json.dumps(st)))
    advance(cfg, loaded, day * 10)
    assert loaded['cash'] == 99902


def test_exchange_both_directions_rounds_against_arbitrage():
    cfg, st = town()
    worth = economy.net_worth(st)
    result = act(cfg, st, 'buy_usd', 1000)
    assert result['received'] == 2849
    assert st['bank']['usdCents'] == 2849
    assert economy.net_worth(st) <= worth
    act(cfg, st, 'sell_usd', 2849)
    assert st['bank']['usdCents'] == 0 and st['cash'] == 99999
    before = copy.deepcopy(st)
    assert not bank.act(cfg, st, intent(st, 'sell_usd', 1))['ok']
    assert st == before


def test_borrow_creates_liability_and_simple_interest_early_repayment():
    cfg, st = town()
    worth = economy.net_worth(st)
    act(cfg, st, 'borrow', 1000)
    assert economy.net_worth(st) == worth
    advance(cfg, st, bank.day_ticks(cfg) * 2)
    assert bank.debt(cfg, st['bank']) == 1020
    assert economy.net_worth(st) == worth - 20
    act(cfg, st, 'repay', 520)
    assert st['bank']['loan']['principal'] == 500
    advance(cfg, st, bank.day_ticks(cfg) * 3)
    assert bank.debt(cfg, st['bank']) == 505
    act(cfg, st, 'repay', 505)
    assert st['bank']['loan'] is None and st['bank']['creditScore'] == 730
    assert st['bank']['interestPaid'] == 25


def test_immediate_loan_repayment_does_not_farm_credit():
    cfg, st = town()
    act(cfg, st, 'borrow', 1000)
    act(cfg, st, 'repay', 1000)
    assert st['bank']['creditScore'] == 720


def test_full_repayment_uses_current_interest_not_stale_browser_quote():
    cfg, st = town()
    act(cfg, st, 'borrow', 1000)
    request = intent(st, 'repay_all', 1000)
    advance(cfg, st, bank.day_ticks(cfg))
    result = bank.act(cfg, st, request)
    assert result['ok'] and result['amount'] == 1010
    assert st['bank']['loan'] is None
    assert bank.act(cfg, st, request)['replayed']


def test_credit_limit_scales_without_skipping_start_or_counting_borrowed_money():
    cfg, st = town()
    st['cash'] = 0
    assert bank.borrow_limit(st) == 150
    assert bank.borrow_limit(st) >= cfg['tiers'][1]['baseCost']
    assert bank.borrow_limit(st) < cfg['tiers'][2]['baseCost']
    st['cash'] = 10_000_000
    limit = bank.borrow_limit(st)
    assert limit > 1_000_000
    act(cfg, st, 'borrow', 100000)
    assert bank.borrow_limit(st) == limit
    act(cfg, st, 'deposit', 100000)
    assert bank.borrow_limit(st) == limit
    st['bank']['creditScore'] = 850
    assert bank.borrow_limit(st) > limit


def test_low_credit_can_recover_after_old_debt_is_paid():
    cfg, st = town()
    st['bank']['creditScore'] = 300
    assert bank.borrow_limit(st) == 150
    act(cfg, st, 'borrow', 100)
    advance(cfg, st, bank.day_ticks(cfg))
    act(cfg, st, 'repay_all', 101)
    assert st['bank']['creditScore'] == 310


def test_maturity_auto_repayment_and_overdue_only_penalizes_once():
    cfg, st = town()
    act(cfg, st, 'borrow', 1000)
    good = copy.deepcopy(st)
    advance(cfg, good, bank.day_ticks(cfg) * 7)
    assert good['bank']['loan'] is None and good['cash'] == 99930
    st['cash'] = 0
    advance(cfg, st, bank.day_ticks(cfg) * 7)
    assert st['bank']['loan']['overdue'] and st['bank']['creditScore'] == 670
    advance(cfg, st, bank.day_ticks(cfg) * 10)
    assert bank.debt(cfg, st['bank']) == 1100 and st['bank']['creditScore'] == 670
    st['cash'] = 2000
    advance(cfg, st, bank.day_ticks(cfg) * 11)
    assert st['cash'] == 890 and st['bank']['loan'] is None


def test_lending_locks_principal_until_maturity_and_pays_once():
    cfg, st = town()
    worth = economy.net_worth(st)
    act(cfg, st, 'lend', 1000)
    assert st['cash'] == 99000 and economy.net_worth(st) == worth
    advance(cfg, st, bank.day_ticks(cfg) * 7 - 1)
    assert st['cash'] == 99000
    advance(cfg, st, bank.day_ticks(cfg) * 7)
    assert st['cash'] == 100035 and not st['bank']['notes']
    advance(cfg, st, bank.day_ticks(cfg) * 8)
    assert st['cash'] == 100035


@pytest.mark.parametrize('amount', [True, False, 0, -1, 1.5, '100', None, float('nan'), float('inf'), 10**15])
def test_invalid_amount_never_changes_balances(amount):
    cfg, st = town()
    before = copy.deepcopy(st)
    assert not bank.act(cfg, st, intent(st, 'deposit', amount))['ok']
    assert st == before


def test_retries_stale_revision_and_id_collision():
    cfg, st = town()
    request = intent(st, 'deposit', 1000)
    assert bank.act(cfg, st, request)['ok']
    assert bank.act(cfg, st, request)['replayed']
    assert st['bank']['savings'] == 1000
    assert not bank.act(cfg, st, dict(request, amount=2000))['ok']
    assert not bank.act(cfg, st, dict(request, requestId='different-id'))['ok']


def test_existing_saves_migrate_without_retroactive_interest():
    cfg, st = town()
    st.pop('bank')
    st['tick'] = bank.day_ticks(cfg) * 50
    migrated = economy.migrate_state(cfg, st)
    assert migrated['bank']['lastTick'] == st['tick']
    assert migrated['bank']['savings'] == 0
    act(cfg, migrated, 'deposit', 10000)
    advance(cfg, migrated, st['tick'] + 1)
    assert migrated['bank']['interestEarned'] == 0


def test_banking_continues_after_production_offline_allowance():
    cfg, st = town()
    act(cfg, st, 'lend', 1000)
    world = economy.new_class(cfg, bank.day_ticks(cfg) * 8)
    economy.advance_class(cfg, world, [st], 0, bank.day_ticks(cfg) * 8)
    assert not st['bank']['notes'] and st['bank']['interestEarned'] == 35


@pytest.fixture
def seat(tmp_path, monkeypatch):
    monkeypatch.setattr(api, 'DB_PATH', tmp_path / 'bank-test.db')
    api._settled.clear()
    api.init_db()
    teacher = api.create_session({})
    joined = api.join(dict(code=teacher['code'], name='BANK TEST', pin=str(secrets.randbelow(10000)).zfill(4)))
    with api.connect() as conn:
        p = api._player_by_token(conn, joined['token'])
        s = api._session_of(conn, p['code'])
        cfg = api.econ_config(s)
        st = api._load_state(p, cfg, s)
        st['cash'] = 100000
        api._save_state(conn, p['id'], cfg, st)
    yield joined, teacher
    api._settled.clear()


def test_api_atomic_duplicate_requests_persistence_and_player_isolation(seat):
    joined, teacher = seat
    request = dict(token=joined['token'], action='deposit', amount=1000, revision=0, requestId='concurrent-request')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(api.bank_action, [request, request]))
    assert all(r['bank']['savings'] == 1000 for r in results)
    assert sum(bool(r['receipt'].get('replayed')) for r in results) == 1
    saved = api.econ_state(dict(token=joined['token']))
    assert saved['bank']['savings'] == 1000
    other = api.join(dict(code=teacher['code'], name='OTHER PLAYER', pin=str(secrets.randbelow(10000)).zfill(4)))
    assert api.econ_state(dict(token=other['token']))['bank']['savings'] == 0


def test_api_pause_auth_and_reset(seat):
    joined, teacher = seat
    with pytest.raises(api.ApiError):
        api.bank_action(dict(token='invalid'))
    request = dict(token=joined['token'], action='deposit', amount=1000, revision=0, requestId='paused-request')
    api.teacher(dict(teacher_token=teacher['teacher_token'], action='pause'))
    with pytest.raises(api.ApiError):
        api.bank_action(request)
    api.teacher(dict(teacher_token=teacher['teacher_token'], action='resume'))
    assert api.bank_action(request)['bank']['savings'] == 1000
    api.reset_class(teacher['code'])
    assert api.econ_state(dict(token=joined['token']))['bank']['savings'] == 0
