"""Player-visible consequences and reservation accounting, using temporary saves."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
import production_economy as E
import game_api as A
from test_production_api import town, edit, state


def setup(roastery=False):
    cfg=E.load_config();st=E.new_state(cfg)
    if roastery:
        st['b'].append(E._building(2));st['tierOf'].append(2)
    return cfg,st


def run(cfg,st,n):
    world=E.new_class(cfg,st['tick']+n)
    E.advance_class(cfg,world,[st],st['tick'],st['tick']+n)


def snapshot(cfg,st):
    return E.payload(cfg,st,E.new_class(cfg,st['tick']),{'paused':False})


def test_upgrade_explains_bottleneck_and_art_milestone():
    cfg,st=setup();up=snapshot(cfg,st)['buildings'][0]['upgrades']
    assert up['production']['incomeDelta']==0
    assert up['sales']['incomeDelta']==pytest.approx(5.46)
    assert up['storage']['incomeDelta']==0
    st['cash']=10000
    E.buy_upgrade(cfg,st,0,'production');E.buy_upgrade(cfg,st,0,'production')
    b=snapshot(cfg,st)['buildings'][0]
    assert b['artLevel']==3 and b['focusUnlocked']


@pytest.mark.parametrize('kind', ['lv', 'sales', 'storage'])
@pytest.mark.parametrize('level, expected', [(1, 1), (2, 2), (3, 3), (5, 3), (6, 6)])
def test_art_tracks_highest_upgrade_without_changing_buildings(kind, level, expected):
    cfg,st=setup()
    st['b'][0][kind]=level
    before=copy.deepcopy(st['b'])
    assert snapshot(cfg,st)['buildings'][0]['artLevel']==expected
    assert st['b']==before


def test_commit_saves_goods_while_other_goods_keep_selling():
    cfg,st=setup();order=st['offers'][0]
    assert E.commit_order(cfg,st,0,order['id'],True)['ok']
    run(cfg,st,80)
    assert st['inventory']['farm_tomatoes']>=order['requirements'][0]['quantity']
    assert st['cash']>0 and not st['b'][0]['reserve']
    before=st['cash'];assert E.fulfill_order(cfg,st,0,order['id'])['ok']
    assert st['cash']==before+order['reward'] and not E.order_reservations(st)


def test_committed_ingredients_survive_processing_and_clearance():
    cfg,st=setup(True)
    order=st['offers'][0]
    order['requirements']=[dict(goodId='farm_eggs',quantity=4),dict(goodId='farm_honey',quantity=2)]
    assert E.commit_order(cfg,st,0,order['id'],True)['ok']
    run(cfg,st,120)
    required={n['goodId']:n['quantity'] for n in order['requirements']}
    assert all(st['inventory'][gid]>=qty for gid,qty in required.items())
    E.sell_one(cfg,st,0)
    assert all(st['inventory'][gid]>=qty for gid,qty in required.items())
    assert E.fulfill_order(cfg,st,0,order['id'])['ok']


def test_conflicting_orders_cannot_double_spend_or_overcommit_shelf():
    cfg,st=setup();a=st['offers'][0];b=st['offers'][1]
    a['requirements']=[dict(goodId='farm_tomatoes',quantity=40)]
    b['requirements']=[dict(goodId='farm_tomatoes',quantity=40)]
    assert E.commit_order(cfg,st,0,a['id'],True)['ok']
    before=copy.deepcopy(st)
    assert not E.commit_order(cfg,st,1,b['id'],True)['ok']
    assert st==before
    st['inventory']['farm_tomatoes']=40
    assert not E.fulfill_order(cfg,st,1,b['id'])['ok']
    assert E.fulfill_order(cfg,st,0,a['id'])['ok']
    assert st['inventory']['farm_tomatoes']==0


def test_two_orders_with_same_good_can_both_finish_after_replay():
    cfg,st=setup()
    for i in (0,1):
        st['offers'][i]['requirements']=[dict(goodId='farm_tomatoes',quantity=10)]
        assert E.commit_order(cfg,st,i,st['offers'][i]['id'],True)['ok']
    st=E.State(json.loads(json.dumps(st)));run(cfg,st,60)
    for i in (0,1): assert E.fulfill_order(cfg,st,i,st['offers'][i]['id'])['ok']


def test_replacements_are_immediate_free_and_release_goods_after_reload():
    cfg,st=setup();o=st['offers'][0]
    E.commit_order(cfg,st,0,o['id'],True)
    assert E.replace_order(cfg,st,0,o['id'])['ok'] and not E.order_reservations(st)
    st=E.State(json.loads(json.dumps(st)));o=st['offers'][0]
    st['offers'][0]['replaceAfterTick']=100000  # Old saves lose their cooldown.
    cash,materials,tick=st['cash'],st['materials'],st['tick']
    for _ in range(100):
        assert E.replace_order(cfg,st,0,st['offers'][0]['id'])['ok']
    assert (st['cash'],st['materials'],st['tick'])==(cash,materials,tick)
    assert not E.commit_order(cfg,st,0,o['id'],True)['ok']


def test_order_roll_odds_complexity_payout_and_shelf_capacity():
    cfg,st=setup(True);st['b'].append(E._building(1));st['tierOf'].append(1)
    counts={r['id']:0 for r in E.ORDER_ROLLS};examples={}
    for _ in range(10000):
        o=E._make_order(cfg,st,0);counts[o['rarity']]+=1;examples[o['rarity']]=o
        ids=[n['goodId'] for n in o['requirements']]
        assert len(ids)==len(set(ids))
        for n in o['requirements']:
            slot=st['tierOf'].index(E.catalog(cfg)[n['goodId']]['tier'])
            assert 0<n['quantity']<=E._good_capacity(cfg,st,slot,n['goodId'])
        assert o['reward']==E.jsround(o['retailValue']*o['rewardPercent']/100)
    for rarity in E.ORDER_ROLLS:
        assert abs(counts[rarity['id']]/100-rarity['chance'])<2
    assert [len(examples[r]['requirements']) for r in ('standard','large','rare','jackpot')]==[1,3,4,5]
    assert examples['jackpot']['rewardPercent']>examples['rare']['rewardPercent']>examples['large']['rewardPercent']>125


def test_order_roll_sequence_survives_json_reload_and_does_not_change_inventory():
    cfg,st=setup(True);other=E.State(json.loads(json.dumps(st)))
    before=copy.deepcopy(st['inventory'])
    for i in range(100):
        slot=i%2
        E.replace_order(cfg,st,slot,st['offers'][slot]['id'])
        other=E.State(json.loads(json.dumps(other)))
        E.replace_order(cfg,other,slot,other['offers'][slot]['id'])
        assert st['offers']==other['offers']
    assert st['inventory']==before and st['cash']==0


def test_jackpot_requires_every_item_and_pays_once():
    cfg,st=setup(True)
    for _ in range(1000):
        o=st['offers'][0]
        if o.get('rarity')=='jackpot':break
        E.replace_order(cfg,st,0,o['id'])
    assert o['rarity']=='jackpot'
    for n in o['requirements']:st['inventory'][n['goodId']]=n['quantity']
    last=o['requirements'][-1];st['inventory'][last['goodId']]-=1
    before=copy.deepcopy(st)
    assert not E.fulfill_order(cfg,st,0,o['id'])['ok'] and st==before
    st['inventory'][last['goodId']]+=1
    assert E.fulfill_order(cfg,st,0,o['id'])['ok'] and st['cash']==o['reward']
    assert not E.fulfill_order(cfg,st,0,o['id'])['ok']


def test_specialty_changes_actual_production_and_has_a_cost_in_output():
    cfg,st=setup()
    assert not E.set_focus(cfg,st,0,'supply')['ok']
    st['b'][0]['lv']=3;st['b'][0]['reserve']=True
    st['cash']=1000  # Both plans can pay for every batch while stock is held.
    balanced=copy.deepcopy(st)
    assert E.set_focus(cfg,st,0,'supply')['ok']
    run(cfg,st,16);run(cfg,balanced,16)
    assert st['inventory']['farm_eggs']>balanced['inventory']['farm_eggs']
    assert st['inventory']['farm_tomatoes']<balanced['inventory']['farm_tomatoes']
    assert E.set_focus(cfg,st,0,'balanced')['ok']


def test_cafe_project_unlocks_once_and_increases_actual_walk_in_demand():
    cfg,st=setup(True)
    cfg['businessDesign'].pop('connectedProgression', None)
    st['townProjects'].pop('groupProgress', None)
    st['offers'][2] = E._project_order(cfg, st)  # Legacy fixed-project class.
    snapshot(cfg,st)  # Existing roastery satisfies the two construction steps.
    o=st['offers'][2]
    for n in o['requirements']:st['inventory'][n['goodId']]=n['quantity']
    assert E.fulfill_order(cfg,st,2,o['id'])['ok']
    assert not E.fulfill_order(cfg,st,2,o['id'])['ok']
    assert st['regularDeliveries']==3
    assert E.customer_demand(cfg,st,st['b'][1])==7800
    b=snapshot(cfg,st)['buildings'][1];assert b['regularBonus']==20
    # Abundant supplies isolate demand, so this verifies actual cash, not a label.
    st['inventory']={g['id']:40 for ti in st['tierOf'] for g in cfg['tiers'][ti]['goods']}
    other=copy.deepcopy(st);other['regularDeliveries']=0
    for _ in range(20): E._retail(cfg,st);E._retail(cfg,other)
    assert st['cash']>other['cash']


def test_breakfast_upgrade_changes_town_recipe_and_survives_reload():
    cfg,st=setup(True);b=st['b'][1];good=cfg['tiers'][2]['goods'][1]
    st['breakfastEvent']=dict(stage=5,upgrade='coffee')
    assert E.product_speed(cfg,st,b,good)==125
    st=E.State(json.loads(json.dumps(st)))
    assert E.product_speed(cfg,st,st['b'][1],good)==125
    assert E.product_speed(cfg,st,st['b'][1],cfg['tiers'][2]['goods'][2])==100


def test_materials_neither_discount_buildings_nor_pay_out():
    cfg,st=setup();st['materials']=1
    for ti in (1,2,14):
        with_material=E.expansion_quote(cfg,st,ti)
        no_material=copy.deepcopy(st);no_material['materials']=0
        assert E.expansion_quote(cfg,no_material,ti)['cost']==with_material['cost']==cfg['tiers'][ti]['baseCost']
    for _ in range(20):
        o=E._make_order(cfg,st,1)
        value=sum(n['quantity']*E.catalog(cfg)[n['goodId']]['unitPrice'] for n in o['requirements'])
        assert o['materials']==0


def test_retail_is_a_real_alternative_to_required_deliveries():
    cfg,st=setup(True);st['b'].append(E._building(1));st['tierOf'].append(1)
    st['checklist'].update(lv25=True,auto=True,quiz=True)
    assert not E.gate_open(cfg,st)
    st['report']['unitsSold']=100
    assert E.gate_open(cfg,st) and st['cStats']['done']==0


def test_order_reservations_replay_identically_in_chunks():
    cfg,st=setup(True)
    E.commit_order(cfg,st,2,st['offers'][2]['id'],True)
    once=copy.deepcopy(st);chunked=copy.deepcopy(st)
    run(cfg,once,200)
    for n in (3,17,80,100):
        chunked=E.State(json.loads(json.dumps(chunked)));run(cfg,chunked,n)
    assert once==chunked


def test_api_commits_persist_and_concurrent_delivery_pays_once(town):
    now,_,players=town;token=players[0]['token'];o=state(token)['contracts']['offers'][0]
    body=dict(token=token,offerIndex=0,orderId=o['id'])
    result=A.econ_commit_order(dict(body,committed=True))
    assert result['contracts']['offers'][0]['committed']
    # Wait for the actual shipment, independent of the randomly rolled size
    # and the new operating-cost budget. Reservation must persist on reload.
    for _ in range(30):
        now[0]+=60;A._book_cache.clear();before=state(token)
        saved=before['contracts']['offers'][0]
        assert saved['id']==o['id'] and saved['committed']
        if saved['canFulfill']:break
    assert saved['canFulfill'], 'A saved starter order must remain attainable'
    def deliver(_):
        try:return A.econ_fulfill_order(body)
        except A.ApiError:return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(deliver,range(2)))
    assert sum(r is not None for r in results)==1
    assert state(token)['cash']==before['cash']+o['reward']
    with pytest.raises(A.ApiError):A.econ_commit_order(dict(body,committed=True))


def test_api_focus_is_validated_and_fake_allocation_is_rejected(town):
    _,_,players=town;token=players[0]['token']
    with pytest.raises(A.ApiError):A.econ_focus(dict(token=token,slot=0,focus='supply'))
    def prepare(cfg,st):st['b'][0]['lv']=3;st['licenceGrandfathered']=True
    edit(token,prepare)
    assert A.econ_focus(dict(token=token,slot=0,focus='supply'))['buildings'][0]['focus']=='supply'
    cash=state(token)['cash']
    with pytest.raises(A.ApiError):A.econ_keep(dict(token=token,percent=50))
    assert state(token)['cash']==cash


def test_old_material_rewards_retire_in_place_without_rerolling_orders():
    cfg, st = setup()
    st['materials'] = 23
    E.offer_contracts(cfg, st, st['tick'])
    for offer in st['offers']:
        offer['materials'] = 9
    st['offers'][1]['channelLabel'] = 'Building supplies'
    st['offers'][0].update(inTransit=True, committed=True)
    before = copy.deepcopy(st)
    loaded = E.migrate_state(cfg, st)
    assert loaded['materials'] == 0
    assert all(offer['materials'] == 0 for offer in loaded['offers'])
    assert loaded['offers'][1]['channelLabel'] == 'Sector delivery'
    for key in ('cash', 'book', 'inventory', 'b', 'tierOf', 'tick'):
        assert loaded[key] == before[key]
    assert [o['id'] for o in loaded['offers']] == [o['id'] for o in before['offers']]
    assert loaded['offers'][0]['inTransit'] and loaded['offers'][0]['committed']
    assert E.migrate_state(cfg, copy.deepcopy(loaded)) == loaded
