"""Cash receipts and a small regular-customer capacity estimate.

The receipt window contains payments that actually happened, never a forecast
or reconstructed lifetime counters. Operating receipts mean walk-ins and
regular buyers; one-time orders, clearance and event cash stay separate.

Receipt ticks are completion ticks: production tick k records at k + 1, while
an explicit action records at the state's current tick. All amounts are whole
YM. Bundle revenue belongs to the businesses producing the delivered goods,
weighted by those goods' retail values. Upstream inputs are not credited again.
"""
from __future__ import annotations

import math


WINDOW_SECONDS = 60
SOURCES = ('walkIns', 'regularBuyers', 'orders', 'clearance', 'events')
OPERATING_SOURCES = ('walkIns', 'regularBuyers')
STATE_KEY = 'recentEarnings'
TOWN_KEY = 'town'


def ensure(st):
    """Give old saves an empty history, without inventing historical payments."""
    data = st.get(STATE_KEY)
    if not isinstance(data, dict) or data.get('version') != 1:
        data = dict(version=1, startedTick=int(st.get('tick', 0)), buckets=[])
        st[STATE_KEY] = data
    return data


def prune(cfg, st, tick=None, clear=False):
    """Retain (now - 60 seconds, now]; clear when offline production is skipped."""
    now = int(st.get('tick', 0) if tick is None else tick)
    data = ensure(st)
    if clear:
        data.update(startedTick=now, buckets=[])
    else:
        seconds = cfg['global']['tick']
        data['buckets'][:] = [b for b in data['buckets']
                              if 0 <= (now - b['tick']) * seconds < WINDOW_SECONDS]
    return data


def _slot(st, value):
    if type(value) is int:
        slot = value
    elif isinstance(value, str) and value.isdigit() and str(int(value)) == value:
        slot = int(value)
    else:
        raise ValueError('Building attribution needs a valid slot')
    if not 0 <= slot < len(st['b']):
        raise ValueError('Building attribution needs an owned business')
    return str(slot)


def _whole_amount(amount):
    if type(amount) is not int or amount < 0:
        raise ValueError('Cash receipts must be nonnegative whole YM')


def _split(amount, weights):
    """Largest-remainder allocation conserves every YM, with stable slot ties."""
    _whole_amount(amount)
    if not weights:
        if amount:
            raise ValueError('A payment needs a contributing business')
        return {}
    total = sum(weights.values())
    shares = {slot: amount * weight // total for slot, weight in weights.items()}
    remainder = amount - sum(shares.values())
    priority = sorted(weights, key=lambda slot: (-(amount * weights[slot] % total), int(slot)))
    for slot in priority[:remainder]:
        shares[slot] += 1
    return {slot: value for slot, value in shares.items() if value}


def allocate_payment(cfg, st, amount, requirements):
    """Attribute one bundle's cash to its direct producers, exactly once."""
    goods = {g['id']: (ti, g['unitPrice'])
             for ti, tier in enumerate(cfg['tiers']) for g in tier['goods']}
    slots = {ti: str(slot) for slot, ti in enumerate(st['tierOf'])}
    weights = {}
    for need in requirements:
        quantity = need['quantity']
        if type(quantity) is not int or quantity <= 0:
            raise ValueError('Shipment quantities must be positive whole units')
        ti, price = goods[need['goodId']]
        if ti not in slots:
            raise ValueError('A shipment needs an owned producer')
        slot = slots[ti]
        weights[slot] = weights.get(slot, 0) + price * quantity
    return _split(amount, weights)


def record(cfg, st, source, amount, tick=None, by_building=None):
    """Record an already-paid receipt; this function never changes cash/stock.

    ``by_building`` maps owned slots to exact whole-YM shares. Operating income
    must name its producers. Unattributed event or other one-off cash is shown
    explicitly as town income, so shop totals plus that row always reconcile.
    Multiple calls in the same tick are aggregated, keeping saved data bounded.
    """
    if source not in SOURCES:
        raise ValueError('Unknown receipt source')
    _whole_amount(amount)
    now = st.get('tick', 0) if tick is None else tick
    if type(now) is not int or now < 0:
        raise ValueError('Receipt tick must be a nonnegative integer')
    if by_building is None:
        if source in OPERATING_SOURCES and amount:
            raise ValueError('Operating receipts need a contributing business')
        shares = {TOWN_KEY: amount} if amount else {}
    else:
        shares = {}
        for key, value in by_building.items():
            _whole_amount(value)
            slot = _slot(st, key)
            shares[slot] = shares.get(slot, 0) + value
        if sum(shares.values()) != amount:
            raise ValueError('Building receipts must sum to the cash payment')
    data = prune(cfg, st, now)
    if not amount:
        return
    bucket = next((b for b in data['buckets'] if b['tick'] == now), None)
    if bucket is None:
        bucket = dict(tick=now, sources={})
        data['buckets'].append(bucket)
        data['buckets'].sort(key=lambda b: b['tick'])
    payments = bucket['sources'].setdefault(source, {})
    for slot, value in shares.items():
        if value:
            payments[slot] = payments.get(slot, 0) + value


def record_goods(cfg, st, source, amount, requirements, tick=None):
    """Record a delivered bundle after the authoritative payment succeeds."""
    shares = allocate_payment(cfg, st, amount, requirements)
    record(cfg, st, source, amount, tick=tick, by_building=shares)


def _summary(totals):
    by_source = {source: totals.get(source, 0) for source in SOURCES}
    operating = sum(by_source[source] for source in OPERATING_SOURCES)
    total = sum(by_source.values())
    return dict(operatingIncome=operating, oneOffIncome=total - operating,
                totalIncome=total, bySource=by_source)


def payload(cfg, st, tick=None):
    """Actual cash earned in the last 60 seconds, not a promised per-minute rate."""
    now = int(st.get('tick', 0) if tick is None else tick)
    data = prune(cfg, st, now)
    per_shop = {str(slot): {} for slot in range(len(st['b']))}
    unattributed = {}
    totals = {}
    for bucket in data['buckets']:
        for source, payments in bucket['sources'].items():
            for slot, amount in payments.items():
                shop = per_shop[slot] if slot in per_shop else unattributed
                shop[source] = shop.get(source, 0) + amount
                totals[source] = totals.get(source, 0) + amount
    return dict(_summary(totals), windowSeconds=WINDOW_SECONDS,
                observedSeconds=min(WINDOW_SECONDS, max(0, now - data['startedTick']) * cfg['global']['tick']),
                byBuilding={slot: _summary(values) for slot, values in per_shop.items()},
                unattributed=_summary(unattributed),
                attribution='Delivered goods, shared by retail value')


def allocate_regular_flow(cfg, st, pool):
    """Allocate an available goods/minute pool to whole regular shipments.

    The caller first deducts recipe inputs from production. Customers claim
    the remaining pool in actual slot priority; their scarcest required good
    limits the entire bundle. Remaining goods may then serve walk-in demand.

    This is a steady-flow estimate: current stock, finite manual commitments,
    shelf limits and discrete completion timing are intentionally excluded.
    It neither changes the input pool nor issues income. Even an undersupplied
    regular can ship late; no missed-payment backlog is assumed.
    """
    remaining = {gid: max(0.0, float(rate)) for gid, rate in pool.items()}
    if any(not math.isfinite(rate) for rate in remaining.values()):
        raise ValueError('Production rates must be finite')
    consumed = {gid: 0.0 for gid in remaining}
    by_building = {str(slot): 0.0 for slot in range(len(st['b']))}
    customers = []
    total_income = 0.0
    for contract in sorted(st.get('customerContracts', {}).get('active', []), key=lambda c: c['slot']):
        if contract['paused']:
            continue
        seconds = contract['intervalTicks'] * cfg['global']['tick']
        requested = 60.0 / max(1, seconds)
        needs = {}
        for need in contract['requirements']:
            gid, quantity = need['goodId'], need['quantity']
            if type(quantity) is not int or quantity <= 0:
                raise ValueError('Shipment quantities must be positive whole units')
            needs[gid] = needs.get(gid, 0) + quantity
        frequency = min([requested] + [remaining.get(gid, 0.0) / qty for gid, qty in needs.items()]) if needs else 0.0
        for gid, quantity in needs.items():
            used = quantity * frequency
            remaining[gid] = max(0.0, remaining.get(gid, 0.0) - used)
            consumed[gid] = consumed.get(gid, 0.0) + used
        income = contract['reward'] * frequency
        shares = allocate_payment(cfg, st, contract['reward'], contract['requirements'])
        for slot, amount in shares.items():
            by_building[slot] += amount * frequency
        total_income += income
        customers.append(dict(id=contract['id'], slot=contract['slot'],
                              deliveriesPerMinute=frequency, incomePerMinute=income,
                              expectedIntervalSeconds=60.0 / frequency if frequency > 0 else None,
                              requestedIntervalSeconds=seconds,
                              supplyLimited=frequency < requested - 1e-9))
    return dict(remaining=remaining, unitsPerMinute=consumed, incomePerMinute=total_income,
                byBuilding=by_building, customers=customers)
