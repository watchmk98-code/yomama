"""Actual completed production and operating sales over the last 60 seconds.

Completion ticks and offline clearing match the cash receipt window. Recipe
inputs are consumption, not sales; manual orders and clearance are one-off
actions and do not contribute to operating sales. Each completed output and
delivered good belongs only to the business that directly produces it.
"""
from __future__ import annotations


WINDOW_SECONDS = 60
STATE_KEY = 'recentBusinessActivity'
SOURCES = ('production', 'walkIns', 'regularBuyers')


def ensure(st):
    """Old saves start observing now; never reconstruct unrecorded activity."""
    data = st.get(STATE_KEY)
    if not isinstance(data, dict) or data.get('version') != 1:
        data = dict(version=1, startedTick=int(st.get('tick', 0)), buckets=[])
        st[STATE_KEY] = data
    return data


def prune(cfg, st, tick=None, clear=False):
    """Retain (now - 60 seconds, now], aggregating all events in each tick."""
    now = int(st.get('tick', 0) if tick is None else tick)
    data = ensure(st)
    if clear:
        data.update(startedTick=now, buckets=[])
    else:
        seconds = cfg['global']['tick']
        data['buckets'][:] = [bucket for bucket in data['buckets']
                              if 0 <= (now - bucket['tick']) * seconds < WINDOW_SECONDS]
    return data


def record(cfg, st, source, by_building, tick=None):
    """Observe an already-completed event without changing stock or money."""
    if source not in SOURCES:
        raise ValueError('Unknown business activity source')
    now = st.get('tick', 0) if tick is None else tick
    if type(now) is not int or now < 0:
        raise ValueError('Activity tick must be a nonnegative integer')
    quantities = {}
    for key, quantity in by_building.items():
        if type(key) is int:
            slot = key
        elif isinstance(key, str) and key.isdigit() and str(int(key)) == key:
            slot = int(key)
        else:
            raise ValueError('Activity needs a valid business slot')
        if not 0 <= slot < len(st['b']):
            raise ValueError('Activity needs an owned business')
        if type(quantity) is not int or quantity < 0:
            raise ValueError('Activity quantities must be nonnegative whole units')
        if quantity:
            quantities[str(slot)] = quantities.get(str(slot), 0) + quantity
    data = prune(cfg, st, now)
    if not quantities:
        return
    bucket = next((bucket for bucket in data['buckets'] if bucket['tick'] == now), None)
    if bucket is None:
        bucket = dict(tick=now, sources={})
        data['buckets'].append(bucket)
        data['buckets'].sort(key=lambda bucket: bucket['tick'])
    units = bucket['sources'].setdefault(source, {})
    for slot, quantity in quantities.items():
        units[slot] = units.get(slot, 0) + quantity


def record_regular_shipment(cfg, st, requirements, tick=None):
    """Attribute shipment units to direct producers without counting inputs."""
    producers = {good['id']: tier for tier, row in enumerate(cfg['tiers']) for good in row['goods']}
    slots = {tier: slot for slot, tier in enumerate(st['tierOf'])}
    by_building = {}
    for need in requirements:
        quantity = need['quantity']
        if type(quantity) is not int or quantity <= 0:
            raise ValueError('Shipment quantities must be positive whole units')
        tier = producers[need['goodId']]
        if tier not in slots:
            raise ValueError('A shipment needs an owned producer')
        slot = slots[tier]
        by_building[slot] = by_building.get(slot, 0) + quantity
    record(cfg, st, 'regularBuyers', by_building, tick=tick)


def payload(cfg, st, tick=None):
    """Return whole units actually completed/sold, never an extrapolated rate."""
    now = int(st.get('tick', 0) if tick is None else tick)
    data = prune(cfg, st, now)
    observed = min(WINDOW_SECONDS, max(0, now - data['startedTick']) * cfg['global']['tick'])
    buildings = {str(slot): dict(windowSeconds=WINDOW_SECONDS, observedSeconds=observed,
                                producedUnits=0, soldUnits=0,
                                soldBySource=dict(walkIns=0, regularBuyers=0))
                 for slot in range(len(st['b']))}
    for bucket in data['buckets']:
        for source, quantities in bucket['sources'].items():
            for slot, quantity in quantities.items():
                if slot not in buildings:
                    continue
                shop = buildings[slot]
                if source == 'production':
                    shop['producedUnits'] += quantity
                else:
                    shop['soldUnits'] += quantity
                    shop['soldBySource'][source] += quantity
    return dict(windowSeconds=WINDOW_SECONDS, observedSeconds=observed, byBuilding=buildings)
