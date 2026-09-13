"""Upgrade capacity changes immediately; completed goods still require real ticks."""
from __future__ import annotations

import copy
import json

import pytest

import production_economy as E


def town():
    cfg=E.load_config();st=E.new_state(cfg,seed=7)
    st['cash']=10000
    return cfg,st


def replay(cfg,st,count):
    start=st['tick']
    E.advance_class(cfg,E.new_class(cfg),[st],start,start+count)


def building(cfg,st,slot=0):
    return E.payload(cfg,st,E.new_class(cfg),{'paused':False})['buildings'][slot]


@pytest.mark.parametrize('kind,field,before,after,unit',[
    ('production','productionCapacityPerMinute',7,8.75,'goods/min'),
    ('sales','customerCapacityPerMinute',4.55,6.14,'walk-ins/min'),
    ('storage','capacity',180,270,'spaces'),
])
def test_purchase_changes_installed_capacity_without_rewriting_completed_activity(kind,field,before,after,unit):
    cfg,st=town();replay(cfg,st,8)
    previous=building(cfg,st);inventory=copy.deepcopy(st['inventory'])
    preview=previous['upgrades'][kind]
    assert previous[field]==before
    assert (preview['capacityBefore'],preview['capacityAfter'],preview['capacityUnit'])==(before,after,unit)
    assert preview['effect']==f'{before:g} → {after:g} {unit}'
    result=E.buy_upgrade(cfg,st,0,kind)
    assert result['ok']
    current=building(cfg,st)
    assert current[field]==after
    assert current['activity']==previous['activity']
    assert st['inventory']==inventory
    assert result['effect']==preview['effect']


@pytest.mark.parametrize('kind,counter',[
    ('production','unitsProduced'),('sales','unitsSold'),
])
def test_upgrade_increases_completed_goods_over_sustained_real_replay(kind,counter):
    cfg,control=town();replay(cfg,control,8)
    upgraded=copy.deepcopy(control)
    assert E.buy_upgrade(cfg,upgraded,0,kind)['ok']
    before=control['report'][counter]
    # Sixteen full minutes demonstrate an actual increase despite whole-unit
    # rounding in individual 60-second windows. Shelves still have room.
    replay(cfg,control,64);replay(cfg,upgraded,64)
    assert upgraded['report'][counter]-before>control['report'][counter]-before
    assert all(upgraded['inventory'].get(good['id'],0)<E._good_capacity(cfg,upgraded,0,good['id'])
               for good in cfg['tiers'][0]['goods'])


@pytest.mark.parametrize('kind',['production','sales'])
def test_income_rate_increases_in_purchase_response_without_advancing_time(kind):
    cfg,st=town()
    # Give production an outlet; at level 1 the starter farm already supplies
    # all its walk-ins. Customer upgrades instead start with spare production.
    if kind=='production': st['b'][0].update(sales=3,auto=3)
    replay(cfg,st,8)
    before=E.payload(cfg,st,E.new_class(cfg),{'paused':False})
    saved=copy.deepcopy(st)
    preview=before['buildings'][0]['upgrades'][kind]
    result=E.buy_upgrade(cfg,st,0,kind)
    assert result['ok']
    after=E.payload(cfg,st,E.new_class(cfg),{'paused':False})
    assert after['tick']==before['tick']
    assert after['incomePerMinute']>before['incomePerMinute']
    assert after['buildings'][0]['incomePerMinute']>before['buildings'][0]['incomePerMinute']
    assert result['incomeBefore']==preview['incomeBefore']==before['incomePerMinute']
    assert result['incomeAfter']==preview['incomeAfter']==after['incomePerMinute']
    assert result['incomeDelta']==round(after['incomePerMinute']-before['incomePerMinute'],2)
    assert after['cash']==before['cash']-result['cost']
    assert after['earnings']==before['earnings']
    assert after['buildings'][0]['activity']==before['buildings'][0]['activity']
    assert st['inventory']==saved['inventory'] and st['report']==saved['report']
    reloaded=E.migrate_state(cfg,E.State(json.loads(json.dumps(st))))
    assert E.payload(cfg,reloaded,E.new_class(cfg),{'paused':False})['incomePerMinute']==after['incomePerMinute']


def test_capacity_uses_saved_rules_and_batch_quantities_after_reload(monkeypatch):
    cfg,st=town()
    cfg=json.loads(json.dumps(cfg))  # A class keeps its own rules snapshot.
    cfg['global']['tick']=12
    cfg['production']['speedPerLevel']=40
    cfg['production']['customerPerLevel']=20
    cfg['tiers'][0]['goods'][0]['quantity']=2
    st=E.migrate_state(cfg,E.State(json.loads(json.dumps(st))))
    monkeypatch.setattr(E,'load_config',lambda: pytest.fail('Use the class rules already supplied.'))
    shop=building(cfg,st)
    assert shop['productionCapacityPerMinute']==13.75
    assert shop['upgrades']['production']['capacityAfter']==19.25
    assert shop['upgrades']['sales']['capacityBefore']==5.69
    assert shop['upgrades']['sales']['capacityAfter']==6.83
    assert E.buy_upgrade(cfg,st,0,'production')['ok']
    assert building(cfg,st)['productionCapacityPerMinute']==19.25


def test_capacity_remains_visible_when_ingredients_limit_actual_production():
    cfg,st=town()
    st['tierOf'].append(2);st['b'].append(E._building(2,lv=12))
    shop=building(cfg,st,1)
    assert shop['productionCapacityPerMinute']==26.25
    assert shop['productionPerMinute']<shop['productionCapacityPerMinute']


def test_full_shelves_explain_why_more_production_cannot_complete():
    cfg,st=town();st['b'][0]['reserve']=True
    st['inventory']={good['id']:E._good_capacity(cfg,st,0,good['id']) for good in cfg['tiers'][0]['goods']}
    result=E.buy_upgrade(cfg,st,0,'production')
    assert result['ok'] and result['capacityAfter']>result['capacityBefore']
    assert 'shelves are full' in result['consequence']
    replay(cfg,st,8)
    assert building(cfg,st)['activity']['producedUnits']==0
    assert 'Walk-in sales paused' in E.upgrade_preview(cfg,st,0,'sales')['consequence']


@pytest.mark.parametrize('operations_enabled',[True,False])
def test_production_upgrade_has_isolated_income_potential_despite_current_customer_limit(operations_enabled):
    cfg,st=town()
    if not operations_enabled: cfg.pop('businessDesign')
    saved=copy.deepcopy(st)
    preview=E.upgrade_preview(cfg,st,0,'production')
    assert preview['incomeDelta']==0
    assert (preview['optimizedIncomeBefore'],preview['optimizedIncomeAfter'],
            preview['optimizedIncomeDelta'])==(24,30,6)
    assert st==saved, 'Estimating fully sold output must not create goods or receipts.'
    receipt=E.buy_upgrade(cfg,st,0,'production')
    assert receipt['ok'] and receipt['optimizedIncomeDelta']==6
    assert st['cash']==saved['cash']-receipt['cost']
    assert st['inventory']==saved['inventory'] and st['report']==saved['report']


@pytest.mark.parametrize('constraint',['paused','reserved','full','ingredients','cash'])
def test_optimized_recipe_income_ignores_current_operating_constraints(constraint):
    cfg,st=town()
    st['tierOf'].append(2);st['b'].append(E._building(2))
    E.business_operations.ensure(cfg,st)
    b=st['b'][1]
    if constraint=='paused': b.update(paused=True,processing=False)
    elif constraint=='reserved': b['reserve']=True
    elif constraint=='full':
        st['inventory'].update({g['id']:E._good_capacity(cfg,st,1,g['id'])
                                for g in cfg['tiers'][2]['goods']})
    elif constraint=='ingredients':
        st['b'][0]['paused']=True
        st['inventory'].clear()
        st['productionBlocked']={'roastery_pastries':dict(reason='ingredient',goodId='farm_eggs')}
    else: st['cash']=0
    saved=copy.deepcopy(st)
    preview=E.upgrade_preview(cfg,st,1,'production')
    assert (preview['optimizedIncomeBefore'],preview['optimizedIncomeAfter'],
            preview['optimizedIncomeDelta'])==(54,67.5,13.5)
    assert st==saved


def test_optimized_income_includes_only_unlocked_recipes():
    cfg,st=town()
    st['tierOf'].append(3);st['b'].append(E._building(3))
    locked=E.upgrade_preview(cfg,st,1,'production')
    assert not E.business_progression.product_unlocked(cfg,st,'garage_custom_mods')
    assert (locked['optimizedIncomeBefore'],locked['optimizedIncomeAfter'],
            locked['optimizedIncomeDelta'])==(56,70,14)
    st['businessProgression']['quests']['garage-signature']=dict(completed=True)
    unlocked=E.upgrade_preview(cfg,st,1,'production')
    assert (unlocked['optimizedIncomeBefore'],unlocked['optimizedIncomeAfter'],
            unlocked['optimizedIncomeDelta'])==(80,100,20)


def test_optimized_income_uses_saved_tick_batch_and_specialty_rules(monkeypatch):
    cfg,st=town()
    cfg=json.loads(json.dumps(cfg))
    cfg['global']['tick']=12
    cfg['production']['speedPerLevel']=40
    cfg['tiers'][0]['goods'][0]['quantity']=2
    st['b'][0].update(lv=3,focus='supply')
    st=E.migrate_state(cfg,E.State(json.loads(json.dumps(st))))
    monkeypatch.setattr(E,'load_config',lambda: pytest.fail('Use the saved class rules.'))
    preview=E.upgrade_preview(cfg,st,0,'production')
    # Tomatoes: 31 -> 39; eggs and honey: 20.5 -> 24.5 YM/min each.
    assert (preview['optimizedIncomeBefore'],preview['optimizedIncomeAfter'],
            preview['optimizedIncomeDelta'])==(72,88,16)


def test_optimized_income_is_realizable_when_farm_has_enough_customers():
    cfg,control=town()
    control['b'][0].update(sales=12,auto=12)
    upgraded=copy.deepcopy(control)
    preview=E.upgrade_preview(cfg,control,0,'production')
    assert E.buy_upgrade(cfg,upgraded,0,'production')['ok']
    before=control['report']['retailEarned']
    replay(cfg,control,80);replay(cfg,upgraded,80)
    minutes=80*cfg['global']['tick']/60
    assert (control['report']['retailEarned']-before)/minutes==preview['optimizedIncomeBefore']
    assert (upgraded['report']['retailEarned']-before)/minutes==preview['optimizedIncomeAfter']
    assert (upgraded['report']['retailEarned']-control['report']['retailEarned'])/minutes==preview['optimizedIncomeDelta']


def test_every_default_business_production_level_adds_positive_income_potential():
    cfg,st=town()
    st['tierOf']=list(range(len(cfg['tiers'])))
    st['b']=[E._building(tier) for tier in st['tierOf']]
    assert len(st['b'])==15
    for slot,b in enumerate(st['b']):
        for level in range(1,cfg['production']['maxLevel']):
            b['lv']=level
            assert E.upgrade_cost(cfg,st,slot,'production') is not None
            preview=E.upgrade_preview(cfg,st,slot,'production')
            assert preview['optimizedIncomeAfter']>preview['optimizedIncomeBefore']
            assert preview['optimizedIncomeDelta']>0, (cfg['tiers'][b['tier']]['id'],level)


def test_optimized_paused_income_retains_installed_staff_speed():
    cfg,st=town()
    cfg['workforce']['populationEnabled'] = False  # Existing class snapshots retain crew effects.
    # Permanent trained crew remains installed while a business is paused.
    import workforce
    st['workforce']['teams']['farm']=dict(workforce._empty_team(),
        hires=1,trainers=1,workers=10,nodes=['orientation'],
        allocation=dict(production=10,sales=0,efficiency=0))
    running=E.upgrade_preview(cfg,st,0,'production')
    st['b'][0]['paused']=True
    paused=E.upgrade_preview(cfg,st,0,'production')
    assert (paused['optimizedIncomeBefore'],paused['optimizedIncomeAfter'],
            paused['optimizedIncomeDelta'])==(28.8,34.8,6)
    for key in ('optimizedIncomeBefore','optimizedIncomeAfter','optimizedIncomeDelta'):
        assert paused[key]==running[key]
