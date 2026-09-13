"""Recurring sales conserve goods and remain safe across absences and saves."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_economy as E


@pytest.fixture
def town():
    cfg=E.load_config()
    return cfg,E.new_state(cfg,seed=37)


def replay(cfg,st,ticks):
    begin=st['tick']
    E.advance_class(cfg,E.new_class(cfg),[st],begin,begin+ticks)


def own(st,*tiers):
    st['tierOf']=list(tiers)
    st['b']=[E._building(ti) for ti in tiers]


def sign(cfg,st,customer='corner_grocer',slot=0):
    result=E.manage_customer_contract(cfg,st,slot,'accept',customer_id=customer)
    assert result['ok'],result
    return next(c for c in st['customerContracts']['active'] if c['slot']==slot)


def order(st,gid,qty,committed=False):
    st['offers'][0]=dict(id='chosen-delivery',name='Chosen delivery',requirements=[dict(goodId=gid,quantity=qty)],
                         reward=40,materials=0,customer=None,committed=committed)


def test_choices_slots_and_chain_unlocks(town):
    cfg,st=town
    view=E.customer_contract_payload(cfg,st)
    assert view['slots']==2 and view['maxSlots']==4
    assert view['nextUnlock']==dict(buildings=3,slots=3)
    starter=[c for c in view['customers'] if c['available']]
    assert len(starter)==3
    assert len({c['requirements'][0]['goodId'] for c in starter})==3
    assert len({c['intervalSeconds'] for c in starter})==3
    assert not E.manage_customer_contract(cfg,st,2,'accept',customer_id='corner_grocer')['ok']
    own(st,2)
    cafe=next(c for c in E.customer_contract_payload(cfg,st)['customers'] if c['id']=='copper_cafe')
    assert not cafe['available'] and 'Farm' in cafe['unlockText']
    assert not E.manage_customer_contract(cfg,st,0,'accept',customer_id='copper_cafe')['ok']
    own(st,0,1,2)
    assert E.customer_contract_payload(cfg,st)['slots']==3
    sign(cfg,st,'copper_cafe',2)
    own(st,0,1,2,3,4,5)
    view=E.customer_contract_payload(cfg,st)
    assert view['slots']==4 and view['nextUnlock'] is None


def test_first_shipment_waits_full_interval_and_debits_real_goods(town):
    cfg,st=town
    contract=sign(cfg,st)
    assert contract['reward']==15 and st['customerContracts']['earned']==0
    replay(cfg,st,contract['intervalTicks']-1)
    assert st['customerContracts']['deliveries']==0
    before=st['inventory'].get('farm_tomatoes',0)
    replay(cfg,st,1)
    assert st['customerContracts']['deliveries']==1
    assert st['inventory']['farm_tomatoes']==before+1-6
    assert st['report']['customerEarned']==15
    assert st['report']['customerDeliveries']==1


def test_recurring_inventory_and_money_are_conserved_without_legacy_rewards(town):
    cfg,st=town
    sign(cfg,st)
    sign(cfg,st,'sunrise_diner',1)
    before=copy.deepcopy(st['cStats']),copy.deepcopy(st['checklist'])
    replay(cfg,st,120)
    customers=st['customerContracts'];report=st['report'];goods=E.catalog(cfg)
    stock=sum(qty*goods[gid]['unitPrice'] for gid,qty in st['inventory'].items())
    assert customers['deliveries']>5
    assert st['cash']+st['businessOperations']['totalOperatingCosts']==report['retailEarned']+customers['earned']
    assert report['produced']==stock+report['retailEarned']+customers['earned']*4//5
    assert report['customerEarned']==customers['earned']
    assert report['customerDeliveries']==customers['deliveries']
    assert (st['cStats'],st['checklist'])==before
    assert st.get('regularDeliveries',0)==0
    assert all(type(qty) is int and qty>=0 for qty in st['inventory'].values())


def test_bundle_shortage_is_atomic_and_late_shipment_creates_no_backlog(town):
    cfg,st=town
    own(st,0,1,2)
    contract=sign(cfg,st,'copper_cafe')
    st['inventory']={'roastery_espresso_shots':4,'roastery_pastries':1}
    before=copy.deepcopy(st)
    due=contract['nextDeliveryTick']+1000
    E._tick_customer_contracts(cfg,st,due)
    assert st==before
    st['inventory']['roastery_pastries']=2
    E._tick_customer_contracts(cfg,st,due)
    assert st['inventory']=={'roastery_espresso_shots':0,'roastery_pastries':0}
    assert st['customerContracts']['deliveries']==1
    assert contract['nextDeliveryTick']==due+contract['intervalTicks']
    after=copy.deepcopy(st)
    E._tick_customer_contracts(cfg,st,due)
    assert st==after


def test_committed_manual_delivery_keeps_priority_over_regular(town):
    cfg,st=town
    contract=sign(cfg,st)
    order(st,'farm_tomatoes',6,committed=True)
    st['inventory']['farm_tomatoes']=6
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick'])
    assert st['customerContracts']['earned']==0
    assert st['inventory']['farm_tomatoes']==6
    view=E.payload(cfg,st,E.new_class(cfg),{'paused':False})
    assert view['contracts']['offers'][0]['canFulfill']
    assert view['customerContracts']['active'][0]['requirements'][0]['reserved']==0
    assert E.fulfill_order(cfg,st,0,'chosen-delivery')['ok']
    assert st['inventory']['farm_tomatoes']==0


def test_uncommitted_delivery_and_clear_stock_respect_regular_reservation(town):
    cfg,st=town
    contract=sign(cfg,st)
    order(st,'farm_tomatoes',6)
    st['inventory']['farm_tomatoes']=6
    before=copy.deepcopy(st)
    assert not E.fulfill_order(cfg,st,0,'chosen-delivery')['ok']
    assert not E.sell_one(cfg,st,0)['ok']
    assert st==before
    view=E.payload(cfg,st,E.new_class(cfg),{'paused':False})
    assert not view['contracts']['offers'][0]['canFulfill']
    assert E.manage_customer_contract(cfg,st,0,'pause',contract_id=contract['id'])['ok']
    assert E.fulfill_order(cfg,st,0,'chosen-delivery')['ok']


def test_new_manual_commit_can_take_priority_and_regular_waits(town):
    cfg,st=town
    sign(cfg,st)
    order(st,'farm_tomatoes',6)
    st['inventory']['farm_tomatoes']=6
    assert E.customer_contract_payload(cfg,st)['active'][0]['requirements'][0]['owned']==6
    assert E.commit_order(cfg,st,0,'chosen-delivery',True)['ok']
    assert E.customer_contract_payload(cfg,st)['active'][0]['requirements'][0]['owned']==0
    assert E.fulfill_order(cfg,st,0,'chosen-delivery')['ok']


def test_regular_holds_leave_recipe_capacity_and_do_not_block_processing(town):
    cfg,st=town
    own(st,0,1,2)
    sign(cfg,st,'sunrise_diner')
    sign(cfg,st,'copper_cafe',1)
    st['b'][2]['sales']=12
    replay(cfg,st,160)
    history=st['customerContracts']['history']
    assert history['copper_cafe']['deliveries']>0
    assert st['report']['customerEarned']>0
    assert E.chain_reservations(cfg,st)['farm_eggs']>0
    for ti in st['tierOf']:
        slot=st['tierOf'].index(ti)
        for good in cfg['tiers'][ti]['goods']:
            assert st['inventory'].get(good['id'],0)<=E._good_capacity(cfg,st,slot,good['id'])


def test_shared_goods_are_reserved_once_and_shelf_capacity_is_bounded(town):
    cfg,st=town
    contract=sign(cfg,st)
    # Future catalog customers may share products. Allocation must still work.
    second=copy.deepcopy(contract)
    second.update(id='second-regular',customerId='second-customer',slot=1)
    st['customerContracts']['active'].append(second)
    st['inventory']['farm_tomatoes']=8
    view=E.customer_contract_payload(cfg,st)
    assert [c['requirements'][0]['reserved'] for c in view['active']]==[6,2]
    order(st,'farm_tomatoes',58,committed=True)
    targets,_=E._customer_stock_plan(cfg,st)
    assert targets['farm_tomatoes']==2


def test_pause_release_and_switch_keep_cash_history_and_release_goods(town):
    cfg,st=town
    original=sign(cfg,st)
    replay(cfg,st,original['intervalTicks'])
    earned=st['customerContracts']['earned'];cash=st['cash']
    assert earned>0
    assert E.manage_customer_contract(cfg,st,0,'pause',contract_id=original['id'])['ok']
    assert E._customer_reservations(cfg,st)=={}
    replay(cfg,st,100)
    assert st['customerContracts']['earned']==earned
    assert E.manage_customer_contract(cfg,st,0,'resume',contract_id=original['id'])['ok']
    assert original['nextDeliveryTick']==st['tick']+original['intervalTicks']
    assert E.manage_customer_contract(cfg,st,0,'switch',customer_id='sunrise_diner',contract_id=original['id'])['ok']
    replacement=st['customerContracts']['active'][0]
    assert replacement['id']!=original['id']
    assert replacement['nextDeliveryTick']==st['tick']+replacement['intervalTicks']
    assert 'farm_tomatoes' not in E._customer_reservations(cfg,st)
    assert st['customerContracts']['history']['corner_grocer']['earned']==earned
    assert st['cash']>=cash
    assert E.manage_customer_contract(cfg,st,0,'release',contract_id=replacement['id'])['ok']
    assert not st['customerContracts']['active']
    assert st['customerContracts']['earned']==earned
    back=sign(cfg,st)
    assert back['earned']==earned and back['deliveries']==1
    assert back['id'] not in (original['id'],replacement['id'])


@pytest.mark.parametrize('kwargs',[
    dict(slot=True,action='accept',customer_id='corner_grocer'),
    dict(slot=-1,action='accept',customer_id='corner_grocer'),
    dict(slot=3,action='accept',customer_id='corner_grocer'),
    dict(slot=0,action=[],customer_id='corner_grocer'),
    dict(slot=0,action='accept',customer_id=[]),
    dict(slot=0,action='accept',customer_id='missing'),
    dict(slot=0,action='release',contract_id='stale'),
    dict(slot=0,action='pause',contract_id=[]),
])
def test_bad_requests_do_not_mutate(town,kwargs):
    cfg,st=town
    before=copy.deepcopy(st)
    assert not E.manage_customer_contract(cfg,st,**kwargs)['ok']
    assert st==before


def test_duplicate_customers_and_stale_actions_cannot_change_replacement(town):
    cfg,st=town
    first=sign(cfg,st)
    assert not E.manage_customer_contract(cfg,st,1,'accept',customer_id='corner_grocer')['ok']
    assert E.manage_customer_contract(cfg,st,0,'switch',customer_id='sunrise_diner',contract_id=first['id'])['ok']
    before=copy.deepcopy(st)
    for action in ('pause','resume','release','switch'):
        assert not E.manage_customer_contract(cfg,st,0,action,customer_id='corner_grocer',contract_id=first['id'])['ok']
        assert st==before


def test_json_reload_and_segmented_replay_do_not_duplicate_payments(town):
    cfg,continuous=town
    sign(cfg,continuous)
    sign(cfg,continuous,'honey_collective',1)
    segmented=E.State(json.loads(json.dumps(continuous)))
    replay(cfg,continuous,250)
    for count in (7,19,41,63,120):
        replay(cfg,segmented,count)
        segmented=E.State(json.loads(json.dumps(segmented)))
    assert continuous==segmented
    before=copy.deepcopy(segmented)
    replay(cfg,segmented,0)
    assert segmented==before


def test_offline_cap_does_not_pay_skipped_shipments_on_return(town):
    cfg,long_absence=town
    sign(cfg,long_absence)
    capped=copy.deepcopy(long_absence)
    cap=int(cfg['runtime']['offlineHours']*E.ticks_per_hour(cfg))
    replay(cfg,capped,cap)
    replay(cfg,long_absence,cap*3)
    assert long_absence['customerContracts']['earned']==capped['customerContracts']['earned']
    assert long_absence['customerContracts']['deliveries']==capped['customerContracts']['deliveries']
    assert long_absence['cash']==capped['cash']
    due_capped=capped['customerContracts']['active'][0]['nextDeliveryTick']-capped['tick']
    due_long=long_absence['customerContracts']['active'][0]['nextDeliveryTick']-long_absence['tick']
    assert due_long==due_capped
    earned=long_absence['customerContracts']['earned']
    E.on_login(cfg,long_absence)
    replay(cfg,long_absence,due_long-1)
    assert long_absence['customerContracts']['earned']==earned
    replay(cfg,long_absence,1)
    assert long_absence['customerContracts']['earned']==earned+15


def test_old_v4_saves_gain_empty_customers_without_reset_and_migrate_idempotently(town):
    cfg,st=town
    replay(cfg,st,40)
    st['regularDeliveries']=3
    st.pop('townProjects',None)
    # Represent a pre-project v4 board, preserving its promised delivery.
    st['offers'][2]=E._make_order(cfg,st,1)
    st['offers'][2].update(customer='breakfast',channelLabel='Breakfast regulars',committed=True)
    st['customerContracts']={}
    del st['customerContracts']
    del st['report']['customerEarned']
    del st['report']['customerDeliveries']
    previous=copy.deepcopy(st)
    migrated=E.migrate_state(cfg,st)
    assert migrated['customerContracts']==dict(serial=0,earned=0,deliveries=0,active=[],history={})
    assert migrated['report']['customerEarned']==migrated['report']['customerDeliveries']==0
    for field in ('cash','inventory','b','offers','regularDeliveries','tick'):
        assert migrated[field]==previous[field]
    before=copy.deepcopy(migrated)
    assert E.migrate_state(cfg,migrated)==before


def test_larger_offer_requires_three_shipments_and_never_changes_terms_automatically(town):
    cfg,st=town
    contract=sign(cfg,st)
    assert E.customer_contract_payload(cfg,st)['active'][0]['largerOffer'] is None
    replay(cfg,st,contract['intervalTicks']*2)
    before=copy.deepcopy(st)
    assert not E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=contract['id'])['ok']
    assert not E.manage_customer_contract(cfg,st,0,'downgrade',contract_id=contract['id'])['ok']
    assert st==before
    replay(cfg,st,contract['intervalTicks'])
    active=E.customer_contract_payload(cfg,st)['active'][0]
    assert not active['largerOrder']
    assert active['largerOffer']==dict(reward=33,intervalSeconds=120,requirements=[
        dict(goodId='farm_tomatoes',name='Tomatoes',buildingId='farm',quantity=12)])
    replay(cfg,st,contract['intervalTicks']*4)
    assert not contract['largerOrder']
    assert contract['reward']==15
    assert contract['requirements']==[dict(goodId='farm_tomatoes',quantity=6)]


def test_resizing_rotates_id_preserves_pause_and_history_without_spending_or_paying(town):
    cfg,st=town
    contract=sign(cfg,st)
    replay(cfg,st,contract['intervalTicks']*3)
    first_id=contract['id']
    assert E.manage_customer_contract(cfg,st,0,'pause',contract_id=first_id)['ok']
    before=copy.deepcopy(st)
    resized=E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=first_id)
    assert resized['ok'] and resized['contractId']!=first_id
    large_id=contract['id']
    assert contract['largerOrder'] and contract['paused']
    assert contract['reward']==33 and contract['requirements'][0]['quantity']==12
    assert contract['nextDeliveryTick']==st['tick']+contract['intervalTicks']
    assert not E.customer_contract_payload(cfg,st)['active'][0]['largerOffer']
    assert E._customer_reservations(cfg,st)=={}
    for field in ('cash','inventory','report','cStats','checklist','offers'):
        assert st[field]==before[field]
    for field in ('earned','deliveries','history'):
        assert st['customerContracts'][field]==before['customerContracts'][field]
    after=copy.deepcopy(st)
    assert not E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=large_id)['ok']
    for action in ('pause','resume','release','upgrade','downgrade','switch'):
        assert not E.manage_customer_contract(cfg,st,0,action,customer_id='sunrise_diner',contract_id=first_id)['ok']
        assert st==after
    smaller=E.manage_customer_contract(cfg,st,0,'downgrade',contract_id=large_id)
    assert smaller['ok'] and smaller['contractId'] not in (first_id,large_id)
    assert not contract['largerOrder'] and contract['paused']
    assert contract['reward']==15 and contract['requirements'][0]['quantity']==6
    for field in ('cash','inventory','report','cStats','checklist','offers'):
        assert st[field]==before[field]
    assert E.customer_contract_payload(cfg,st)['active'][0]['largerOffer']['reward']==33


def test_larger_shipments_require_double_goods_and_only_pay_after_full_interval(town):
    cfg,st=town
    contract=sign(cfg,st)
    replay(cfg,st,contract['intervalTicks']*3)
    assert E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=contract['id'])['ok']
    st['inventory']['farm_tomatoes']=12
    before=copy.deepcopy(st)
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick']-1)
    assert st==before
    st['inventory']['farm_tomatoes']=11
    due=contract['nextDeliveryTick']
    short=copy.deepcopy(st)
    E._tick_customer_contracts(cfg,st,due+100)
    assert st==short
    st['inventory']['farm_tomatoes']=12
    E._tick_customer_contracts(cfg,st,due+100)
    assert st['inventory']['farm_tomatoes']==0
    assert st['cash']==before['cash']+33
    assert st['report']['customerEarned']==before['report']['customerEarned']+33
    assert st['report']['customerDeliveries']==before['report']['customerDeliveries']+1
    assert contract['nextDeliveryTick']==due+100+contract['intervalTicks']
    paid=copy.deepcopy(st)
    E._tick_customer_contracts(cfg,st,due+100)
    assert st==paid


def test_larger_regular_still_waits_for_manual_reservations_and_can_return_to_small(town):
    cfg,st=town
    contract=sign(cfg,st)
    replay(cfg,st,contract['intervalTicks']*3)
    assert E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=contract['id'])['ok']
    order(st,'farm_tomatoes',54,committed=True)
    st['inventory']['farm_tomatoes']=60
    before=copy.deepcopy(st)
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick'])
    assert st==before
    assert E.customer_contract_payload(cfg,st)['active'][0]['requirements'][0]['reserved']==6
    assert E.manage_customer_contract(cfg,st,0,'downgrade',contract_id=contract['id'])['ok']
    E._tick_customer_contracts(cfg,st,contract['nextDeliveryTick'])
    assert st['inventory']['farm_tomatoes']==54
    assert st['cash']==before['cash']+15


def test_larger_choice_survives_reload_and_rejoin_returns_to_base_with_offer(town):
    cfg,st=town
    contract=sign(cfg,st)
    replay(cfg,st,contract['intervalTicks']*3)
    assert E.manage_customer_contract(cfg,st,0,'upgrade',contract_id=contract['id'])['ok']
    restored=E.State(json.loads(json.dumps(st)))
    assert E.migrate_state(cfg,restored)==st
    replay(cfg,st,100)
    for count in (13,31,56):
        replay(cfg,restored,count)
        restored=E.State(json.loads(json.dumps(restored)))
    assert restored==st
    earned=st['customerContracts']['earned']
    assert E.manage_customer_contract(cfg,st,0,'release',contract_id=contract['id'])['ok']
    back=sign(cfg,st)
    assert not back['largerOrder'] and back['reward']==15
    assert back['deliveries']>=3
    assert E.customer_contract_payload(cfg,st)['active'][0]['largerOffer']['reward']==33
    assert st['customerContracts']['earned']==earned


def test_migration_defaults_existing_customer_size_without_changing_terms(town):
    cfg,st=town
    contract=sign(cfg,st)
    replay(cfg,st,contract['intervalTicks']*3)
    del contract['largerOrder']
    before=copy.deepcopy(st)
    migrated=E.migrate_state(cfg,st)
    assert not migrated['customerContracts']['active'][0]['largerOrder']
    expected=copy.deepcopy(before)
    expected['customerContracts']['active'][0]['largerOrder']=False
    assert migrated==expected
