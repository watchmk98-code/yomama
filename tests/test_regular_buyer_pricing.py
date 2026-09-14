"""Regular shipments trade discounted prices for reliable recurring volume."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import production_economy as E


@pytest.fixture
def town():
    cfg=E.load_config()
    return cfg,E.new_state(cfg,seed=91)


def sign(cfg,st,customer='corner_grocer',slot=0):
    result=E.manage_customer_contract(cfg,st,slot,'accept',customer_id=customer)
    assert result['ok'],result
    return next(c for c in st['customerContracts']['active'] if c['slot']==slot)


def test_every_catalog_buyer_pays_less_than_retail(town):
    cfg,st=town
    goods=E.catalog(cfg)
    offers=E.customer_contract_payload(cfg,st)['customers']
    assert len(offers)==len(E.CUSTOMER_CATALOG)
    for offer in offers:
        retail=sum(goods[n['goodId']]['unitPrice']*n['quantity'] for n in offer['requirements'])
        assert isinstance(offer['reward'],int)
        assert 0<offer['reward']<retail
        assert abs(offer['reward']-retail*0.9)<=0.5


@pytest.mark.parametrize('retail,reward',[(1,1),(2,1),(4,3),(5,4),(9,8),(10,9),(16,14),(32,29)])
def test_whole_ym_rounding_keeps_small_bundles_discounted(retail,reward):
    cfg=dict(tiers=[dict(id='sample',goods=[dict(id='sample_good',unitPrice=1)])])
    assert E._customer_reward(cfg,[dict(goodId='sample_good',quantity=retail)])==reward


def test_new_contract_pays_discount_only_when_its_goods_ship(town):
    cfg,st=town
    before_cash=st['cash']
    contract=sign(cfg,st)
    assert contract['reward']==11
    assert st['cash']==before_cash
    st['inventory']['farm_tomatoes']=6
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick']-1)
    assert st['cash']==before_cash
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick'])
    assert st['cash']==before_cash+11
    assert st['inventory']['farm_tomatoes']==0
    assert contract['earned']==st['customerContracts']['earned']==st['report']['customerEarned']==11


def test_larger_offer_and_contract_reprice_full_bundle_without_volume_premium(town):
    cfg,st=town
    contract=sign(cfg,st,'sunrise_diner')
    assert contract['requirements']==[dict(goodId='farm_eggs',quantity=4)]
    assert contract['reward']==14  # Retail 16, rounded from 14.4.
    contract['deliveries']=3
    offered=E.customer_contract_payload(cfg,st)['active'][0]['largerOffer']
    assert offered['reward']==29  # Retail 32, rounded from 28.8, not 2 x rounded 14.
    assert offered['requirements'][0]['quantity']==8
    cash=st['cash']
    assert E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=contract['id'])['ok']
    assert contract['reward']==offered['reward']
    assert contract['requirements']==[dict(goodId='farm_eggs',quantity=8)]
    assert st['cash']==cash
    assert E.manage_customer_contract(cfg,st,0,'downgrade',contract_id=contract['id'])['ok']
    assert contract['reward']==14
    assert contract['requirements']==[dict(goodId='farm_eggs',quantity=4)]
    assert st['cash']==cash


def test_saved_contracts_reprice_in_place_without_changing_terms_or_history(town):
    cfg,st=town
    small=sign(cfg,st)
    large=sign(cfg,st,'sunrise_diner',1)
    # Saved terms may differ from today's catalog and must keep their quantities
    # and interval, including a paused contract and a late larger shipment.
    small.update(paused=True,reward=18,requirements=[dict(goodId='farm_tomatoes',quantity=7)],
                 intervalTicks=13,intervalSeconds=195,nextDeliveryTick=27,deliveries=4,earned=73)
    large.update(largerOrder=True,reward=44,requirements=[dict(goodId='farm_eggs',quantity=8)],
                 intervalTicks=17,intervalSeconds=255,nextDeliveryTick=0,deliveries=9,earned=231)
    st['customerContracts'].update(earned=304,deliveries=13,history=dict(
        corner_grocer=dict(earned=73,deliveries=4),sunrise_diner=dict(earned=231,deliveries=9)))
    st['report'].update(customerEarned=304,customerDeliveries=13)
    st['cash']+=304
    expected=copy.deepcopy(st)
    expected['customerContracts']['active'][0]['reward']=13
    expected['customerContracts']['active'][1]['reward']=29
    saved=E.State(json.loads(json.dumps(st)))
    migrated=E.migrate_state(cfg,saved)
    assert migrated==expected
    assert E.migrate_state(cfg,migrated)==expected
    reloaded=E.State(json.loads(json.dumps(migrated)))
    assert E.migrate_state(cfg,reloaded)==expected


def test_repriced_saved_shipment_adds_only_new_discounted_income(town):
    cfg,st=town
    contract=sign(cfg,st)
    contract.update(reward=15,deliveries=2,earned=30)
    st['customerContracts'].update(earned=30,deliveries=2,
                                  history=dict(corner_grocer=dict(earned=30,deliveries=2)))
    st['report'].update(customerEarned=30,customerDeliveries=2)
    st['inventory']['farm_tomatoes']=6
    cash=st['cash']
    st=E.migrate_state(cfg,st)
    contract=st['customerContracts']['active'][0]
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick'])
    assert st['cash']==cash+11
    assert contract['earned']==st['customerContracts']['earned']==st['report']['customerEarned']==41
    assert st['customerContracts']['history']['corner_grocer']==dict(earned=41,deliveries=3)
