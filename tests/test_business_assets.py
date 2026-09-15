"""Catalog-only assets cannot mint ownership or change the economy."""
import copy
import business_assets as B
import crafting as C
import production_economy as E


def test_asset_catalog_has_no_economy_side_effects():
    cfg = E.load_config()
    st = E.new_state(cfg, seed=19)
    before = copy.deepcopy(st)
    assets = C.payload(cfg, st)['businessAssets']
    assert len(assets) == len({a['id'] for a in assets}) == 45
    assert st == before
    for business, _, _ in B.BUSINESSES:
        rows = [a for a in assets if a['businessId'] == business]
        assert [a['assetType'] for a in rows] == ['tangible', 'tangible', 'intangible']
        assert all(a['recordedValue'] is None and a['usefulLife'] is None for a in rows)
    C.ensure(st)
    before = copy.deepcopy(st)
    result = C.act(cfg, st, dict(action='craft', itemId=assets[0]['id'], requestId='asset-no-free-craft', revision=st['crafting']['revision']))
    assert not result['ok']
    assert st == before
