"""Standalone three-card prototype; the live Market does not import this module.

Card one takes time to deliver, card two automatically chooses one sector, and
card three retains the current engine's offers and actions. Prices, rarity,
reservations, and delivery accounting follow the existing economy.
"""
from __future__ import annotations

import copy
import hashlib
import math

import business_progression as progression
import production_economy as economy
from delivery_recipes import ORDER_RECIPES


ORDER_CLASSES = (
    dict(id='cooldown', index=0, label='Delivery orders'),
    dict(id='sector', index=1, label='Sector orders'),
    dict(id='standard', index=2, label='Current orders'),
)


def class_profiles():
    return copy.deepcopy(list(ORDER_CLASSES))


def _label(offer, index):
    profile = ORDER_CLASSES[index]
    return dict(offer, classId=profile['id'], classLabel=profile['label'])


def _validate_base_seconds(base_seconds):
    if (type(base_seconds) not in (int, float) or not math.isfinite(base_seconds)
            or base_seconds <= 0):
        raise ValueError('Delivery base must be a positive number of seconds')


def quote_delivery_seconds(cfg, offer, base_seconds=60):
    """Quote cash-based travel time, rounded up to a game tick; never mutate."""
    _validate_base_seconds(base_seconds)
    reward = offer.get('reward')
    if (type(reward) not in (int, float) or not math.isfinite(reward) or reward < 0):
        raise ValueError('Delivery cash reward must be a finite nonnegative number')
    tick_seconds = cfg['global']['tick']
    duration = max(30, base_seconds * math.sqrt(reward / 300))
    return math.ceil(duration / tick_seconds) * tick_seconds


def _prepare_delivery_offer(cfg, board):
    offer = _label(board['offers'][0], 0)
    metadata = board['orderEngine']
    if 'deliverySeconds' not in offer:
        # Old shipments keep their original full duration and arrival tick.
        offer['deliverySeconds'] = (metadata['cooldownTicks'] * cfg['global']['tick']
                                    if offer.get('inTransit') else
                                    quote_delivery_seconds(cfg, offer, metadata['deliveryBaseSeconds']))
    board['offers'][0] = offer


def _sector_recipes(cfg, state):
    goods = economy.catalog(cfg)
    slots = {tier: slot for slot, tier in enumerate(state['tierOf'])}

    def can_make(gid):
        return (gid in goods and goods[gid]['tier'] in slots
                and progression.product_unlocked(cfg, state, gid))

    sectors = {}
    for recipe in ORDER_RECIPES:
        selected = set(recipe['goods'])
        if not selected or len(selected) != len(recipe['goods']) or not all(can_make(gid) for gid in selected):
            continue
        families = {cfg['tiers'][goods[gid]['tier']]['family'] for gid in selected}
        if len(families) != 1:
            continue
        if any(economy._good_capacity(cfg, state, slots[goods[gid]['tier']], gid) < 1 for gid in selected):
            continue
        sectors.setdefault(next(iter(families)), []).append(recipe)
    return goods, sectors


def _sector_order(cfg, state):
    goods, sectors = _sector_recipes(cfg, state)
    if not sectors:
        raise ValueError('No sector orders can be supplied by these businesses')
    serial = state['orderSerial']
    digest = hashlib.sha256('{}:{}:1:order-roll-v1'.format(state.get('rngState', 1), serial).encode()).digest()
    roll = int.from_bytes(digest[:8], 'big') % 100
    rarity = economy.ORDER_ROLLS[-1]
    for candidate in economy.ORDER_ROLLS:
        if roll < candidate['chance']:
            rarity = candidate
            break
        roll -= candidate['chance']
    previous = state['orderEngine'].get('lastSector')
    choices = sorted(sectors)
    if len(choices) > 1 and previous in choices:
        choices.remove(previous)
    sector = choices[int.from_bytes(digest[16:24], 'big') % len(choices)]
    recipes = sectors[sector]
    target = rarity['items'] or 2
    sizes = [len(r['goods']) for r in recipes if len(r['goods']) <= target]
    size = max(sizes) if sizes else min(len(r['goods']) for r in recipes)
    candidates = [r for r in recipes if len(r['goods']) == size]
    history = state.setdefault('orderRecipeHistory', [[], [], []])[1]
    on_board = {offer.get('recipeId') for offer in state.get('offers') or []}
    unseen = [r for r in candidates if r['id'] not in history]
    if unseen:
        unseen = [r for r in unseen if r['id'] not in on_board] or unseen
        recipe = unseen[int.from_bytes(digest[8:16], 'big') % len(unseen)]
    else:
        rank = {rid: i for i, rid in enumerate(history)}
        recipe = min(candidates, key=lambda r: rank[r['id']])
    requirements = []
    value = 0
    for gid in recipe['goods']:
        good = goods[gid]
        quantity = max(2, math.ceil(cfg['production']['orderMinutes'][1] * 60
                                   / (good['cycleTicks'] * cfg['global']['tick'])))
        quantity = math.ceil(quantity * rarity['quantityPercent'] / 100)
        slot = state['tierOf'].index(good['tier'])
        quantity = min(quantity, economy._good_capacity(cfg, state, slot, gid))
        requirements.append(dict(goodId=gid, quantity=quantity))
        value += quantity * good['unitPrice']
    reward_percent = economy.jsround(110 * rarity['payoutPercent'] / 100)
    if recipe['id'] in history:
        history.remove(recipe['id'])
    history.append(recipe['id'])
    del history[:-len(ORDER_RECIPES)]
    state['orderSerial'] += 1
    state['orderEngine']['lastSector'] = sector
    return _label(dict(id='order-{}-{}'.format(state.get('rngState', 1), serial),
                       name=recipe['name'], recipeId=recipe['id'], purpose=recipe['purpose'],
                       channelLabel='Building supplies', requirements=requirements,
                       reward=economy.jsround(value * reward_percent / 100),
                       materials=max(1, economy.jsround(value * .25 / cfg['production']['materialCashValue'])),
                       customer=None, committed=False, rarity=rarity['id'], rarityLabel=rarity['label'],
                       rewardPercent=reward_percent, retailValue=value,
                       sectorId=sector, sectorLabel=cfg['families'][sector]['name']), 1)


def create_board(cfg, source_state, *, cooldown_seconds=60):
    """Copy a town; cooldown_seconds is the base delivery time for a 300 YM job."""
    _validate_base_seconds(cooldown_seconds)
    board = copy.deepcopy(source_state)
    economy.offer_contracts(cfg, board, board['tick'])
    if len(board['offers']) != 3:
        raise ValueError('The prototype requires three order cards')
    if board.get('orderEngine', {}).get('prototype'):
        _migrate_delivery_board(cfg, board)
        return board
    board['orderEngine'] = dict(prototype=True, deliveryBaseSeconds=cooldown_seconds,
                                cooldownTicks=math.ceil(cooldown_seconds / cfg['global']['tick']),
                                cooldownUntilTick=None, lastSector=None, lastDelivery=None)
    _prepare_delivery_offer(cfg, board)
    board['offers'][1] = _sector_order(cfg, board)
    return board


def cooldown_remaining(cfg, board):
    offer = board['offers'][0]
    until = offer.get('deliveryUntilTick') if offer.get('inTransit') else None
    return 0 if until is None else max(0, (until - board['tick']) * cfg['global']['tick'])


def _migrate_delivery_board(cfg, board):
    """An old waiting card was already settled or skipped; never pay it again."""
    metadata = board['orderEngine']
    metadata.setdefault('lastDelivery', None)
    metadata.setdefault('deliveryBaseSeconds', metadata['cooldownTicks'] * cfg['global']['tick'])
    metadata['cooldownUntilTick'] = None
    if board['offers'][0].get('waiting'):
        board['offers'][0] = economy._make_order(cfg, board, 0)
    _prepare_delivery_offer(cfg, board)


def refresh_board(cfg, board):
    """Settle arrivals once against the saved game clock, then offer the next job."""
    _migrate_delivery_board(cfg, board)
    offer = board['offers'][0]
    if not offer.get('inTransit') or cooldown_remaining(cfg, board) > 0:
        return board
    working = copy.deepcopy(board)
    result = economy._settle_order(cfg, working, working['offers'][0])
    if result['ok']:
        working['orderEngine']['lastDelivery'] = dict(
            orderId=offer['id'], reward=result['reward'], materials=result['materials'],
            rarity=offer.get('rarity', 'standard'))
        working['offers'][0] = economy._make_order(cfg, working, 0)
        _prepare_delivery_offer(cfg, working)
        economy._sync_pools(cfg, working)
        board.clear()
        board.update(working)
    return board


def _dispatch(cfg, board):
    offer = board['offers'][0]
    held = economy.delivery_reservations(cfg, board, exclude=offer['id'])
    goods = economy.catalog(cfg)
    for need in offer['requirements']:
        gid = need['goodId']
        if board['inventory'].get(gid, 0) - held.get(gid, 0) < need['quantity']:
            return dict(ok=False, why='Need unreserved ' + goods[gid]['name'])
    room = economy._commit_room(cfg, board, offer)
    if not room['ok']:
        return room
    duration_seconds = offer['deliverySeconds']
    economy._freeze_selling_terms(cfg,board,offer)
    offer.update(committed=True, inTransit=True,
                 deliveryUntilTick=board['tick'] + duration_seconds // cfg['global']['tick'])
    return dict(ok=True, kind='order_dispatch', orderId=offer['id'], reward=0, materials=0,
                durationSeconds=duration_seconds)


def _delivery_reservation_check(board):
    """A later commitment cannot claim goods already assigned to a shipment."""
    offer = board['offers'][0]
    if offer.get('inTransit'):
        held = economy.order_reservations(board)
        if any(board['inventory'].get(n['goodId'], 0) < held.get(n['goodId'], 0)
               for n in offer['requirements']):
            return dict(ok=False, why='These goods are already on their way. Wait for the delivery or save more stock.')
    return dict(ok=True)


def apply_action(cfg, board, index, action, order_id=None):
    """Apply an existing order action atomically to this isolated prototype only.

    Call refresh_board after advancing the game tick. An in-transit card never
    accepts another action, even when due; refreshing settles its original terms.
    """
    check = economy._order_check(board, index, order_id)
    if not check['ok']:
        return check
    if action not in ('fulfill', 'replace', 'commit', 'release'):
        return dict(ok=False, why='Choose a valid order action')
    if index == 0 and (board['offers'][0].get('inTransit') or board['offers'][0].get('waiting')):
        return dict(ok=False, why='This delivery is on its way',
                    remainingSec=cooldown_remaining(cfg, board))
    working = copy.deepcopy(board)
    if action in ('commit', 'release'):
        result = economy.commit_order(cfg, working, index, order_id, action == 'commit')
        if result['ok'] and action == 'commit':
            protected = _delivery_reservation_check(working)
            if not protected['ok']:
                result = protected
    elif index == 2:
        handler = economy.fulfill_order if action == 'fulfill' else economy.replace_order
        result = handler(cfg, working, index, order_id)
    else:
        if action == 'replace':
            result = dict(ok=True, kind='replace_order')
        elif index == 0:
            result = _dispatch(cfg, working)
        else:
            result = economy._settle_order(cfg, working, working['offers'][index])
        if result['ok']:
            if index == 0 and action == 'replace':
                working['offers'][0] = economy._make_order(cfg, working, 0)
                _prepare_delivery_offer(cfg, working)
            elif index == 1:
                working['offers'][1] = _sector_order(cfg, working)
            if action == 'fulfill' and index == 1:
                economy._sync_pools(cfg, working)
    if result['ok']:
        board.clear()
        board.update(working)
    return result
