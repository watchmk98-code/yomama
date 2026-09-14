"""Finite town-opening projects and construction-only entitlements.

This module owns progression, never the economy transaction. The caller checks
unreserved stock, debits goods, and pays the order before calling ``complete``.
Construction grants cover the complete quote without consuming cash/materials;
the caller consumes the grant only after its queue/frontier checks have passed.
Connected groups observe already-settled ordinary deliveries. Their claim
returns a cash reward for the caller to pay, and never consumes goods again.
No engine import is used, so the economy can safely import these helpers.
"""
from __future__ import annotations

import math


PROJECTS = (
    dict(id='farm_neighbors', title='Feed the neighborhood',
         description='Send fresh tomatoes to your neighbors to earn a fully funded fish stall.',
         purpose='A small produce delivery opens your next business.',
         building='farm', goods=(('farm_tomatoes', 6),), grant='fish_stall'),
    dict(id='harbor_lunch', title='Serve the harbor lunch',
         description='Supply smoked fish and oysters to earn a fully funded roastery.',
         purpose='Deliver your fish stall’s products before opening another business.',
         building='fish_stall', goods=(('fish_stall_smoked_fish', 2), ('fish_stall_oysters', 4)),
         grant='roastery'),
    dict(id='cafe_opening', title='Open the neighborhood cafe',
         description='Send espresso and pastries to welcome your cafe customers.',
         purpose='Your roastery makes coffee and pastries to bring the neighborhood together.',
         building='roastery', goods=(('roastery_espresso_shots', 4), ('roastery_pastries', 2)),
         grant=None),
)
TOTAL = len(PROJECTS)
STATE_KEY = 'townProjects'
RECENT_DELIVERY_LIMIT = 128
GROUP_COPY = {
    'farm_neighbors': ('Launch farm supply',
                       'Deliver 6 tomatoes through ordinary orders to earn fully funded fish-stall construction.',
                       'Your first supplier funds the next business in your conglomerate.'),
    'harbor_lunch': ('Establish seafood processing',
                     'Deliver 2 smoked fish and 4 oysters through ordinary orders to earn fully funded roastery construction.',
                     'Produce seafood at your fish stall before adding another business.'),
    'cafe_opening': ('Open the neighborhood café',
                     'Deliver 4 espresso shots and 2 pastries through ordinary orders to earn a permanent customer bonus.',
                     'Your roastery produces its own espresso and pastries for the neighborhood.'),
}


def _count(value):
    try:
        return max(0, min(TOTAL, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _tier(cfg, building_id):
    return next((i for i, item in enumerate(cfg.get('tiers', []))
                 if item.get('id') == building_id), None)


def _building_name(cfg, building_id):
    tier = _tier(cfg, building_id)
    return cfg['tiers'][tier]['name'] if tier is not None else building_id.replace('_', ' ').title()


def _owned(cfg, st, building_id):
    tier = _tier(cfg, building_id)
    return tier is not None and tier in st.get('tierOf', [])


def _owned_or_pending(cfg, st, building_id):
    tier = _tier(cfg, building_id)
    if tier is None:
        return False
    build = st.get('build') or {}
    return tier in st.get('tierOf', []) or tier in st.get('queue', []) or build.get('i') == tier


def _goods(cfg):
    return {good['id']: good for tier in cfg.get('tiers', []) for good in tier.get('goods', [])}


def enabled(cfg):
    """Small custom/test rule sets need not contain this particular opening."""
    catalog = _goods(cfg)
    return all(_tier(cfg, p['building']) is not None
               and all(gid in catalog for gid, _ in p['goods']) for p in PROJECTS)


def connected(cfg):
    design = cfg.get('businessDesign', {})
    return bool(design.get('enabled') and design.get('connectedProgression')) and enabled(cfg)


def _grant(data, cfg, st, building_id):
    if not building_id:
        return
    grants = data['grants']
    if _owned_or_pending(cfg, st, building_id):
        grants[building_id] = 'used'
    elif grants.get(building_id) not in ('used', 'ready'):
        grants[building_id] = 'ready'


def migrate(cfg, st):
    """Add progression without changing old orders, goods, cash or buildings.

    Existing loyalty deliveries count as completed project steps. Existing or
    queued starter buildings also satisfy their opening steps, without cash
    refunds or newly awarding their corresponding grants. Earned grants survive
    saving; a consumed grant is never restored by repeated migration.
    """
    data = st.get(STATE_KEY)
    observing = connected(cfg) and isinstance(data, dict) and isinstance(data.get('groupProgress'), dict)
    legacy = _count(st.get('regularDeliveries', 0))
    inferred = 2 if _owned_or_pending(cfg, st, 'roastery') else (
        1 if _owned_or_pending(cfg, st, 'fish_stall') else 0)
    # Import existing ownership once. Afterwards group achievements come from
    # deliveries and claims, never a later purchase or construction queue.
    if observing:
        inferred = 0
    if not isinstance(data, dict):
        data = dict(version=1, completed=max(legacy, inferred), legacyCredit=legacy, grants={})
        st[STATE_KEY] = data
        for step, project in enumerate(PROJECTS[:2], 1):
            target = project['grant']
            if _owned_or_pending(cfg, st, target):
                data['grants'][target] = 'used'
            elif legacy >= step and legacy < TOTAL:
                data['grants'][target] = 'ready'
            elif inferred >= step or legacy == TOTAL:
                data['grants'][target] = 'skipped'
    else:
        data.setdefault('version', 1)
        if not isinstance(data.get('grants'), dict):
            data['grants'] = {}
        prior_credit = _count(data.get('legacyCredit', 0))
        # A preserved pre-project breakfast order can still pay its promised
        # loyalty credit when the player eventually fulfills it.
        if legacy > prior_credit:
            for step, project in enumerate(PROJECTS[:2], 1):
                if prior_credit < step <= legacy and legacy < TOTAL:
                    _grant(data, cfg, st, project['grant'])
            data['legacyCredit'] = legacy
        data['completed'] = max(_count(data.get('completed', 0)), legacy, inferred)
        for step, project in enumerate(PROJECTS[:2], 1):
            target = project['grant']
            if _owned_or_pending(cfg, st, target):
                data['grants'][target] = 'used'
            elif inferred >= step and target not in data['grants']:
                data['grants'][target] = 'skipped'
    if connected(cfg):
        group = data.setdefault('groupProgress', {})
        group.setdefault('version', 1)
        group.setdefault('delivered', {})
        group.setdefault('seenOrderIds', [])
        group.setdefault('creditedOrderIds', [])
        del group['seenOrderIds'][:-RECENT_DELIVERY_LIMIT]
    return data


def default(cfg, st):
    """Initialize a new town; also safe to call on an existing save."""
    return migrate(cfg, st)


def _reward_text(cfg, project):
    if project['grant']:
        return 'Fully funded ' + _building_name(cfg, project['grant']) + ' construction'
    return '+20% roastery walk-in customers, permanently'


def current_order(cfg, st):
    """Return the current fixed third-slot order, or None after completion.

    Does not replace ``st['offers']``: integration must honor an existing third
    card until fulfilled or explicitly replaced. ``check`` remains required,
    because the next project's producer can still be under construction.
    """
    data = migrate(cfg, st)
    if data['completed'] >= TOTAL or not enabled(cfg):
        return None
    stage = data['completed']
    project = PROJECTS[stage]
    catalog = _goods(cfg)
    value = sum(catalog[gid]['unitPrice'] * qty for gid, qty in project['goods'])
    return dict(id='town-project-' + project['id'], name=project['title'],
                project=True, projectId=project['id'], projectStage=stage,
                buildingId=project['building'],
                recipeId='project_' + project['id'], purpose=project['purpose'],
                description=project['description'], channelLabel='Town project',
                requirements=[dict(goodId=gid, quantity=qty) for gid, qty in project['goods']],
                reward=int(math.floor(value * 1.25 + .5)), retailValue=value,
                rewardPercent=125, materials=0, customer=None, committed=False,
                rewardText=_reward_text(cfg, project))


def check(cfg, st, order_id):
    """Validate project identity and producer access, not goods/payment."""
    order = current_order(cfg, st)
    if order is None:
        return dict(ok=False, why='These town projects are complete' if enabled(cfg)
                    else 'These town projects are unavailable with this town\'s rules')
    if order_id != order['id']:
        return dict(ok=False, why='This town project changed. Check your current project.')
    project = PROJECTS[order['projectStage']]
    if not _owned(cfg, st, project['building']):
        return dict(ok=False, why='Open ' + _building_name(cfg, project['building']) + ' first',
                    requiredBuildingId=project['building'])
    return dict(ok=True, projectId=project['id'])


def gate(cfg, st, order_id):
    return check(cfg, st, order_id)


def complete(cfg, st, order_id):
    """Advance one validated, economically settled project, exactly once."""
    result = check(cfg, st, order_id)
    if not result['ok']:
        return result
    data = st[STATE_KEY]
    project = PROJECTS[data['completed']]
    data['completed'] += 1
    if project['grant']:
        _grant(data, cfg, st, project['grant'])
    else:
        st['regularDeliveries'] = max(3, st.get('regularDeliveries', 0))
        data['legacyCredit'] = TOTAL
    return dict(ok=True, kind='town_project', projectId=project['id'],
                completed=data['completed'], grantBuildingId=project['grant'],
                rewardText=_reward_text(cfg, project))


def record_delivery(cfg, st, requirements, order_id):
    """Observe one successful ordinary delivery; the engine owns settlement.

    Only the project active when this event occurs can receive progress. Receipt
    Contributing IDs survive every stage/reload, bounded by the finite required
    goods totals. Recent noncontributing IDs are bounded; the engine rejects
    already-settled offers before invoking this observer. No inventory snapshot
    or practice stock is progress; completed groups retain no new receipts.
    """
    if not connected(cfg):
        return dict(ok=True, kind='group_project_progress', recorded=False)
    if not isinstance(order_id, str) or not order_id or len(order_id) > 200:
        return dict(ok=False, why='A settled delivery ID is required')
    if not isinstance(requirements, (list, tuple)) or any(
            not isinstance(need, dict) or not isinstance(need.get('goodId'), str)
            or type(need.get('quantity')) is not int or need['quantity'] <= 0
            for need in requirements):
        return dict(ok=False, why='A settled delivery needs whole positive goods quantities')
    data = migrate(cfg, st)
    group = data['groupProgress']
    if (data['completed'] >= TOTAL or order_id in group['seenOrderIds']
            or order_id in group['creditedOrderIds']):
        return dict(ok=True, kind='group_project_progress', recorded=False)
    group['seenOrderIds'].append(order_id)
    del group['seenOrderIds'][:-RECENT_DELIVERY_LIMIT]
    project = PROJECTS[data['completed']]
    access = check(cfg, st, 'town-project-' + project['id'])
    if not access['ok']:
        return dict(ok=True, kind='group_project_progress', recorded=False,
                    projectId=project['id'], why=access['why'])
    supplied = {}
    for need in requirements:
        gid = need['goodId']
        supplied[gid] = supplied.get(gid, 0) + need['quantity']
    delivered = group['delivered'].setdefault(project['id'], {})
    added = {}
    for gid, target in project['goods']:
        prior = min(target, max(0, delivered.get(gid, 0)))
        amount = min(target - prior, supplied.get(gid, 0))
        if amount:
            delivered[gid] = prior + amount
            added[gid] = amount
    if added:
        group['creditedOrderIds'].append(order_id)
    return dict(ok=True, kind='group_project_progress', recorded=bool(added),
                projectId=project['id'], added=added,
                ready=all(delivered.get(gid, 0) >= qty for gid, qty in project['goods']))


def check_claim(cfg, st, project_id):
    """Validate a group milestone without consuming its already-delivered goods."""
    if not connected(cfg):
        return dict(ok=False, why='Group projects are not enabled for this conglomerate')
    data = migrate(cfg, st)
    if data['completed'] >= TOTAL:
        return dict(ok=False, why='These group projects are complete')
    project = PROJECTS[data['completed']]
    if project_id != project['id']:
        return dict(ok=False, why='This group project changed. Check your current project.')
    if _legacy_project_pending(st, project):
        return dict(ok=False, why='Complete your saved project delivery first')
    access = check(cfg, st, 'town-project-' + project['id'])
    if not access['ok']:
        return access
    delivered = data['groupProgress']['delivered'].get(project['id'], {})
    goods = _goods(cfg)
    for gid, quantity in project['goods']:
        missing = quantity - delivered.get(gid, 0)
        if missing > 0:
            return dict(ok=False, why='Deliver ' + str(missing) + ' more ' + goods[gid]['name'] + ' in ordinary orders')
    order = current_order(cfg, st)
    return dict(ok=True, projectId=project['id'], cashReward=order['reward'])


def _legacy_project_pending(st, project):
    saved = st.get('legacyProjectOffer')
    return isinstance(saved, dict) and (saved.get('projectId') == project['id']
                                       or saved.get('id') == 'town-project-' + project['id'])


def _group_suppliers(cfg, st, project):
    producers = {good['id']: tier['id'] for tier in cfg['tiers'] for good in tier['goods']}
    direct = {producers[gid] for gid, _ in project['goods']}
    return [dict(buildingId=tier['id'], name=tier['name'], owned=_owned(cfg, st, tier['id']),
                 role='Products')
            for tier in cfg['tiers'] if tier['id'] in direct]


def claim(cfg, st, project_id):
    """Advance once; the engine pays cashReward in its same atomic transaction."""
    result = check_claim(cfg, st, project_id)
    if not result['ok']:
        return result
    completed = complete(cfg, st, 'town-project-' + project_id)
    if not completed['ok']:
        return completed
    return dict(completed, kind='group_project_claim', cashReward=result['cashReward'])


def group_payload(cfg, st):
    """Separate progress guide; all three Market cards remain ordinary orders."""
    if not connected(cfg):
        return dict(enabled=False, completed=0, total=TOTAL, current=None, projects=[])
    data = migrate(cfg, st)
    goods = _goods(cfg)
    done = data['completed']
    rows = []
    for stage, project in enumerate(PROJECTS):
        title, description, purpose = GROUP_COPY[project['id']]
        completed = stage < done
        current = stage == done
        delivered = data['groupProgress']['delivered'].get(project['id'], {})
        requirements = [dict(goodId=gid, name=goods[gid]['name'], quantity=qty,
                             delivered=qty if completed else min(qty, max(0, delivered.get(gid, 0))),
                             remaining=0 if completed else max(0, qty - delivered.get(gid, 0)))
                        for gid, qty in project['goods']]
        access = check(cfg, st, 'town-project-' + project['id']) if current else dict(ok=False)
        if current and _legacy_project_pending(st, project):
            access = dict(ok=False, why='Complete your saved project delivery first')
        ready = current and access['ok'] and all(need['remaining'] == 0 for need in requirements)
        why = '' if completed or ready else (access.get('why', '') if current and not access['ok'] else
              'Fulfill ordinary orders containing these goods' if current else
              'Complete ' + GROUP_COPY[PROJECTS[stage - 1]['id']][0] + ' first')
        value = sum(goods[gid]['unitPrice'] * qty for gid, qty in project['goods'])
        rows.append(dict(id=project['id'], projectId=project['id'], name=title, title=title,
                         buildingId=project['building'], buildingName=_building_name(cfg, project['building']),
                         description=description, purpose=purpose, stage=stage,
                         suppliers=_group_suppliers(cfg, st, project),
                         requirements=requirements,
                         progressPercent=round(100 * sum(n['delivered'] for n in requirements) /
                                               sum(n['quantity'] for n in requirements), 1),
                         ready=ready, canClaim=ready, why=why, unlockText=why,
                         completed=completed, status='completed' if completed else 'ready' if ready else
                         'tracking' if current and access['ok'] else 'locked',
                         cashReward=int(math.floor(value * 1.25 + .5)), rewardText=_reward_text(cfg, project)))
    return dict(enabled=True, completed=done, total=TOTAL, current=rows[done] if done < TOTAL else None,
                projects=rows, status='complete' if done >= TOTAL else rows[done]['status'],
                title='Conglomerate opening projects complete' if done >= TOTAL else rows[done]['title'],
                description='Ordinary deliveries grow your connected businesses. Each project reward is claimed once.')


def construction_grant(cfg, st, tier):
    """Inspect a noncash entitlement covering the entire target build quote."""
    data = migrate(cfg, st)
    if type(tier) is not int or not 0 <= tier < len(cfg.get('tiers', [])):
        return None
    target = cfg['tiers'][tier]['id']
    if data['grants'].get(target) != 'ready' or _owned_or_pending(cfg, st, target):
        return None
    return dict(buildingId=target, tier=tier, fullCost=True,
                label=_building_name(cfg, target) + ' construction grant',
                description='Construction is fully funded. Your cash and materials stay in your town.')


def consume_construction_grant(cfg, st, tier):
    """Redeem only after the caller validates capacity, frontier and timing."""
    grant = construction_grant(cfg, st, tier)
    if grant is None:
        return dict(ok=False, why='No construction grant is available for this business')
    st[STATE_KEY]['grants'][grant['buildingId']] = 'used'
    return dict(ok=True, **grant)


def _project_rows(cfg, st, available=None, catalog_available=None):
    """Keep each existing project visible under its business as progress changes."""
    if not enabled(cfg):
        return []
    done = migrate(cfg, st)['completed']
    goods = _goods(cfg)
    inventory = st.get('inventory', {}) if catalog_available is None else catalog_available
    rows = []
    for stage, project in enumerate(PROJECTS):
        order_id = 'town-project-' + project['id']
        existing = next((order for order in st.get('offers') or []
                         if order.get('project') and order.get('id') == order_id), None)
        current = stage == done
        stock = available if current and existing and available is not None else inventory
        status, unlock_text = 'completed', ''
        if stage > done:
            status = 'locked'
            unlock_text = 'Complete ' + PROJECTS[stage - 1]['title'] + ' first'
        elif current:
            access = check(cfg, st, order_id)
            status = 'available' if access['ok'] and existing else 'locked'
            if not access['ok']:
                unlock_text = access['why']
            elif not existing:
                unlock_text = 'Finish or replace your saved delivery in Market first'
        rows.append(dict(id=project['id'], buildingId=project['building'],
                         buildingName=_building_name(cfg, project['building']),
                         title=project['title'], description=project['description'],
                         purpose=project['purpose'], rewardText=_reward_text(cfg, project),
                         status=status, unlockText=unlock_text,
                         orderId=order_id if current and existing else None,
                         requirements=[dict(goodId=gid, name=goods[gid]['name'],
                                            quantity=qty, owned=max(0, stock.get(gid, 0)))
                                       for gid, qty in project['goods']]))
    return rows


def project_payload(cfg, st, available=None, catalog_available=None):
    """Player guide; pass engine-computed available stock for accurate readiness."""
    data = migrate(cfg, st)
    done = data['completed']
    projects = _project_rows(cfg, st, available, catalog_available)
    if done >= TOTAL:
        return dict(status='complete', completed=TOTAL, total=TOTAL,
                    projects=projects,
                    title='Neighborhood cafe established',
                    description='Your opening projects are complete.',
                    purpose='Choose a regular buyer and keep your connected businesses supplied.',
                    rewardText='+20% roastery walk-in customers earned',
                    nextAction='Choose your next operating plan', orderId=None)
    project = PROJECTS[done]
    order = current_order(cfg, st)
    if order is None:
        return dict(status='locked', completed=done, total=TOTAL,
                    projects=projects,
                    title=project['title'], description=project['description'],
                    purpose=project['purpose'], rewardText=_reward_text(cfg, project),
                    nextAction='This project is unavailable with this town\'s rules', orderId=None)
    access = check(cfg, st, order['id'])
    inventory = st.get('inventory', {}) if available is None else available
    ready = all(inventory.get(n['goodId'], 0) >= n['quantity'] for n in order['requirements'])
    existing = next((o for o in st.get('offers') or [] if o.get('id') == order['id']), {})
    committed = bool(existing.get('committed'))
    status = 'locked' if not access['ok'] else 'ready' if ready else 'available'
    action = access['why'] if not access['ok'] else (
        'Deliver your project goods' if ready else
        'Your project goods are being saved' if committed else 'Save goods for this project')
    return dict(status=status, completed=done, total=TOTAL, projectId=project['id'], projects=projects,
                title=project['title'], description=project['description'], purpose=project['purpose'],
                rewardText=order['rewardText'], nextAction=action, orderId=order['id'],
                requiredBuildingId=project['building'], committed=committed,
                requirements=[dict(n, available=max(0, inventory.get(n['goodId'], 0)))
                              for n in order['requirements']])
