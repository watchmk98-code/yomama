"""rules_tables: lookups derived from cfg are shared only inside one replay."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import business_progression as P
import production_economy as E
import rules_tables


def test_outside_a_pin_every_call_rebuilds_from_the_current_rules():
    cfg = E.load_config()
    first = E.catalog(cfg)
    assert E.catalog(cfg) is not first
    cfg['tiers'][0]['goods'][0]['unitPrice'] += 1
    assert E.catalog(cfg)['farm_tomatoes']['unitPrice'] == first['farm_tomatoes']['unitPrice'] + 1
    assert P.product_unlocked(cfg, E.new_state(cfg, 0), 'farm_honey')
    assert rules_tables._pinned is None


def test_inside_a_pin_one_table_per_cfg_object_and_the_pin_is_released_on_error():
    cfg = E.load_config()
    other = copy.deepcopy(cfg)
    with rules_tables.pinned(cfg):
        assert E.catalog(cfg) is E.catalog(cfg) and E.catalog(cfg) == E._build_catalog(cfg)
        assert P._catalog(cfg) is P._catalog(cfg) and P._catalog(cfg) == P._build_catalog(cfg)
        assert E.catalog(other) is not E.catalog(other), 'another cfg object is not pinned'
    assert rules_tables._pinned is None
    try:
        with rules_tables.pinned(cfg):
            raise RuntimeError('replay failed')
    except RuntimeError:
        pass
    assert rules_tables._pinned is None


def test_advance_class_pins_its_rules_only_while_it_runs(monkeypatch):
    cfg = E.load_config()
    st = E.new_state(cfg, 0)
    cls = E.new_class(cfg, 100, E.PriceBook(cfg))
    pins = []
    real = E.player_tick
    monkeypatch.setattr(E, 'player_tick', lambda *a: (pins.append(bool(rules_tables._pinned) and rules_tables._pinned[0] is cfg), real(*a)))
    E.advance_class(cfg, cls, [st], 0, 3)
    assert pins == [True, True, True] and st['tick'] == 3
    assert rules_tables._pinned is None


def test_progression_ensure_fast_path_returns_the_finished_record_unchanged():
    cfg = E.load_config()
    st = E.new_state(cfg, 0)
    p = P.ensure(cfg, st)
    before = copy.deepcopy(p)
    assert P.ensure(cfg, st) is p and p == before
    del p['equipmentValue']   # an older record: the full normalization runs again
    assert P.ensure(cfg, st) is p and p == before
    disconnected = copy.deepcopy(cfg)
    disconnected['businessDesign']['connectedProgression'] = False
    assert P.ensure(disconnected, st) is p and p == before


def test_signature_lookup_matches_the_rules_it_replaces():
    cfg = E.load_config()
    table = P._signature_buildings(cfg)
    assert table == {t['goods'][-1]['id']: t['id'] for t in cfg['tiers']}
    assert 'farm_tomatoes' not in table and table['garage_custom_mods'] == 'garage'
