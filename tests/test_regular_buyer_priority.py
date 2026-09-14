"""The next regular shipment gets finished goods before manual orders."""
from __future__ import annotations

import copy

import pytest

import production_economy as E


@pytest.fixture
def town():
    cfg=E.load_config()
    st=E.new_state(cfg,seed=191)
    st['tierOf']=[0,2]
    st['b']=[E._building(0),E._building(2)]
    st['cash']=1000
    st['businessProgression']['grandfathered']=['farm','roastery']
    return cfg,st


def sign(cfg,st,customer='sunrise_diner'):
    result=E.manage_customer_contract(cfg,st,0,'accept',customer_id=customer)
    assert result['ok'],result
    return st['customerContracts']['active'][0]


@pytest.mark.parametrize('starting_eggs',[3,4])
def test_same_tick_products_are_independent_and_regular_eggs_stay_reserved(town,starting_eggs):
    cfg,st=town
    sign(cfg,st)
    st['inventory'].update(farm_eggs=starting_eggs,farm_honey=1)
    # One egg and one pastry batch become ready in this same production tick.
    st['productionWork'].update(farm_eggs=100,roastery_pastries=300)
    E._produce(cfg,st)
    assert st['inventory']['farm_eggs']==starting_eggs+1
    assert st['inventory']['roastery_pastries']==1
    assert st['inventory']['farm_honey']==1
    active=E.customer_contract_payload(cfg,st)['active'][0]
    assert active['requirements'][0]['reserved']==4


def test_pausing_regular_releases_its_goods_to_manual_orders(town):
    cfg,st=town
    contract=sign(cfg,st)
    st['inventory'].update(farm_eggs=4,farm_honey=1)
    st['productionWork']['roastery_pastries']=300
    E._produce(cfg,st)
    assert st['inventory']['roastery_pastries']==1
    st['offers'][0]=dict(id='spare-eggs',name='Spare eggs',committed=False,
                         requirements=[dict(goodId='farm_eggs',quantity=4)],reward=30,materials=0)
    assert not E.fulfill_order(cfg,st,0,'spare-eggs')['ok']
    assert E.manage_customer_contract(cfg,st,0,'pause',contract_id=contract['id'])['ok']
    assert E.fulfill_order(cfg,st,0,'spare-eggs')['ok']
    assert st['inventory']['farm_eggs']==0
    assert st['inventory']['roastery_pastries']==1
    assert E._customer_reservations(cfg,st)=={}


def test_new_manual_commit_leaves_room_for_regular_even_with_no_current_stock(town):
    cfg,st=town
    sign(cfg,st)
    capacity=E._good_capacity(cfg,st,0,'farm_eggs')
    st['offers'][0]=dict(id='egg-order',name='Egg order',committed=False,
                         requirements=[dict(goodId='farm_eggs',quantity=capacity-3)],reward=100,materials=0)
    before=copy.deepcopy(st)
    assert not E.commit_order(cfg,st,0,'egg-order',True)['ok']
    assert st==before
    st['offers'][0]['requirements'][0]['quantity']=capacity-4
    assert E.commit_order(cfg,st,0,'egg-order',True)['ok']


def test_regular_and_saved_manual_order_debit_each_unit_only_once(town):
    cfg,st=town
    contract=sign(cfg,st)
    st['offers'][0]=dict(id='egg-order',name='Egg order',committed=True,
                         requirements=[dict(goodId='farm_eggs',quantity=3)],reward=30,materials=0)
    st['inventory']['farm_eggs']=7
    cash=st['cash']
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick'])
    assert st['inventory']['farm_eggs']==3
    assert st['cash']==cash+contract['reward']
    # A regular's next bundle keeps first claim after its current bundle ships.
    blocked=copy.deepcopy(st)
    assert not E.fulfill_order(cfg,st,0,'egg-order')['ok']
    assert st==blocked
    st['inventory']['farm_eggs']+=4
    assert E.fulfill_order(cfg,st,0,'egg-order')['ok']
    assert st['inventory']['farm_eggs']==4
    assert st['cash']==cash+contract['reward']+30


def test_finished_regular_shipment_leaves_an_unrelated_saved_product_untouched(town):
    cfg,st=town
    contract=sign(cfg,st,'copper_cafe')
    capacity=E._good_capacity(cfg,st,0,'farm_eggs')
    st['offers'][0]=dict(id='all-eggs',name='All eggs',committed=True,
                         requirements=[dict(goodId='farm_eggs',quantity=capacity)],reward=100,materials=0)
    st['inventory'].update(farm_eggs=capacity,farm_honey=10)
    for building in st['b']:
        building['reserve']=True
    E.advance_class(cfg,E.new_class(cfg),[st],st['tick'],st['tick']+contract['intervalTicks']*3)
    assert contract['deliveries']>=1
    assert contract['earned']>=contract['reward']
    assert st['offers'][0]['id']=='all-eggs' and st['offers'][0]['committed']
    assert st['inventory']['farm_eggs']==capacity
    assert all(quantity>=0 for quantity in st['inventory'].values())


def test_fast_production_never_debits_unrelated_saved_goods(town):
    cfg,st=town
    sign(cfg,st,'copper_cafe')
    st['offers'][0]=dict(id='saved-eggs',name='Saved eggs',committed=True,
                         requirements=[dict(goodId='farm_eggs',quantity=20)],reward=100,materials=0)
    st['inventory'].update(farm_eggs=20,farm_honey=10,roastery_espresso_shots=4)
    st['productionWork']['roastery_pastries']=4000
    E._produce(cfg,st)
    assert st['inventory']['roastery_pastries']==10
    assert st['inventory']['farm_eggs']==20
    assert st['inventory']['farm_honey']==10
