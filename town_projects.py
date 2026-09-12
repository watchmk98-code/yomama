"""Finite town-opening projects and construction-only entitlements.

This module owns progression, never the economy transaction. The caller checks
unreserved stock, debits goods, and pays the order before calling ``complete``.
Construction grants cover the complete quote without consuming cash/materials;
the caller consumes the grant only after its queue/frontier checks have passed.
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
         purpose='Turn fresh catch into a finished meal before connecting another business.',
         building='fish_stall', goods=(('fish_stall_smoked_fish', 2), ('fish_stall_oysters', 4)),
         grant='roastery'),
    dict(id='cafe_opening', title='Open the neighborhood cafe',
         description='Send espresso and pastries to welcome your cafe customers.',
         purpose='Your farm supplies the pastries; your roastery brings the neighborhood together.',
         building='roastery', goods=(('roastery_espresso_shots', 4), ('roastery_pastries', 2)),
         grant=None),
)
TOTAL = len(PROJECTS)
STATE_KEY = 'townProjects'


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
    legacy = _count(st.get('regularDeliveries', 0))
    inferred = 2 if _owned_or_pending(cfg, st, 'roastery') else (
        1 if _owned_or_pending(cfg, st, 'fish_stall') else 0)
    data = st.get(STATE_KEY)
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
    # Old towns can own a processor without its suppliers. Every ingredient
    # producer must exist before this project can reserve or consume goods.
    producers = {good['id']: tier['id'] for tier in cfg['tiers'] for good in tier['goods']}
    goods = _goods(cfg)
    pending = [need['goodId'] for need in order['requirements']]
    seen = set()
    while pending:
        gid = pending.pop()
        if gid in seen:
            continue
        seen.add(gid)
        if not _owned(cfg, st, producers[gid]):
            return dict(ok=False, why='Open ' + _building_name(cfg, producers[gid]) + ' first',
                        requiredBuildingId=producers[gid])
        pending.extend(need['goodId'] for need in goods[gid].get('inputs', []))
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


def project_payload(cfg, st, available=None):
    """Player guide; pass engine-computed available stock for accurate readiness."""
    data = migrate(cfg, st)
    done = data['completed']
    if done >= TOTAL:
        return dict(status='complete', completed=TOTAL, total=TOTAL,
                    title='Neighborhood cafe established',
                    description='Your opening projects are complete.',
                    purpose='Choose a regular buyer and keep your connected businesses supplied.',
                    rewardText='+20% roastery walk-in customers earned',
                    nextAction='Choose your next operating plan', orderId=None)
    project = PROJECTS[done]
    order = current_order(cfg, st)
    if order is None:
        return dict(status='locked', completed=done, total=TOTAL,
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
    return dict(status=status, completed=done, total=TOTAL, projectId=project['id'],
                title=project['title'], description=project['description'], purpose=project['purpose'],
                rewardText=order['rewardText'], nextAction=action, orderId=order['id'],
                requiredBuildingId=project['building'], committed=committed,
                requirements=[dict(n, available=max(0, inventory.get(n['goodId'], 0)))
                              for n in order['requirements']])
