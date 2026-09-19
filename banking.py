"""Saved, integer-only classroom banking. Time is measured in economy ticks.

Savings earn on time actually deposited; interest is paid to spendable YM at
class midnight. Borrowing is simple interest, lending is a fixed seven-day
note. USD is a separate game wallet, not the Part 2 trading wallet.
"""
from __future__ import annotations

import copy
import re

DAY_SECONDS = 86400
FX = 3509  # hundredths of YM per USD
SAVINGS_BPS = 20
LOAN_BPS = 100
LENDING_BPS = 50
TERM_DAYS = 7
MAX_AMOUNT = 1_000_000_000


def day_ticks(cfg):
    return max(1, round(DAY_SECONDS / cfg['global']['tick']))


def ensure(st):
    if 'bank' not in st:
        st['bank'] = dict(version=1, savings=0, usdCents=0, creditScore=720,
                          lastTick=st.get('tick', 0), savingsAccrued=0,
                          interestEarned=0, interestPaid=0, loan=None, notes=[],
                          revision=0, serial=0, requests=[], history=[])
    return st['bank']


def record(bank, tick, kind, amount, **extra):
    bank['serial'] += 1
    bank['history'].insert(0, dict(id=bank['serial'], tick=tick, kind=kind,
                                   amount=amount, **extra))
    del bank['history'][40:]


def debt(cfg, bank):
    loan = bank['loan']
    if not loan:
        return 0
    den = day_ticks(cfg) * 10000
    return loan['principal'] + (loan['interestAccrued'] + den - 1) // den


def _repay(cfg, st, amount, tick):
    bank = ensure(st)
    loan = bank['loan']
    interest = debt(cfg, bank) - loan['principal']
    paid_interest = min(amount, interest)
    loan['interestAccrued'] = max(0, loan['interestAccrued'] - paid_interest * day_ticks(cfg) * 10000)
    loan['principal'] -= amount - paid_interest
    st['cash'] -= amount
    bank['interestPaid'] += paid_interest
    record(bank, tick, 'repay', amount)
    if loan['principal'] == 0 and loan['interestAccrued'] == 0:
        if not loan['overdue'] and tick - loan['startTick'] >= day_ticks(cfg):
            bank['creditScore'] = min(850, bank['creditScore'] + 10)
        bank['loan'] = None


def advance(cfg, st, target):
    bank = ensure(st)
    start = bank['lastTick']
    if target <= start:
        return
    day = day_ticks(cfg)
    den = day * 10000
    # An empty account can jump across arbitrarily long class histories.
    if not (bank['savings'] or bank['savingsAccrued'] or bank['loan'] or bank['notes']):
        bank['lastTick'] = target
        return
    while start < target:
        stop = min(target, (start // day + 1) * day)
        future = [n['dueTick'] for n in bank['notes'] if n['dueTick'] > start]
        loan = bank['loan']
        if loan and loan['dueTick'] > start:
            future.append(loan['dueTick'])
        if future:
            stop = min(stop, min(future))
        bank['savingsAccrued'] += bank['savings'] * SAVINGS_BPS * (stop - start)
        if loan:
            loan['interestAccrued'] += loan['principal'] * LOAN_BPS * (stop - start)
        if stop % day == 0:
            earned, bank['savingsAccrued'] = divmod(bank['savingsAccrued'], den)
            if earned:
                st['cash'] += earned
                bank['interestEarned'] += earned
                record(bank, stop, 'savings_interest', earned)
        for note in list(bank['notes']):
            if note['dueTick'] <= stop:
                st['cash'] += note['principal'] + note['interest']
                bank['interestEarned'] += note['interest']
                bank['notes'].remove(note)
                record(bank, stop, 'lending_matured', note['principal'] + note['interest'])
        if loan and loan['dueTick'] <= stop:
            owed = debt(cfg, bank)
            if st['cash'] >= owed:
                _repay(cfg, st, owed, stop)
            elif not loan['overdue']:
                loan['overdue'] = True
                bank['creditScore'] = max(300, bank['creditScore'] - 50)
                record(bank, stop, 'loan_overdue', owed)
        start = stop
    bank['lastTick'] = target


def stored_value(st, cfg=None):
    bank = st.get('bank')
    if not bank:
        return 0
    # Day length is stored on borrowing so callers of net_worth(st) also deduct
    # accrued interest without importing the economy (which would be circular).
    loan = bank['loan']
    liability = 0
    if loan:
        den = loan['dayTicks'] * 10000
        liability = loan['principal'] + (loan['interestAccrued'] + den - 1) // den
    return (bank['savings'] + bank['usdCents'] * FX // 10000
            + sum(n['principal'] for n in bank['notes']) - liability)


def borrow_limit(st):
    # Exclude borrowed principal from the collateral base, even after exchange,
    # depositing, or lending. Inventory/book value comes from the economy.
    import production_economy
    equity = max(0, production_economy.net_worth(st))
    score = ensure(st)['creditScore']
    # 720 earns a 38% line, 850 earns 50%. The starter allowance can fund a
    # fish stall, but cannot skip the early town straight to the roastery.
    return min(MAX_AMOUNT, max(150, equity * max(0, score - 300) // 1100))


def act(cfg, st, body):
    bank = ensure(st)
    request_id = body.get('requestId')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_id):
        return dict(ok=False, why='A valid transaction ID is required.')
    fields = {key: body.get(key) for key in ('action', 'amount', 'revision')}
    for saved in bank['requests']:
        if saved['id'] == request_id:
            if saved['fields'] != fields:
                return dict(ok=False, why='Transaction ID already used for different instructions.')
            return dict(copy.deepcopy(saved['receipt']), replayed=True)
    if type(body.get('revision')) is not int or body['revision'] != bank['revision']:
        return dict(ok=False, why='Your account changed. Refresh before making another transaction.')
    amount = body.get('amount')
    if type(amount) is not int or not 0 < amount <= MAX_AMOUNT:
        return dict(ok=False, why='Enter a positive whole YM amount (USD uses cents), up to 1 billion.')
    action = body.get('action')
    tick = st['tick']
    day = day_ticks(cfg)
    receipt = dict(ok=True, kind='bank', action=action, amount=amount)
    if action in ('deposit', 'lend', 'buy_usd') and amount > st['cash']:
        return dict(ok=False, why='Not enough spendable YM.')
    if action == 'deposit':
        bank['savings'] += amount
        st['cash'] -= amount
    elif action == 'withdraw':
        if amount > bank['savings']:
            return dict(ok=False, why='Not enough deposited YM.')
        bank['savings'] -= amount
        st['cash'] += amount
    elif action == 'buy_usd':
        cents = amount * 10000 // FX
        if cents < 1:
            return dict(ok=False, why='Amount is too small to exchange.')
        st['cash'] -= amount
        bank['usdCents'] += cents
        receipt['received'] = cents
    elif action == 'sell_usd':
        if amount > bank['usdCents']:
            return dict(ok=False, why='Not enough USD.')
        ym = amount * FX // 10000
        if ym < 1:
            return dict(ok=False, why='Exchange enough USD to receive at least 1 YM.')
        bank['usdCents'] -= amount
        st['cash'] += ym
        receipt['received'] = ym
    elif action == 'borrow':
        if bank['loan']:
            return dict(ok=False, why='Repay your current loan before borrowing again.')
        if not 100 <= amount <= borrow_limit(st):
            return dict(ok=False, why='Borrow between 100 YM and your displayed borrowing limit.')
        bank['loan'] = dict(principal=amount, originalPrincipal=amount, interestAccrued=0,
                            startTick=tick, dueTick=tick + TERM_DAYS * day,
                            dayTicks=day, overdue=False)
        st['cash'] += amount
    elif action in ('repay', 'repay_all'):
        if not bank['loan']:
            return dict(ok=False, why='You have no loan to repay.')
        if action == 'repay_all':
            amount = debt(cfg, bank)
            receipt['amount'] = amount
        if amount > debt(cfg, bank) or amount > st['cash']:
            return dict(ok=False, why='Repayment exceeds your debt or spendable YM.')
        _repay(cfg, st, amount, tick)
    elif action == 'lend':
        if amount < 100 or len(bank['notes']) >= 5:
            return dict(ok=False, why='Lend at least 100 YM. At most five bank notes can be active.')
        interest = amount * LENDING_BPS * TERM_DAYS // 10000
        bank['notes'].append(dict(id=request_id, principal=amount, interest=interest,
                                  startTick=tick, dueTick=tick + TERM_DAYS * day))
        st['cash'] -= amount
        receipt['interest'] = interest
    else:
        return dict(ok=False, why='Unknown bank action.')
    if action not in ('repay', 'repay_all'):
        record(bank, tick, action, amount, received=receipt.get('received'))
    bank['revision'] += 1
    bank['requests'].append(dict(id=request_id, fields=fields, receipt=copy.deepcopy(receipt)))
    del bank['requests'][:-64]
    return receipt


def payload(cfg, st):
    bank = ensure(st)
    tick = st['tick']
    day = day_ticks(cfg)
    loan = copy.deepcopy(bank['loan'])
    if loan:
        loan.update(balance=debt(cfg, bank), secondsRemaining=max(0, loan['dueTick'] - tick) * cfg['global']['tick'])
    notes = [dict(n, secondsRemaining=max(0, n['dueTick'] - tick) * cfg['global']['tick']) for n in bank['notes']]
    return dict(revision=bank['revision'], savings=bank['savings'], usdCents=bank['usdCents'],
                creditScore=bank['creditScore'], debt=debt(cfg, bank), borrowLimit=borrow_limit(st),
                loan=loan, notes=notes, interestEarned=bank['interestEarned'], interestPaid=bank['interestPaid'],
                history=copy.deepcopy(bank['history']), nextInterestSeconds=(day - tick % day) * cfg['global']['tick'],
                savingsAccrued=bank['savingsAccrued'] // (day * 10000),
                rules=dict(ymPerUsdHundredths=FX, savingsBps=SAVINGS_BPS, loanBps=LOAN_BPS,
                           lendingBps=LENDING_BPS, termDays=TERM_DAYS, maxNotes=5))
