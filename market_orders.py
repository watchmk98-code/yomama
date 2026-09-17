"""Manual market tools: relevant offers and bounded delivery batches."""
from __future__ import annotations

import copy

import business_progression
import production_economy as economy


def eligible_goods(cfg, st):
    return [gid for gid, good in economy.catalog(cfg).items()
            if good['tier'] in st['tierOf'] and business_progression.product_unlocked(cfg, st, gid)]


def protected(order):
    return any(order.get(key) for key in ('committed', 'inTransit', 'project', 'goalOrder'))


def defaults(cfg, st):
    st.setdefault('marketKnownGoods', eligible_goods(cfg, st))
    st.setdefault('marketPendingGoods', [])


def pending_tier(cfg, st):
    """Give a queued producer the next freed card, even on a fully ready board."""
    pending = st.get('marketPendingGoods') or []
    if not pending or st.get('orderEngine', {}).get('prototype'):
        return None
    goods = economy.catalog(cfg)
    represented = {goods[n['goodId']]['tier'] for o in st.get('offers') or []
                   if not o.get('project') for n in o['requirements']}
    available = set(eligible_goods(cfg, st))
    return next((goods[gid]['tier'] for gid in pending
                 if gid in available and goods[gid]['tier'] not in represented), None)


def ready(cfg, st, order):
    held = economy.delivery_reservations(cfg, st, exclude=order['id'])
    return bool(order['requirements']) and all(
        st['inventory'].get(n['goodId'], 0) - held.get(n['goodId'], 0) >= n['quantity']
        for n in order['requirements'])


def sync(cfg, st):
    """Introduce newly available products once; keep saved and ready offers.

    Old saves establish a baseline without replacing their existing promises.
    Pending products survive reloads when every card is occupied.
    """
    if st.get('orderEngine', {}).get('prototype'):
        return
    available = eligible_goods(cfg, st)
    known = st.setdefault('marketKnownGoods', list(available))
    pending = st.setdefault('marketPendingGoods', [])
    pending[:] = list(dict.fromkeys([gid for gid in pending if gid in available] +
                                   [gid for gid in available if gid not in known]))
    st['marketKnownGoods'] = list(available)
    goods = economy.catalog(cfg)
    offers = st.get('offers') or []
    introduced = set()
    for gid in list(pending):
        tier = goods[gid]['tier']
        # One introduction covers this producer; selecting it can find more.
        represented = any(any(goods[n['goodId']]['tier'] == tier for n in o['requirements'])
                          for o in offers if not o.get('project'))
        if not represented:
            slot = next((i for i, o in enumerate(offers[:3])
                         if i not in introduced and not protected(o) and not ready(cfg, st, o)), None)
            if slot is None:
                continue
            offers[slot] = economy._make_order(cfg, st, slot, target_tier=tier)
            introduced.add(slot)
        pending[:] = [item for item in pending if goods[item]['tier'] != tier]


def _selection(st, rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        return None
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        index, order_id = row.get('offerIndex'), row.get('orderId')
        if type(index) is not int or index not in range(3) or index in selected:
            return None
        if not isinstance(order_id, str) or not economy._order_check(st, index, order_id)['ok']:
            return None
        selected.append(index)
    return selected


def fulfill_ready(cfg, st, rows):
    selected = _selection(st, rows)
    if selected is None:
        return dict(ok=False, why='These orders changed. Refresh and try again.')
    # Only the submitted, visible cards can be delivered, never replacements.
    working = copy.deepcopy(st)
    receipts = []
    for index in selected:
        order = working['offers'][index]
        if order.get('project') or order.get('goalOrder') or order.get('inTransit'):
            continue
        result = economy.fulfill_order(cfg, working, index, order['id'])
        if result['ok']:
            receipts.append(result)
    if not receipts:
        return dict(ok=False, why='No selected orders have enough unreserved goods.')
    st.clear(); st.update(working)
    sync(cfg, st)
    return dict(ok=True, kind='orders_batch', delivered=len(receipts),
                reward=sum(r['reward'] for r in receipts),
                orderIds=[r['orderId'] for r in receipts], skipped=len(selected)-len(receipts))

