"""Data-driven quests. Definitions are content in config/quests.v1.json.

The engine observes activity the economy already settles; it never produces
goods, never debits stock a second time, and never pays a reward twice. A
refused claim changes nothing: act() validates against a copy and only then
commits. Boost charges are spent on real multiplied value, never on wall
clock, so an offline catch-up and a live session consume them identically.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import rules_tables

CONFIG_PATH = Path(__file__).parent / 'config/quests.v1.json'
STATE_KEY = 'questEngine'
OPENING = ('farm', 'fish_stall', 'roastery')
# Boosts multiply an order delivery: one visible payout the player chose to
# earn. Walk-in retail settles per good per tick, so a charge spent there would
# vanish in seconds without a decision behind it.
METRICS = frozenset(('order_payout',))
SALE_SOURCES = frozenset(('orders', 'walkIns', 'regularBuyers', 'clearance'))
ACTIONS = frozenset(('quest_claim',))
RECENT_LIMIT = 12


def configure(cfg):
    """Stage the quest content on a class config. Not called in production
    until the engine is switched on; see QUEST_ENGINE_DESIGN.md."""
    cfg[STATE_KEY] = json.loads(CONFIG_PATH.read_text(encoding='utf8'))
    return cfg


def enabled(cfg):
    return cfg.get('version') == 4 and cfg.get(STATE_KEY, {}).get('enabled') is True


# ---------------------------------------------------------------- definitions

def quests(cfg):
    return rules_tables.derived(cfg, 'quest_engine_quests', _build_quests)


def _build_quests(cfg):
    spec = cfg.get(STATE_KEY, {})
    result = {}
    for quest in spec.get('quests', ()):
        result[quest['id']] = dict(quest, source='chapter')
    for template in spec.get('templates', ()):
        if template.get('forEachBusiness'):
            for quest in _expand(cfg, template):
                result[quest['id']] = quest
    return result


def _expand(cfg, template):
    """One template becomes one quest per business, so twelve near-identical
    records stay a single edit. Businesses with fewer than three goods, and
    the opening three that keep their recipes, are skipped."""
    skip = set(template.get('skipBusinesses', ()))
    for tier in cfg.get('tiers', ()):
        goods = tier.get('goods', ())
        if tier['id'] in skip or len(goods) < 3:
            continue
        fields = {
            'businessId': tier['id'], 'businessName': tier['name'],
            'good1': goods[0]['id'], 'good1Name': goods[0]['name'],
            'good2': goods[1]['id'], 'good2Name': goods[1]['name'],
            'good3': goods[2]['id'], 'good3Name': goods[2]['name'],
        }
        quest = _fill(template, fields)
        quest.pop('forEachBusiness', None)
        quest.pop('skipBusinesses', None)
        quest['id'] = template['id'] + ':' + tier['id']
        quest['source'] = 'template'
        quest['buildingId'] = tier['id']
        yield quest


def _fill(value, fields):
    if isinstance(value, str):
        return value.format(**fields) if '{' in value else value
    if isinstance(value, dict):
        return {key: _fill(item, fields) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, fields) for item in value]
    return value


def _catalog(cfg):
    return rules_tables.derived(cfg, 'quest_engine_catalog', _build_catalog)


def _build_catalog(cfg):
    return {g['id']: t['id'] for t in cfg.get('tiers', ()) for g in t.get('goods', ())}


# --------------------------------------------------------------------- state

def ensure(cfg, st):
    if not enabled(cfg):
        return {}
    data = st.setdefault(STATE_KEY, {})
    defaults = dict(version=1, counters={}, completed={}, boosts=[], vouchers=[],
                    flags=[], unlockedRecipes=[], perks={}, features=[], grants=[],
                    recent=[], sequence=0)
    for key, value in defaults.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
    return data


def _bump(data, name, amount):
    data['counters'][name] = data['counters'].get(name, 0) + amount


# --------------------------------------------------------------- observation

def record_production(cfg, st, good_id, qty):
    """Observe a completed batch. Never creates goods."""
    if not enabled(cfg) or type(qty) is not int or qty <= 0:
        return
    building = _catalog(cfg).get(good_id)
    if building is None:
        return
    data = ensure(cfg, st)
    _bump(data, 'produce:' + good_id, qty)
    _bump(data, 'produce:business:' + building, qty)
    _bump(data, 'produce:any', qty)


def record_sale(cfg, st, requirements, source):
    """Observe goods that a caller has already settled and paid for."""
    if not enabled(cfg) or not isinstance(source, str):
        return
    data = ensure(cfg, st)
    catalog = _catalog(cfg)
    for need in requirements or ():
        gid, qty = need.get('goodId'), need.get('quantity')
        if gid not in catalog or type(qty) is not int or qty <= 0:
            continue
        _bump(data, 'sell:' + gid, qty)
        _bump(data, 'sell:business:' + catalog[gid], qty)
        _bump(data, 'sell:any', qty)
        if source in SALE_SOURCES:
            _bump(data, 'sell:source:' + source, qty)


def record_order(cfg, st):
    """One completed manual order, whatever it contained."""
    if not enabled(cfg):
        return
    _bump(ensure(cfg, st), 'deliver:order', 1)


def record_action(cfg, st, verb, amount=1):
    """A thing the player did once: upgrade, focus_node, accept_contract,
    set_regular, open_business, port_trade, quiz_pass."""
    if not enabled(cfg) or not isinstance(verb, str) or type(amount) is not int or amount <= 0:
        return
    _bump(ensure(cfg, st), 'act:' + verb, amount)


# ---------------------------------------------------------------- objectives

def _owned(cfg, st):
    tiers = cfg.get('tiers', ())
    return {tiers[ti]['id'] for ti in st.get('tierOf', ())
            if type(ti) is int and 0 <= ti < len(tiers)}


def _state_value(cfg, st, objective):
    check = objective.get('check')
    if check == 'own:businesses':
        return len(_owned(cfg, st))
    if check == 'businesses_at_level':
        level = objective.get('level', 1)
        return sum(1 for b in st.get('b', ()) if b.get('lv', 1) >= level)
    if isinstance(check, str) and check.startswith('level:'):
        bid = check.split(':', 1)[1]
        tiers = cfg.get('tiers', ())
        slots = {tiers[ti]['id']: slot for slot, ti in enumerate(st.get('tierOf', ()))
                 if type(ti) is int and 0 <= ti < len(tiers)}
        slot = slots.get(bid)
        return st['b'][slot].get('lv', 1) if slot is not None and slot < len(st.get('b', ())) else 0
    if isinstance(check, str) and check.startswith('unlocked:'):
        return int(check.split(':', 1)[1] in ensure(cfg, st)['unlockedRecipes'])
    return 0


def _progress(cfg, st, quest):
    data = ensure(cfg, st)
    rows = []
    for objective in quest.get('objectives', ()):
        target = max(1, int(objective.get('target', 1)))
        owned = (data['counters'].get(objective.get('counter', ''), 0)
                 if objective.get('kind') == 'count' else _state_value(cfg, st, objective))
        rows.append(dict(label=objective.get('label', ''), owned=min(owned, target),
                         quantity=target, ready=owned >= target))
    return rows


def _visible(cfg, st, quest):
    appear = quest.get('appear', {})
    data = ensure(cfg, st)
    for dependency in appear.get('afterQuests', ()):
        if dependency not in data['completed']:
            return False
    owns = appear.get('ownsBusiness')
    owned = _owned(cfg, st)
    if owns is not None and owns not in owned:
        return False
    return len(owned) >= appear.get('minBuildings', 0)


def _row(cfg, st, quest):
    data = ensure(cfg, st)
    done = quest['id'] in data['completed']
    objectives = _progress(cfg, st, quest)
    ready = not done and bool(objectives) and all(o['ready'] for o in objectives)
    started = any(o['owned'] for o in objectives)
    return dict(id=quest['id'], chapter=quest.get('chapter', 0), title=quest.get('title', ''),
                summary=quest.get('summary', ''), teaches=quest.get('teaches', ''),
                buildingId=quest.get('buildingId'), source=quest.get('source', 'chapter'),
                status='done' if done else 'ready' if ready else 'tracking' if started else 'available',
                objectives=objectives, rewardText=reward_text(cfg, quest), ready=ready)


def reward_text(cfg, quest):
    labels = (_reward_label(cfg, r) for r in quest.get('rewards', ()))
    return ' · '.join(label for label in labels if label)


def _reward_label(cfg, reward):
    kind = reward.get('type')
    if kind == 'cash':
        return str(reward.get('amount', 0)) + ' YM'
    if kind == 'supplies':
        return 'Supply pack'
    if kind == 'boost':
        return ('×' + str(reward.get('multiplier', 1)) + ' ' +
                reward.get('metric', '').replace('_', ' ') + ' · ' +
                str(reward.get('charges', 0)) + ' uses')
    if kind == 'upgrade_voucher':
        return 'Upgrade voucher ' + str(reward.get('amount', 0)) + ' YM'
    if kind == 'grant_building':
        return 'A funded ' + _business_name(cfg, reward.get('businessId'))
    if kind == 'unlock_recipe':
        return 'Unlock ' + _good_name(cfg, reward.get('goodId'))
    if kind == 'unlock_craft':
        return 'Unlock a crafted product'
    if kind == 'unlock_feature':
        return 'Unlock ' + str(reward.get('feature', '')).replace('_', ' ')
    if kind == 'speed_perk':
        return '+' + str(reward.get('percent', 0)) + '% ' + _good_name(cfg, reward.get('goodId')) + ' speed'
    return ''


def _business_name(cfg, bid):
    return next((t['name'] for t in cfg.get('tiers', ()) if t['id'] == bid), str(bid))


def _good_name(cfg, gid):
    return next((g['name'] for t in cfg.get('tiers', ()) for g in t.get('goods', ())
                 if g['id'] == gid), str(gid))


def payload(cfg, st):
    if not enabled(cfg):
        return dict(enabled=False, quests=[], boosts=[], vouchers=[], features=[], recent=[])
    data = ensure(cfg, st)
    rows = [_row(cfg, st, quest) for quest in quests(cfg).values()
            if _visible(cfg, st, quest) or quest['id'] in data['completed']]
    rows.sort(key=lambda r: (r['chapter'], r['id']))
    return dict(enabled=True, quests=rows,
                boosts=[dict(metric=b['metric'], multiplier=b['multiplier'], charges=b['charges'])
                        for b in data['boosts'] if b['charges'] > 0],
                vouchers=[dict(amount=v['remaining']) for v in data['vouchers'] if v['remaining'] > 0],
                features=list(data['features']), recent=list(data['recent']),
                completed=len(data['completed']), total=len(quests(cfg)))


# ------------------------------------------------------------------- rewards

def _grant(cfg, st, reward):
    data = ensure(cfg, st)
    kind = reward.get('type')
    if kind == 'cash':
        st['cash'] = st.get('cash', 0) + max(0, int(reward.get('amount', 0)))
    elif kind == 'supplies':
        _supply_pack(cfg, st, int(reward.get('budget', 0)))
    elif kind == 'boost':
        if reward.get('metric') in METRICS:
            data['sequence'] += 1
            data['boosts'].append(dict(id=data['sequence'], metric=reward['metric'],
                                       multiplier=max(1, int(reward.get('multiplier', 1))),
                                       charges=max(0, int(reward.get('charges', 0)))))
    elif kind == 'upgrade_voucher':
        amount = max(0, int(reward.get('amount', 0)))
        data['sequence'] += 1
        data['vouchers'].append(dict(id=data['sequence'], amount=amount, remaining=amount))
    elif kind == 'grant_building':
        bid = reward.get('businessId')
        if bid is not None and bid not in data['grants']:
            data['grants'].append(bid)
    elif kind == 'unlock_recipe':
        gid = reward.get('goodId')
        if gid is not None and gid not in data['unlockedRecipes']:
            data['unlockedRecipes'].append(gid)
    elif kind == 'unlock_craft':
        pilot = st.get('craftingPilot')
        if isinstance(pilot, dict):
            pilot.setdefault('unlocked', {})[reward.get('itemId')] = True
    elif kind == 'unlock_feature':
        feature = reward.get('feature')
        if feature is not None and feature not in data['features']:
            data['features'].append(feature)
    elif kind == 'speed_perk':
        gid = reward.get('goodId')
        if gid is not None:
            data['perks'][gid] = data['perks'].get(gid, 0) + max(0, int(reward.get('percent', 0)))
    elif kind == 'flag':
        name = reward.get('name')
        if name is not None and name not in data['flags']:
            data['flags'].append(name)


def _supply_pack(cfg, st, budget):
    """Reuse the crafting pilot's award, which owns supply identities and
    values. Without the pilot there is nowhere to put supplies, so nothing
    is granted rather than inventing a currency."""
    if budget <= 0:
        return
    try:
        import crafting_pilot
    except ImportError:
        return
    if crafting_pilot.enabled(cfg) and isinstance(st.get('crafting'), dict):
        crafting_pilot._award(cfg, st, 'Quest reward', budget)


# ------------------------------------------------------- read by other systems

def product_unlocked(cfg, st, gid):
    """True when this good needs no quest unlock, or its quest granted it."""
    if not enabled(cfg):
        return True
    tiers = cfg.get('tiers', ())
    building = next((t for t in tiers if any(g['id'] == gid for g in t.get('goods', ()))), None)
    if building is None or building['id'] in OPENING or len(building.get('goods', ())) < 3:
        return True
    if building['goods'][-1]['id'] != gid:
        return True
    return gid in ensure(cfg, st)['unlockedRecipes']


def speed_bonus(cfg, st, gid):
    return ensure(cfg, st)['perks'].get(gid, 0) if enabled(cfg) else 0


def has_flag(cfg, st, name):
    return enabled(cfg) and name in ensure(cfg, st)['flags']


def has_feature(cfg, st, feature):
    return enabled(cfg) and feature in ensure(cfg, st)['features']


def building_grant(cfg, st, bid):
    return enabled(cfg) and bid in ensure(cfg, st)['grants']


def consume_building_grant(cfg, st, bid):
    """Called by the caller that has already passed its own build checks."""
    if not building_grant(cfg, st, bid):
        return False
    ensure(cfg, st)['grants'].remove(bid)
    return True


def apply_boost(cfg, st, metric, amount):
    """Multiply a real payout and spend one charge. A charge is never spent on
    a zero value, so an empty sale cannot burn the reward."""
    if not enabled(cfg) or metric not in METRICS or amount <= 0:
        return amount, 0
    data = ensure(cfg, st)
    boost = next((b for b in data['boosts'] if b['metric'] == metric and b['charges'] > 0), None)
    if boost is None:
        return amount, 0
    boost['charges'] -= 1
    if boost['charges'] <= 0:
        data['boosts'].remove(boost)
    return amount * boost['multiplier'], boost['multiplier']


def voucher_cover(cfg, st, cost):
    """What a voucher would cover, without spending it. The caller checks
    affordability with this before committing to the purchase."""
    if not enabled(cfg) or cost <= 0:
        return 0
    voucher = next((v for v in ensure(cfg, st)['vouchers'] if v['remaining'] > 0), None)
    return min(voucher['remaining'], cost) if voucher else 0


def apply_voucher(cfg, st, cost):
    """Pay down one upgrade with the oldest voucher. Returns what is left to
    pay in cash and what the voucher covered."""
    if not enabled(cfg) or cost <= 0:
        return cost, 0
    data = ensure(cfg, st)
    voucher = next((v for v in data['vouchers'] if v['remaining'] > 0), None)
    if voucher is None:
        return cost, 0
    covered = min(voucher['remaining'], cost)
    voucher['remaining'] -= covered
    if voucher['remaining'] <= 0:
        data['vouchers'].remove(voucher)
    return cost - covered, covered


# -------------------------------------------------------------------- actions

def act(cfg, st, body):
    """Validate against a copy: a refused claim never grants or spends."""
    if not enabled(cfg):
        return dict(ok=False, why='Quests are not enabled for this class')
    if not isinstance(body, dict):
        return dict(ok=False, why='Invalid quest action')
    working = copy.deepcopy(st)
    ensure(cfg, working)
    result = _act(cfg, working, body)
    if result['ok']:
        st.clear()
        st.update(working)
    return result


def _act(cfg, st, body):
    if body.get('action') not in ACTIONS:
        return dict(ok=False, why='Unknown quest action')
    data = ensure(cfg, st)
    quest = quests(cfg).get(body.get('questId'))
    if quest is None:
        return dict(ok=False, why='Unknown quest')
    if quest['id'] in data['completed']:
        return dict(ok=False, why='This quest is already complete')
    if not _visible(cfg, st, quest):
        return dict(ok=False, why='This quest is not available yet')
    if not all(o['ready'] for o in _progress(cfg, st, quest)):
        return dict(ok=False, why='Finish the quest goals first')
    for reward in quest.get('rewards', ()):
        _grant(cfg, st, reward)
    data['completed'][quest['id']] = dict(tick=st.get('tick', 0))
    data['recent'].append(dict(id=quest['id'], title=quest.get('title', ''),
                               tick=st.get('tick', 0), rewardText=reward_text(cfg, quest)))
    del data['recent'][:-RECENT_LIMIT]
    return dict(ok=True, kind='quest', questId=quest['id'],
                message=quest.get('title', 'Quest') + ' complete: ' + reward_text(cfg, quest))
