"""Production cadence only; average rates, prices and demand stay unchanged."""
from __future__ import annotations


PROFILES = (
    dict(id='food', sector='F', label='Food', shortLabel='Food · Small batches',
         batchMultiplier=1,
         description='Small batches arrive frequently. Useful for filling small orders as goods become ready.'),
    dict(id='industry', sector='I', label='Industry', shortLabel='Industry · Larger batches',
         batchMultiplier=2,
         description='Usually makes two batches together, taking twice the time and production cost. '
                     'A smaller batch can finish when cash or shelf space is tight.'),
    dict(id='energy', sector='E', label='Energy / Tech', shortLabel='Energy · Staggered output',
         batchMultiplier=1,
         description='Products start at different times so goods arrive more evenly. '
                     'A short, one-time startup delay does not change average production speed.'),
)


def enabled(cfg):
    return cfg.get('production', {}).get('sectorRhythms', True) is True


def profile(cfg, building):
    if not enabled(cfg):
        return None
    sector = cfg['tiers'][building['tier']]['family']
    return next((dict(row) for row in PROFILES if row['sector'] == sector), None)


def batch_multiplier(cfg, building):
    return 2 if enabled(cfg) and cfg['tiers'][building['tier']]['family'] == 'I' else 1


def delay_tick(cfg, state, building, good):
    """Delay initial active work once; never grant or discard earned work."""
    tier = cfg['tiers'][building['tier']]
    if not enabled(cfg) or tier['family'] != 'E':
        return False
    phases = state.setdefault('productionPhase', {})
    gid = good['id']
    if gid not in phases:
        index = next(i for i, product in enumerate(tier['goods']) if product['id'] == gid)
        phases[gid] = min(index, max(0, good['cycleTicks'] - 1))
    if phases[gid] > 0:
        phases[gid] -= 1
        return True
    return False


def payload(cfg):
    return dict(enabled=enabled(cfg), profiles=[dict(row) for row in PROFILES] if enabled(cfg) else [])
