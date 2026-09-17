"""Cross-business development focuses, owned and timed by the economy server.

Completed nodes are the source of permanent modifiers, so reloading a save
never adds a bonus again. Timers use the class clock, including absence but
excluding a teacher pause. There is no client completion or cancellation.
"""
from __future__ import annotations

import math

import business_progression
import quest_engine
from economy import jsround


NODES = (
    dict(id='secure_harvest', title='Secure the Harvest', branch=None,
         description='Invest in a dependable harvest and give your food business a strong start.',
         requires=(), owns=('farm',), rewardText='Farm production +5% of base speed'),
    dict(id='reliable_supply', title='Reliable Supply', branch=None,
         description='Build room for the next harvest and connect your growing businesses.',
         requires=('secure_harvest',), owns=('farm',), rewardText='Farm storage +20%'),
    dict(id='preserve_surplus', title='Preserve the Surplus', branch='volume',
         description='Turn your cannery into a high-output supplier for the wider business network.',
         requires=('reliable_supply',), owns=('cannery',), rewardText='Cannery production +10% of base speed'),
    dict(id='distribution_network', title='Distribution Network', branch='volume',
         description='Build a reputation for dependable deliveries and earn more from every order.',
         requires=('preserve_surplus',), owns=('cannery',), rewardText='Delivery order rewards +8%'),
    dict(id='regional_supplier', title='Regional Supplier', branch='volume',
         description='Give all your food businesses the shelf space to serve a growing region.',
         requires=('distribution_network',), owns=('cannery',), rewardText='All Food business storage +15%'),
    dict(id='local_brand', title='Build a Local Brand', branch='premium',
         description='Make your roastery a destination for local customers.',
         requires=('reliable_supply',), owns=('roastery',), rewardText='Roastery walk-in demand +10%'),
    dict(id='breakfast_regulars', title='Breakfast Regulars', branch='premium',
         description='Reward reliable service with better payments from your regular buyers.',
         requires=('local_brand', 'secure_harvest'), owns=('farm', 'roastery'), regular=True,
         rewardText='Regular buyer rewards +8%'),
    dict(id='signature_experience', title='Signature Experience', branch='premium',
         description='Perfect your signature food products and produce them faster.',
         requires=('breakfast_regulars',), owns=('roastery',), levels={'roastery': 3},
         rewardText='Food signature products +10% of base speed'),
    dict(id='food_empire', title='Regional Business Network', branch=None,
         description='Complete either strategy and claim a voucher for your next business upgrade.',
         requires=(), requiresAny=('regional_supplier', 'signature_experience'), owns=('farm',),
         rewardText='One 1,000 YM business upgrade voucher'),
    dict(id='workshop_foundation', title='Workshop Foundations', branch=None,
         description='Build the industrial skills that food processing and logistics need.',
         requires=(), owns=('workshop',), rewardText='Workshop production +5% of base speed'),
    dict(id='clean_power', title='Clean Power', branch=None,
         description='Develop your solar co-op into the energy foundation of a connected town.',
         requires=(), owns=('solar_coop',), rewardText='Solar co-op production +5% of base speed'),
    dict(id='powered_industry', title='Powered Industry', branch=None,
         description='Connect workshop expertise with clean energy to strengthen industrial production.',
         requires=('workshop_foundation', 'clean_power'), owns=('workshop', 'solar_coop'),
         rewardText='All Industry production +5% of base speed'),
    dict(id='automated_packaging', title='Automated Packaging', branch=None,
         description='Combine cannery production with workshop engineering to improve packaging.',
         requires=('preserve_surplus', 'workshop_foundation'), owns=('cannery', 'workshop'), developed=('cannery',),
         rewardText='Cannery production +5% of base speed'),
    dict(id='smart_grid', title='Smart Grid', branch=None,
         description='Connect powered industry to a relay station and coordinate energy production.',
         requires=('powered_industry',), owns=('generator', 'relay_station'),
         rewardText='All Energy production +5% of base speed'),
    dict(id='shared_logistics', title='Shared Logistics', branch=None,
         description='Join food distribution and automated packaging through your freight terminal.',
         requires=('distribution_network', 'automated_packaging'), owns=('freight_terminal',),
         rewardText='All Industry storage +15%'),
    dict(id='digital_market', title='Digital Marketplace', branch=None,
         description='Bring your local brand online using a smart grid and data hub.',
         requires=('local_brand', 'smart_grid'), owns=('data_center',),
         rewardText='All business walk-in demand +5%'),
    dict(id='connected_economy', title='Connected Economy', branch=None,
         description='Unite your regional businesses, freight network and digital marketplace.',
         requires=('food_empire', 'shared_logistics', 'digital_market'), owns=(),
         rewardText='All business storage +10%'),
)
# Positions and artwork are shared with the browser; edges come from requirements.
LAYOUT = {
    'secure_harvest': (1, 1, 'FOOD', 'secure_harvest'),
    'reliable_supply': (1, 2, 'FOOD', 'reliable_supply'),
    'preserve_surplus': (1, 3, 'FOOD', 'preserve_surplus'),
    'distribution_network': (1, 4, 'LOGISTICS', 'distribution_network'),
    'regional_supplier': (1, 5, 'FOOD', 'regional_supplier'),
    'local_brand': (2, 3, 'COMMERCE', 'local_brand'),
    'breakfast_regulars': (2, 4, 'FOOD + COMMERCE', 'breakfast_regulars'),
    'signature_experience': (2, 5, 'COMMERCE', 'signature_experience'),
    'food_empire': (2, 6, 'REGIONAL NETWORK', 'food_empire'),
    'workshop_foundation': (3, 1, 'INDUSTRY', 'workshop'),
    'clean_power': (4, 1, 'ENERGY', 'solar_coop'),
    'powered_industry': (3, 2, 'INDUSTRY + ENERGY', 'machine_works'),
    'automated_packaging': (3, 4, 'FOOD + INDUSTRY', 'cannery'),
    'smart_grid': (4, 4, 'ENERGY + INDUSTRY', 'relay_station'),
    'shared_logistics': (3, 5, 'LOGISTICS + INDUSTRY', 'freight_terminal'),
    'digital_market': (4, 5, 'COMMERCE + ENERGY', 'data_center'),
    'connected_economy': (3, 7, 'ALL BUSINESSES', 'food_empire'),
}
BY_ID = {node['id']: node for node in NODES}
STATE_KEY = 'focusTree'
# Early construction takes 1–3 minutes, industrial construction 20–90 minutes,
# and late infrastructure 3–4 hours. Focuses complement that pace, not days of
# idle waiting. No focus is required to buy a business, earn Prestige or unlock
# a recipe; the existing progression systems retain ownership of those gates.
DURATION_MINUTES = {
    'secure_harvest': 5, 'reliable_supply': 10, 'local_brand': 10,
    'breakfast_regulars': 15, 'signature_experience': 20, 'food_empire': 20,
    'workshop_foundation': 20, 'clean_power': 30, 'powered_industry': 30,
    'preserve_surplus': 30, 'distribution_network': 30, 'regional_supplier': 45,
    'automated_packaging': 45, 'smart_grid': 60, 'shared_logistics': 60,
    'digital_market': 90, 'connected_economy': 120,
}


def enabled(cfg, st):
    return cfg.get('version') == 4 and st.get('modelVersion') == 4


def ensure(cfg, st):
    """Add state to existing v4 towns without changing their other progress."""
    if not enabled(cfg, st):
        return {}
    data = st.setdefault(STATE_KEY, {})
    data['version'] = 2
    data.setdefault('completed', {})
    data.setdefault('active', None)
    # v1 choices no longer exclude businesses. Keep completions and timers.
    data['branch'] = None
    data.setdefault('voucherRemaining', 0)
    return data


def duration_ticks(cfg, focus_id='secure_harvest'):
    return max(1, math.ceil(DURATION_MINUTES[focus_id] * 60 / cfg['global']['tick']))


def has(st, focus_id):
    return focus_id in st.get(STATE_KEY, {}).get('completed', {})


def _owned(cfg, st):
    return {cfg['tiers'][b['tier']]['id'] for b in st.get('b', ())
            if type(b.get('tier')) is int and 0 <= b['tier'] < len(cfg['tiers'])}


def _requirements(cfg, st, node):
    completed = st.get(STATE_KEY, {}).get('completed', {})
    rows = [dict(text='Complete ' + BY_ID[key]['title'], met=key in completed)
            for key in node['requires']]
    if node.get('requiresAny'):
        rows.append(dict(text='Complete ' + ' or '.join(BY_ID[key]['title'] for key in node['requiresAny']),
                         met=any(key in completed for key in node['requiresAny'])))
    names = {tier['id']: tier['name'] for tier in cfg['tiers']}
    owned = _owned(cfg, st)
    rows.extend(dict(text='Own ' + names.get(key, key.replace('_', ' ').title()), met=key in owned)
                for key in node['owns'])
    if node.get('regular'):
        regulars = st.get('customerContracts', {})
        rows.append(dict(text='Sign your first regular buyer in Market',
                         met=bool(regulars.get('active') or regulars.get('history') or regulars.get('serial', 0))))
    for key, level in node.get('levels', {}).items():
        rows.append(dict(text=names.get(key, key) + ': Production level ' + str(level),
                         met=any(cfg['tiers'][b['tier']]['id'] == key and b.get('lv', 1) >= level
                                 for b in st.get('b', ()))))
    for key in node.get('developed', ()):
        tier = next(t for t in cfg['tiers'] if t['id'] == key)
        good = tier['goods'][-1]
        rows.append(dict(text='Unlock ' + good['name'] + ' through business development',
                         met=business_progression.product_unlocked(cfg, st, good['id'])))
    return rows


def _status(data, node, requirements):
    if node['id'] in data['completed']:
        return 'completed', 'Focus already completed'
    active = data['active']
    if active and active['id'] == node['id']:
        return 'active', 'Focus in progress'
    missing = next((row['text'] for row in requirements if not row['met']), None)
    if missing:
        return 'locked', missing
    if active:
        return 'locked', 'Finish your active focus first'
    return 'available', ''


def act(cfg, st, body):
    if not enabled(cfg, st):
        return dict(ok=False, why='Focus trees require the production economy')
    if not isinstance(body, dict) or body.get('action') != 'start':
        return dict(ok=False, why='Choose a focus to start')
    focus_id = body.get('focusId')
    if not isinstance(focus_id, str) or focus_id not in BY_ID:
        return dict(ok=False, why='Unknown focus')
    data = ensure(cfg, st)
    node = BY_ID[focus_id]
    status, why = _status(data, node, _requirements(cfg, st, node))
    if status != 'available':
        return dict(ok=False, why=why)
    tick = st['tick']
    data['active'] = dict(id=focus_id, startedTick=tick, endsTick=tick + duration_ticks(cfg, focus_id))
    return dict(ok=True, kind='focus_tree', action='start', focusId=focus_id)


def advance(cfg, st, tick):
    """Complete at most one focus. Returns its ID once, else None."""
    data = ensure(cfg, st)
    active = data.get('active')
    if not active or tick < active['endsTick']:
        return None
    focus_id = active['id']
    data['active'] = None
    if focus_id in data['completed']:
        return None
    data['completed'][focus_id] = active['endsTick']
    if focus_id == 'food_empire':
        if quest_engine.enabled(cfg):
            quest_engine._grant(cfg, st, dict(type='upgrade_voucher', amount=1000))
        else:
            # Old class snapshots may predate the quest engine. They receive
            # the same upgrade-only benefit without changing their rules.
            data['voucherRemaining'] += 1000
    return focus_id


def speed_bonus(cfg, st, building, good):
    tier = cfg['tiers'][building['tier']]
    bonus = 5 if tier['id'] == 'farm' and has(st, 'secure_harvest') else 0
    if tier['id'] == 'cannery' and has(st, 'preserve_surplus'):
        bonus += 10
    for focus_id, applies in (
            ('workshop_foundation', tier['id'] == 'workshop'),
            ('clean_power', tier['id'] == 'solar_coop'),
            ('powered_industry', tier['family'] == 'I'),
            ('automated_packaging', tier['id'] == 'cannery'),
            ('smart_grid', tier['family'] == 'E')):
        if applies and has(st, focus_id):
            bonus += 5
    if tier['family'] == 'F' and good['id'] == tier['goods'][-1]['id'] and has(st, 'signature_experience'):
        bonus += 10
    return bonus


def storage_percent(cfg, st, tier):
    bonus = 20 if tier['id'] == 'farm' and has(st, 'reliable_supply') else 0
    if tier['family'] == 'F' and has(st, 'regional_supplier'):
        bonus += 15
    if tier['family'] == 'I' and has(st, 'shared_logistics'):
        bonus += 15
    if has(st, 'connected_economy'):
        bonus += 10
    return 100 + bonus


def demand_percent(cfg, st, building):
    bonus = 10 if cfg['tiers'][building['tier']]['id'] == 'roastery' and has(st, 'local_brand') else 0
    return 100 + bonus + (5 if has(st, 'digital_market') else 0)


def order_reward(st, reward):
    return jsround(reward * 108 / 100) if has(st, 'distribution_network') else reward


def regular_reward(st, reward):
    return jsround(reward * 108 / 100) if has(st, 'breakfast_regulars') else reward


def voucher_cover(st, cost):
    return min(max(0, cost), st.get(STATE_KEY, {}).get('voucherRemaining', 0))


def apply_voucher(st, cost):
    covered = voucher_cover(st, cost)
    if covered:
        st[STATE_KEY]['voucherRemaining'] -= covered
    return cost - covered, covered


def payload(cfg, st):
    if not enabled(cfg, st):
        return dict(enabled=False, nodes=[], completed=[], active=None, branch=None)
    data = ensure(cfg, st)
    active = data['active']
    if active:
        remaining = max(0, active['endsTick'] - st['tick'])
        duration = max(1, active['endsTick'] - active['startedTick'])
        active = dict(active, remainingTicks=remaining, remainingSeconds=remaining * cfg['global']['tick'],
                      progressPercent=round(min(100, max(0, (duration - remaining) * 100 / duration)), 1))
    nodes = []
    for node in NODES:
        ticks = (data['active']['endsTick'] - data['active']['startedTick']
                 if data['active'] and data['active']['id'] == node['id']
                 else duration_ticks(cfg, node['id']))
        requirements = _requirements(cfg, st, node)
        status, why = _status(data, node, requirements)
        column, row, sector, art = LAYOUT[node['id']]
        nodes.append(dict(id=node['id'], title=node['title'], description=node['description'],
                          column=column, row=row, sector=sector, art=art,
                          branch=node['branch'], requires=list(node['requires']),
                          requiresAny=list(node.get('requiresAny', ())), requirements=requirements,
                          durationDays=ticks * cfg['global']['tick'] / 86400,
                          durationTicks=ticks, durationSeconds=ticks * cfg['global']['tick'],
                          rewardText=node['rewardText'], status=status, canStart=status == 'available', why=why))
    completed = [node['id'] for node in NODES if has(st, node['id'])]
    return dict(enabled=True, title='Focus Tree', branch=None, active=active,
                completed=completed, completedCount=len(completed), totalNodes=len(NODES),
                pathNodes=len(NODES), nodes=nodes, voucherRemaining=data['voucherRemaining'],
                effects=[BY_ID[key]['rewardText'] for key in completed])
