"""Visible worker population; no assignments, costs or gameplay effects."""
from __future__ import annotations

GROWTH_CAP = 20


def enabled(cfg):
    return (cfg.get('businessDesign', {}).get('enabled') is True
            and cfg.get('workforce', {}).get('enabled') is True
            and cfg.get('workforce', {}).get('populationEnabled') is True)


def _count(value):
    return value if type(value) is int and value >= 0 else 0


def _rules(cfg):
    settings = cfg.get('workforce', {})
    base = settings.get('populationWorkersPerBusiness', 5)
    per_level = settings.get('populationWorkersPerProductionLevel', 1)
    return (base if type(base) is int and base >= 0 else 5,
            per_level if type(per_level) is int and per_level >= 0 else 1)


def _entitlement(cfg, level):
    base, per_level = _rules(cfg)
    return min(GROWTH_CAP, base + per_level * (max(1, level) - 1))


def _growth(cfg, st, saved=None):
    saved = saved if isinstance(saved, dict) else {}
    known = {tier['id'] for tier in cfg.get('tiers', [])}
    milestones = {key: dict(productionLevel=max(1, _count(value.get('productionLevel'))),
                            workers=min(GROWTH_CAP, _count(value.get('workers'))))
                  for key, value in saved.items() if key in known and isinstance(value, dict)}
    added = 0
    for building in st.get('b', []):
        ti = building.get('tier')
        if type(ti) is not int or not 0 <= ti < len(cfg.get('tiers', [])):
            continue
        key = cfg['tiers'][ti]['id']
        old = milestones.get(key, dict(productionLevel=1, workers=0))
        level = max(old['productionLevel'], max(1, _count(building.get('lv', 1))))
        workers = max(old['workers'], _entitlement(cfg, level))
        added += workers - old['workers']
        milestones[key] = dict(productionLevel=level, workers=workers)
    return milestones, added


def ensure(cfg, st):
    """Credit permanent growth milestones once, without changing the economy."""
    if not enabled(cfg):
        return {}
    data = st.get('workerPopulation')
    if not isinstance(data, dict):
        teams = st.get('workforce', {}).get('teams', {})
        teams = teams if isinstance(teams, dict) else {}
        legacy = sum(_count(team.get('workers')) for team in teams.values()
                     if isinstance(team, dict))
        milestones, growth_total = _growth(cfg, st)
        data = dict(version=1, total=max(legacy, growth_total),
                    growthMilestones=milestones, legacyImportedWorkers=legacy)
        st['workerPopulation'] = data
    data.setdefault('version', 1)
    milestones, added = _growth(cfg, st, data.get('growthMilestones'))
    data['growthMilestones'] = milestones
    data['total'] = _count(data.get('total')) + added
    # Superseded development-preview assignments have no authority or effects.
    data.pop('allocations', None)
    data.pop('businessIds', None)
    return data


def fixed_total(cfg):
    """workforce.populationFixedTotal pins the shown head count for every
    town (0 or absent: the count grows with the businesses). Growth
    milestones are still recorded, so removing the pin resumes growth."""
    return _count(cfg.get('workforce', {}).get('populationFixedTotal'))


def summary(cfg, st):
    if not enabled(cfg):
        return dict(enabled=False, total=0)
    data = ensure(cfg, st)
    base, per_level = _rules(cfg)
    pinned = fixed_total(cfg)
    return dict(enabled=True, total=pinned or data['total'], purposeEnabled=False, fixedTotal=pinned,
                growth=dict(workersPerBusiness=base,
                            workersPerProductionLevel=per_level,
                            capacityPerBusiness=GROWTH_CAP))
