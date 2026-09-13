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
