"""Reporting-only weighted-average production cost; never changes cash or stock.

Old stock has no historical cost record. Seed it at its current production cost
and mark the estimate. New batches carry their actual whole-YM production charge.
Costs leave this ledger before the caller removes the corresponding goods.
"""
from __future__ import annotations

import business_operations as operations

SCALE = 1_000_000
KEY = 'inventoryCosts'


def ensure(cfg, st):
    if not operations.enabled(cfg):
        return {}
    data = st.setdefault(KEY, dict(version=1, startedTick=st.get('tick', 0), goods={}, openingEstimates={}))
    return data


def _pool(cfg, st, gid):
    data = ensure(cfg, st)
    quantity = st.get('inventory', {}).get(gid, 0)
    pool = data['goods'].setdefault(gid, dict(quantity=0, costMicros=0, estimated=False))
    if quantity < pool['quantity']:
        # Crafting/other non-sale consumption removes its own share, never shop cost.
        pool['costMicros'] = pool['costMicros'] * quantity // pool['quantity']
        pool['quantity'] = quantity
    if quantity > pool['quantity']:
        extra = quantity - pool['quantity']
        unit_cost = 0
        for b in st.get('b', []):
            good = next((g for g in cfg['tiers'][b['tier']]['goods'] if g['id'] == gid), None)
            if good:
                unit_cost = operations.effective_batch_cost(cfg, b, good, st) / good['quantity']
                break
        estimate = round(unit_cost * extra * SCALE)
        pool['costMicros'] += estimate
        pool['quantity'] = quantity
        pool['estimated'] = True
        data['openingEstimates'].setdefault(gid, dict(quantity=extra, costMicros=estimate,
                                                     tick=st.get('tick', 0)))
    if not quantity:
        pool.update(costMicros=0, estimated=False)
    return pool


def migrate(cfg, st):
    if not operations.enabled(cfg):
        return
    ensure(cfg, st)
    for gid in st.get('inventory', {}):
        _pool(cfg, st, gid)


def produce(cfg, st, gid, quantity, cost):
    """Called after the successful cash charge, before adding physical output."""
    if not operations.enabled(cfg):
        return
    pool = _pool(cfg, st, gid)
    pool['quantity'] += quantity
    pool['costMicros'] += cost * SCALE


def consume(cfg, st, requirements):
    """Return costs per persistent business identity, before physical stock debit."""
    if not operations.enabled(cfg):
        return {}
    counts = {}
    for need in requirements:
        gid, quantity = need['goodId'], need['quantity']
        if type(quantity) is not int or quantity < 0:
            raise ValueError('Costed quantity must be a nonnegative integer')
        counts[gid] = counts.get(gid, 0) + quantity
    if any(quantity > st.get('inventory', {}).get(gid, 0) for gid, quantity in counts.items()):
        raise ValueError('Cannot cost more goods than are in stock')
    operations.ensure(cfg, st)
    owners = {g['id']: b['buildingId'] for b in st['b'] for g in cfg['tiers'][b['tier']]['goods']}
    result = {}
    for gid, quantity in counts.items():
        if not quantity:
            continue
        pool = _pool(cfg, st, gid)
        cost = pool['costMicros'] * quantity // pool['quantity']
        row = result.setdefault(owners.get(gid, 'town'), dict(costMicros=0, estimated=False))
        row['costMicros'] += cost
        row['estimated'] = row['estimated'] or pool['estimated']
        pool['quantity'] -= quantity
        pool['costMicros'] -= cost
        if not pool['quantity']:
            pool['estimated'] = False
    return result
