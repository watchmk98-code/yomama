"""Small ordinary deliveries for the current opening goal and supply estimates.

Goal offers live beside the three random offers. This module never settles a
delivery, grants a project reward, or advances the live economy. The engine
owns all payment, reservation, and delivery-observation transactions.
"""
from __future__ import annotations

import copy
import math

import town_projects


GOAL_KEY = 'goalOffer'
SERIAL_KEY = 'goalOrderSerial'
MAX_ESTIMATE_TICKS = 240


def _current(cfg, st, can_make=None):
    if not town_projects.connected(cfg) or st.get('legacyProjectOffer'):
        return None
    progress = st.get(town_projects.STATE_KEY, {})
    stage = progress.get('completed', 0)
    if type(stage) is not int or not 0 <= stage < town_projects.TOTAL:
        return None
    project = town_projects.PROJECTS[stage]
    tier = next((i for i, row in enumerate(cfg['tiers'])
                 if row['id'] == project['building']), None)
    if tier not in st.get('tierOf', []):
        return None
    delivered = progress.get('groupProgress', {}).get('delivered', {}).get(project['id'], {})
    requirements = [dict(goodId=gid, quantity=max(0, quantity - delivered.get(gid, 0)))
                    for gid, quantity in project['goods']]
    requirements = [row for row in requirements if row['quantity'] > 0]
    if not requirements or can_make and not all(can_make(row['goodId']) for row in requirements):
        return None
    return stage, project, requirements


def sync(cfg, st, can_make=None):
    """Update only goalOffer/goalOrderSerial; existing saved terms are immutable.

    Saved terms survive other deliveries that change progress. The engine
    removes the offer after delivery or when the player claims this goal.
    The caller must initialize/migrate townProjects before calling this helper.
    """
    existing = st.get(GOAL_KEY)
    if existing and (existing.get('committed') or existing.get('inTransit')):
        return existing
    current = _current(cfg, st, can_make)
    if current is None:
        st.pop(GOAL_KEY, None)
        return None
    stage, project, requirements = current
    if (existing and existing.get('goalOrder') and existing.get('projectId') == project['id']
            and existing.get('requirements') == requirements):
        return existing
    goods = {good['id']: good for tier in cfg['tiers'] for good in tier['goods']}
    value = sum(goods[row['goodId']]['unitPrice'] * row['quantity'] for row in requirements)
    serial = st.get(SERIAL_KEY, 0) + 1
    st[SERIAL_KEY] = serial
    order = dict(id='goal-order-{}-{}'.format(st.get('rngState', 1), serial),
                 name=project['title'], recipeId='goal_' + project['id'],
                 goalOrder=True, projectId=project['id'], projectStage=stage,
                 buildingId=project['building'], channelLabel='Next goal delivery',
                 purpose='A small delivery toward your next goal.',
                 description=project['description'], requirements=requirements,
                 reward=int(math.floor(value * 1.25 + .5)), retailValue=value,
                 rewardPercent=125, materials=0, customer=None, committed=False,
                 rarity='standard', rarityLabel='Goal delivery')
    st[GOAL_KEY] = order
    return order


def check(cfg, st, order, can_make=None):
    """Reject stale IDs or empty offers before the caller consumes/pays goods."""
    saved = st.get(GOAL_KEY)
    if (not saved or not order or not order.get('goalOrder')
            or saved.get('id') != order.get('id') or saved != order):
        return dict(ok=False, why='This goal delivery changed. Check your next goal.')
    requirements = order.get('requirements')
    if not isinstance(requirements, list) or not requirements or any(
            not isinstance(row, dict) or type(row.get('quantity')) is not int
            or row['quantity'] <= 0 or not isinstance(row.get('goodId'), str)
            for row in requirements):
        return dict(ok=False, why='This goal delivery has no valid goods to deliver.')
    if not order.get('committed') and not order.get('inTransit'):
        current = _current(cfg, st, can_make)
        if current is None or current[1]['id'] != order.get('projectId') or current[2] != requirements:
            return dict(ok=False, why='This goal delivery changed. Check your next goal.')
    return dict(ok=True)


def _result(status, reason='', seconds=None, committed=False):
    if seconds == 0:
        label = 'Ready to deliver'
    elif seconds is not None:
        minutes = math.ceil(seconds / 60)
        duration = '{}s'.format(seconds) if seconds < 60 else '{} min'.format(minutes)
        label = ('About ' if committed else 'If saved: about ') + duration
    else:
        label = dict(paused='Production paused', locked='Open or unlock the producer',
                     storage='Make shelf room', cash='Need production cash',
                     regulars='Regular buyer uses these goods', stopped='Production stopped',
                     long='Timing depends on your other orders').get(status, 'Timing unavailable')
    return dict(etaSeconds=seconds if committed or seconds == 0 else None,
                etaIfSavedSeconds=seconds if not committed and seconds not in (None, 0) else None,
                etaStatus=status, etaLabel=label, etaReason=reason)


def estimate(cfg, st, order, supply):
    """Read-only, bounded supply forecast from engine-supplied current facts.

    ``goods`` descriptors contain stored, savedReserved (other saved orders),
    regularReserved, capacity, speed (work/tick), work, cycleTicks, quantity,
    batchMultiplier, delayTicks, batchCost, paused, unlocked, producerOwned.
    ``regulars`` contain requirements, nextTicks, intervalTicks, and name.

    The forecast assumes the candidate is saved. It respects existing regular
    priorities and their schedules, batch sizes, shelf limits and current cash.
    No uncertain future walk-in income funds production. A regular needing
    unrelated products is conservatively assumed able to ship those products.
    This is an approximate production estimate, never an order deadline.
    """
    committed = bool(order.get('committed'))
    if supply.get('paused'):
        return _result('paused', 'The class clock is paused. Resume to make more goods.')
    needs = {row['goodId']: row['quantity'] for row in order.get('requirements', [])}
    descriptors = supply.get('goods', {})
    if not needs or any(gid not in descriptors for gid in needs):
        return _result('locked', 'Open the business that makes these goods first.')
    models = {gid: copy.deepcopy(descriptors[gid]) for gid in needs}

    def ready():
        return all(row.get('stored', 0) - row.get('savedReserved', 0)
                   - row.get('regularReserved', 0) >= needs[gid] for gid, row in models.items())

    if ready():
        return _result('ready', seconds=0, committed=committed)
    for gid, row in models.items():
        if row.get('stored', 0) - row.get('savedReserved', 0) - row.get('regularReserved', 0) >= needs[gid]:
            continue
        name = row.get('name', gid.replace('_', ' '))
        if not row.get('producerOwned', True) or not row.get('unlocked', True):
            return _result('locked', 'Open or unlock the business that makes ' + name + '.')
        if row.get('paused'):
            return _result('paused', 'Resume the business that makes ' + name + '.')
        if row.get('speed', 0) <= 0:
            return _result('stopped', name + ' is not being produced at the current settings.')
        if needs[gid] + row.get('savedReserved', 0) + row.get('regularReserved', 0) > row['capacity']:
            return _result('storage', 'Release another saved order, pause a regular buyer, or add shelf space for ' + name + '.')
        if row.get('nextBatchCost', row.get('batchCost', 0)) > supply.get('cash', st.get('cash', 0)):
            return _result('cash', 'Keep enough cash to produce ' + name + '. Timing depends on future sales.')
        buyer_can_clear = any(any(need['goodId'] == gid for need in buyer['requirements'])
                              for buyer in supply.get('regulars', []))
        if row.get('quantity', 1) > row['capacity'] - row.get('stored', 0) and not buyer_can_clear:
            return _result('storage', 'Clear shelf space so the next batch of ' + name + ' can fit.')

    regulars = copy.deepcopy(supply.get('regulars', []))
    regulars = [row for row in regulars
                if any(need['goodId'] in needs for need in row['requirements'])]
    cash = max(0, supply.get('cash', st.get('cash', 0)))
    for elapsed in range(1, MAX_ESTIMATE_TICKS + 1):
        for gid, row in models.items():
            if row.get('paused') or not row.get('unlocked', True) or not row.get('producerOwned', True):
                continue
            if row.get('delayTicks', 0) > 0:
                row['delayTicks'] -= 1
                continue
            base = row['cycleTicks'] * 100
            row['work'] = row.get('work', 0) + row.get('speed', 0)
            quantity = row.get('quantity', 1)
            multiplier = row.get('batchMultiplier', 1)
            while row['work'] >= base:
                batches = min(multiplier, max(0, (row['capacity'] - row.get('stored', 0)) // quantity))
                if not batches:
                    row['work'] = min(row['work'], base * multiplier)
                    break
                cost = row.get('batchCost', 0)
                if batches > 1 and batches * cost > cash:
                    batches = 1
                if row['work'] < base * batches:
                    break
                if batches * cost > cash:
                    return _result('cash', 'More operating cash is needed before these goods can finish. Timing depends on future sales.')
                row['stored'] = row.get('stored', 0) + quantity * batches
                row['work'] -= base * batches
                cash -= batches * cost
        prior_regular = {}
        for regular in regulars:
            overlapping = [need for need in regular['requirements'] if need['goodId'] in models]
            available = all(models[need['goodId']].get('stored', 0)
                            - models[need['goodId']].get('inTransitReserved', 0)
                            - prior_regular.get(need['goodId'], 0) >= need['quantity']
                            for need in overlapping)
            if elapsed >= regular.get('nextTicks', 0) and available:
                for need in overlapping:
                    models[need['goodId']]['stored'] -= need['quantity']
                regular['nextTicks'] = elapsed + max(1, regular['intervalTicks'])
            for need in overlapping:
                gid = need['goodId']
                prior_regular[gid] = prior_regular.get(gid, 0) + need['quantity']
        if ready():
            reason = 'Approximate supply time at current production settings; keep enough operating cash.'
            if regulars:
                reason += ' Existing regular buyers receive their goods first.'
            return _result('saving' if committed else 'if_saved', reason,
                           elapsed * supply.get('tickSeconds', cfg['global']['tick']), committed)
    if regulars:
        return _result('regulars', 'Pause a regular buyer to save these goods sooner; a reliable completion time is not available at the current settings.')
    return _result('long', 'More than an hour at the current settings. Save fewer competing goods or increase production.')
