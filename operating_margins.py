"""Gross sale invoices and selling expenses, settled from the same proceeds.

Reference prices, production cash charges and take-home rewards stay unchanged.
The extra selling charge is a fixed product tariff, not a percentage of the
current reward. Reports remain on a cash basis: production spending is recorded
when goods are made, rather than capitalized as accounting inventory.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import math

import business_operations as operations
import earnings


STATE_KEY = 'operatingMargins'
FEE_SCALE = 1_000_000
WINDOW_SECONDS = 60
TARGETS = dict(farm=6, fish_stall=8, roastery=15, garage=12, workshop=16,
               solar_coop=20, cannery=11, machine_works=16, turbine_field=21,
               generator=18, relay_station=18, freight_terminal=12,
               data_center=22, solar_array=23, uplink_center=20)


def enabled(cfg):
    return operations.enabled(cfg) and cfg.get(STATE_KEY, {}).get('enabled', True) is True


def target_margin(cfg, building_id):
    value = cfg.get(STATE_KEY, {}).get('targets', {}).get(building_id, TARGETS.get(building_id, 15))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 100:
        raise ValueError('Operating margin targets must be percentages above zero and at most 100')
    return value


@lru_cache(maxsize=64)
def _cached_tariffs(signature):
    result = []
    for gid, price, quantity, cost, target in signature:
        reference = Decimal(str(price))
        base_cost = Decimal(str(cost)) / Decimal(str(quantity))
        fraction = Decimal(str(target)) / 100
        fee = max(Decimal(0), (reference - base_cost) / fraction - reference)
        result.append((gid, int((fee * FEE_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP))))
    return tuple(result)


def tariffs(cfg):
    """Fixed micro-YM tariffs; only stable product/config inputs enter the cache."""
    if not enabled(cfg):
        return {good['id']: 0 for tier in cfg['tiers'] for good in tier['goods']}
    signature = tuple((good['id'], good['unitPrice'], good['quantity'],
                       operations.base_batch_cost(cfg, good), target_margin(cfg, tier['id']))
                      for tier in cfg['tiers'] for good in tier['goods'])
    return dict(_cached_tariffs(signature))


def _empty_totals():
    return dict(takeHome=0, grossSales=0, sellingCosts=0)


def ensure(cfg, st):
    """Initialize an empty ledger; migration never invents old invoices."""
    if not enabled(cfg):
        return st.get(STATE_KEY, {})
    operations.ensure(cfg, st)
    data = st.setdefault(STATE_KEY, {})
    data.setdefault('version', 1)
    data.setdefault('startedTick', st.get('tick', 0))
    data.setdefault('remainders', {})
    data.setdefault('buckets', [])
    data.setdefault('totals', _empty_totals())
    data.setdefault('bySource', {})
    return data


def migrate(cfg, st):
    return ensure(cfg, st)


def prune(cfg, st, tick=None, clear=False):
    data = ensure(cfg, st)
    if not data:
        return data
    now = st.get('tick', 0) if tick is None else tick
    if clear:
        data.update(startedTick=now, buckets=[])
    else:
        data['buckets'][:] = [bucket for bucket in data['buckets']
                             if 0 <= (now - bucket['tick']) * cfg['global']['tick'] < WINDOW_SECONDS]
    owned = {b.get('buildingId') for b in st['b']}
    # A closed business cannot sell again; its replacement has a new identity.
    data['remainders'] = {key: value for key, value in data['remainders'].items() if key in owned}
    return data


def _identity(st, slot):
    return st['b'][slot].get('buildingId', 'slot:{}'.format(slot))


def _terms(cfg, requirements, terms):
    raw = tariffs(cfg) if terms is None else terms.get('feeMicrosByGood')
    if not isinstance(raw, dict):
        raise ValueError('Sale terms need per-product fees')
    selected = {}
    for need in requirements:
        gid = need['goodId']
        fee = raw.get(gid)
        if type(fee) is not int or fee < 0:
            raise ValueError('Sale terms need a nonnegative whole micro-fee for every product')
        selected[gid] = fee if enabled(cfg) else 0
    return dict(feeMicrosByGood=selected)


def quote(cfg, st, amount, requirements, source=None, terms=None):
    """Read-only invoice quote; freeze ``terms``, not a rounding remainder.

    Passing a source includes its existing fractional carry, matching pay at
    the same state. With no source, the quote starts from zero carry.
    """
    if source is not None and source not in earnings.SOURCES:
        raise ValueError('Unknown receipt source')
    shares = earnings.allocate_payment(cfg, st, amount, requirements)
    frozen = _terms(cfg, requirements, terms)
    slots = {tier: slot for slot, tier in enumerate(st['tierOf'])}
    goods = {good['id']: tier for tier, row in enumerate(cfg['tiers']) for good in row['goods']}
    fee_units = {}
    for need in requirements:
        slot = slots[goods[need['goodId']]]
        fee_units[slot] = fee_units.get(slot, 0) + frozen['feeMicrosByGood'][need['goodId']] * need['quantity']
    remainders = st.get(STATE_KEY, {}).get('remainders', {})
    by_building = {}
    next_remainders = {}
    for slot in sorted(fee_units):
        identity = _identity(st, slot)
        carry = remainders.get(identity, {}).get(source, 0) if source is not None and enabled(cfg) else 0
        fee, remainder = divmod(fee_units[slot] + carry, FEE_SCALE)
        take_home = shares.get(str(slot), 0)
        by_building[identity] = dict(slot=slot, takeHome=take_home,
                                    grossSales=take_home + fee, sellingCosts=fee)
        next_remainders[identity] = remainder
    selling = sum(row['sellingCosts'] for row in by_building.values())
    return dict(takeHome=amount, grossSales=amount + selling, sellingCosts=selling,
                byBuilding=by_building, terms=frozen, remainders=next_remainders)


def pay(cfg, st, source, amount, requirements, tick=None, terms=None):
    """Atomically credit the invoice and pay its fee; net cash stays ``amount``."""
    now = st.get('tick', 0) if tick is None else tick
    if type(now) is not int or now < 0:
        raise ValueError('Receipt tick must be a nonnegative integer')
    if source not in earnings.SOURCES:
        raise ValueError('Unknown receipt source')
    ensure(cfg, st)
    invoice = quote(cfg, st, amount, requirements, source=source, terms=terms)
    # All validation precedes the authoritative payment and net receipt.
    st['cash'] += invoice['grossSales']
    st['cash'] -= invoice['sellingCosts']
    earnings.record_goods(cfg, st, source, amount, requirements, tick=now)
    if enabled(cfg):
        data = prune(cfg, st, now)
        bucket = next((row for row in data['buckets'] if row['tick'] == now), None)
        if bucket is None:
            bucket = dict(tick=now, sources={})
            data['buckets'].append(bucket)
            data['buckets'].sort(key=lambda row: row['tick'])
        payments = bucket['sources'].setdefault(source, {})
        for identity, row in invoice['byBuilding'].items():
            data['remainders'].setdefault(identity, {})[source] = invoice['remainders'][identity]
            target = payments.setdefault(identity, _empty_totals())
            for key in target:
                target[key] += row[key]
        source_totals = data['bySource'].setdefault(source, _empty_totals())
        for key in data['totals']:
            data['totals'][key] += invoice[key]
            source_totals[key] += invoice[key]
    return invoice


def _recent_fees(cfg, st, identity=None, sources=earnings.OPERATING_SOURCES):
    data = prune(cfg, st)
    return sum(row['sellingCosts'] for bucket in data.get('buckets', [])
               for source, payments in bucket['sources'].items() if source in sources
               for key, row in payments.items() if identity is None or key == identity)


def _production_spending(cfg, st, identity=None):
    data = operations.prune(cfg, st)
    return sum(value for bucket in data.get('buckets', []) for key, value in bucket['byBuilding'].items()
               if identity is None or key == identity)


def _figures(net, production, selling):
    # Subtract original forecast inputs before rounding, just like the existing
    # profit estimate. Preserve component precision for town aggregation. Round
    # displayed totals together so sales minus costs still gives that profit.
    sales = round(net + selling, 2)
    profit = round(net - production, 2)
    costs = round(sales - profit, 2)
    return dict(sales=sales, costs=costs, profit=profit,
                margin=profit / sales * 100 if sales > 0 else None,
                takeHome=net, sellingCosts=selling, productionCosts=production)


def statement(cfg, st, slot, rates, net_income, production_cost):
    """Actual cash results plus installed forecasts; supplied amounts forecast.

    Only walk-ins and regular buyers contribute to the operating statement.
    Costs for unsold output remain cash expenses; no COGS is manufactured.
    """
    ensure(cfg, st)
    identity = _identity(st, slot)
    receipts = earnings.payload(cfg, st)['byBuilding'][str(slot)]
    result = _figures(receipts['operatingIncome'], _production_spending(cfg, st, identity),
                      _recent_fees(cfg, st, identity))
    fees = tariffs(cfg)
    goods = cfg['tiers'][st['tierOf'][slot]]['goods']
    selling = sum(rates[g['id']].get('retail', 0) * fees[g['id']] / FEE_SCALE for g in goods)
    # Accepted buyers retain their invoice tariff, including after a class's
    # target configuration changes. Only new walk-in sales use today's tariff.
    regular_flow = earnings.allocate_regular_flow(cfg, st, {gid: row.get('production', 0) for gid, row in rates.items()})
    contracts = {contract['id']: contract for contract in st.get('customerContracts', {}).get('active', [])}
    own_goods = {good['id'] for good in goods}
    for regular in regular_flow['customers']:
        contract = contracts[regular['id']]
        frozen = _terms(cfg, contract['requirements'], contract.get('sellingTerms'))['feeMicrosByGood']
        selling += sum(frozen[need['goodId']] * need['quantity'] / FEE_SCALE
                       for need in contract['requirements'] if need['goodId'] in own_goods) * regular['deliveriesPerMinute']
    potential = _figures(net_income, production_cost, selling)
    result.update({'potential' + key[0].upper() + key[1:]: value for key, value in potential.items()})
    result.update(enabled=enabled(cfg), basis='cash', buildingId=identity,
                  targetMarginPercent=target_margin(cfg, cfg['tiers'][st['tierOf'][slot]]['id']),
                  windowSeconds=WINDOW_SECONDS)
    return result


def town_statement(cfg, st, buildings=()):
    """Sum actual town cash, including removed shops; forecasts use statements."""
    data = ensure(cfg, st)
    receipts = earnings.payload(cfg, st)
    result = _figures(receipts['operatingIncome'], _production_spending(cfg, st), _recent_fees(cfg, st))
    # Accept either direct statements or building payloads under this module's
    # name, so the integration need not recalculate per-building forecasts.
    statements = [b.get('operatingStatement', b.get(STATE_KEY, b)) for b in buildings]
    potential = _figures(sum(b.get('potentialTakeHome', 0) for b in statements),
                         sum(b.get('potentialProductionCosts', 0) for b in statements),
                         sum(b.get('potentialSellingCosts', 0) for b in statements))
    result.update({'potential' + key[0].upper() + key[1:]: value for key, value in potential.items()})
    owned = {_identity(st, slot) for slot in range(len(st['b']))}
    removed_fees = sum(row['sellingCosts'] for bucket in data.get('buckets', [])
                       for source, payments in bucket['sources'].items() if source in earnings.OPERATING_SOURCES
                       for identity, row in payments.items() if identity not in owned)
    removed_production = _production_spending(cfg, st) - sum(_production_spending(cfg, st, identity) for identity in owned)
    result.update(unattributed=_figures(receipts['unattributed']['operatingIncome'], removed_production, removed_fees),
                  bySource={source: dict(takeHome=receipts['bySource'][source],
                                         sellingCosts=_recent_fees(cfg, st, sources=(source,)),
                                         grossSales=receipts['bySource'][source] + _recent_fees(cfg, st, sources=(source,)))
                            for source in earnings.SOURCES},
                  enabled=enabled(cfg), basis='cash', windowSeconds=WINDOW_SECONDS,
                  observedSeconds=min(WINDOW_SECONDS, max(0, st.get('tick', 0) - data.get('startedTick', st.get('tick', 0))) * cfg['global']['tick']),
                  totals=dict(data.get('totals', _empty_totals())))
    return result


def payload(cfg, st, buildings=()):
    return town_statement(cfg, st, buildings)
