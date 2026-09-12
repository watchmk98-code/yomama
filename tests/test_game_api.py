"""SQLite integration: authoritative replay, persistence, transactions, and access."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
import game_api as A
import economy as E


@pytest.fixture
def world(tmp_path, monkeypatch):
    # These cases preserve the original v3 reference contract. The current
    # production model is covered separately in test_production_api.py.
    monkeypatch.setattr(A,'economy',E)
    monkeypatch.setattr(A,'_startup_config',E.load_config())
    monkeypatch.setattr(A,'DB_PATH',tmp_path/'game.db')
    monkeypatch.setattr(A,'AUTO_LOGIN',False)
    now=[2000000000.0]
    monkeypatch.setattr(A.time,'time',lambda:now[0])
    A._book_cache.clear();A.init_db()
    teacher=A.create_session({})
    players=[A.join(dict(code=teacher['code'],name=name,pin='1234')) for name in ('ALICE','BOB')]
    return now,teacher,players


def edit_player(token, apply):
    with A.connect() as conn:
        p=A._player_by_token(conn,token);s=A._session_of(conn,p['code']);cfg=A.econ_config(s)
        st=A._load_state(p,cfg,s);apply(cfg,st);A._save_state(conn,p['id'],cfg,st)


def test_class_advances_every_player_and_persists_pressure(world):
    now,teacher,players=world
    now[0]+=E.load_config()['global']['tick']*2000
    first=A.econ_state({'token':[players[0]['token']]})
    second=A.econ_state({'token':[players[1]['token']]})
    assert first['tick']==second['tick']==2000
    assert first['buildings'][0]['price']==second['buildings'][0]['price']
    assert first['cash']>0 and second['cash']>0
    before=second['buildings'][0]['price']
    receipt=A.econ_sell(dict(token=players[0]['token'],slot=0))['receipt']
    assert receipt['gross']-receipt['tax']==receipt['net']
    assert receipt['premiumSalePct']==E.load_config()['fun']['premiumSalePct']
    A._book_cache.clear()  # simulate process restart: pressure must not be cached-only
    after=A.econ_state({'token':[players[1]['token']]})
    assert after['buildings'][0]['price']<=before
    with A.connect() as conn:
        s=A._session_of(conn,teacher['code']);assert json.loads(s['pressure'])[0]>0
        assert isinstance(s['income_per_hour'],int)
        rows=list(conn.execute('SELECT econ,econ_meta FROM players'))
        assert all('tick' not in json.loads(r['econ']) for r in rows)
        assert all(json.loads(r['econ_meta'])['tick']==2000 for r in rows)


def test_concurrent_sell_cannot_pay_twice(world):
    now,teacher,players=world;token=players[0]['token'];now[0]+=1500
    A.econ_state({'token':[token]})
    def sell(_):
        try: return A.econ_sell(dict(token=token,slot=0))['receipt']['net']
        except A.ApiError as e: assert e.status==400;return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(sell,range(2)))
    assert sum(r is not None for r in results)==1
    assert A.econ_state({'token':[token]})['cash']==next(r for r in results if r is not None)


def test_noncontiguous_frontier_api_validation_and_rollback(world):
    now,teacher,players=world;token=players[0]['token']
    def prepare(cfg,st):st['cash']=100000;st['b'][0]['lv']=cfg['global']['gradLv']
    edit_player(token,prepare)
    with pytest.raises(A.ApiError) as caught:A.econ_expand(dict(token=token,tier=10))
    assert caught.value.details['frontier']==[1,2,3]
    result=A.econ_expand(dict(token=token,tier=3));assert result['build']['tier']==3
    assert [f['tier'] for f in result['frontier']]==[1,2,4]
    with pytest.raises(A.ApiError):A.econ_level(dict(token=token,slot=-1))
    with pytest.raises(A.ApiError):A.econ_level(dict(token=token,slot='0'))
    assert A.econ_state({'token':[token]})['cash']==result['cash']


def test_contract_rng_survives_restart_and_no_backdated_join_income(world):
    now,teacher,players=world;token=players[0]['token'];now[0]+=15
    first=A.econ_state({'token':[token]});offers=first['contracts']['offers'];assert len(offers)==3
    A._book_cache.clear();assert A.econ_state({'token':[token]})['contracts']['offers']==offers
    A.econ_accept_contract(dict(token=token,offerIndex=0))
    now[0]+=15
    after=A.econ_state({'token':[token]});assert after['contracts']['active'][0]['delivered']==1
    now[0]+=10000
    late=A.join(dict(code=teacher['code'],name='LATE',pin='5678'))
    result=A.econ_state({'token':[late['token']]})
    assert result['warehouseStored']==0 and result['cash']==0


def test_teacher_event_auth_and_family_prices(world):
    now,teacher,players=world;token=players[0]['token']
    with pytest.raises(A.ApiError):A.teacher_event(dict(family='F',mag=1.4,holdMin=60,headline='Spoof'))
    with pytest.raises(A.ApiError):A.teacher_econ({})
    A.teacher_event(dict(teacher_token=teacher['teacher_token'],family='F',mag=1.4,holdMin=60,headline='<Test> demand rises'))
    now[0]+=30
    a=A.econ_state({'token':[players[0]['token']]});b=A.econ_state({'token':[players[1]['token']]})
    assert a['activeEvents'][0]['multiplier']>1
    assert a['activeEvents'][0]['headline']=='<Test> demand rises'
    assert a['buildings'][0]['price']==b['buildings'][0]['price']
    assert A.teacher_econ({'teacher_token':[teacher['teacher_token']]})['count']==2


def test_gate_and_keep_are_server_enforced(world):
    now,teacher,players=world;token=players[0]['token']
    with pytest.raises(A.ApiError):A.econ_keep(dict(token=token,percent=50))
    with pytest.raises(A.ApiError):A.trade_equity(dict(token=token,symbol='AAPL',side='buy',shares=1))
    quiz=A._load_quiz();A.econ_quiz(dict(token=token,answers=[q['answer'] for q in quiz['questions']]))
    def prepare(cfg,st):
        st['tierOf']=list(range(cfg['global']['gateTier']));st['b']=[dict(lv=cfg['gate']['levelNeeded'],auto=cfg['global']['a1Mult'],tier=i) for i in st['tierOf']]
        st['checklist'].update(lv25=True,auto=True,goodSales=cfg['gate']['goodSalesNeeded'])
    edit_player(token,prepare)
    assert A.econ_keep(dict(token=token,percent=35))['keepPercent']==35
    with pytest.raises(A.ApiError):A.econ_keep(dict(token=token,percent=101))


def test_overnight_report_counts_classmate_replay_and_collect_is_noop(world):
    now,teacher,players=world;token=players[0]['token']
    A.econ_login(dict(token=token));now[0]+=3*3600
    A.econ_state({'token':[players[1]['token']]})
    login=A.econ_login(dict(token=token));report=login['overnightReport']
    with A.connect() as conn:
        cfg=A.econ_config(A._session_of(conn,teacher['code']))
    expected=sum(e['real'] for e in E.event_schedule(cfg,720))
    assert report['produced']==720 and report['events']==expected
    assert A.econ_login(dict(token=token))['overnightReport'] is None
    assert A.econ_state({'token':[token]})['cash']==login['cash']


def test_cap_and_paused_clock(world):
    now,teacher,players=world
    # A smaller configured cap exercises exactly the same batching path.
    with A.connect() as conn:
        s=A._session_of(conn,teacher['code']);cfg=A.econ_config(s)
        cfg['runtime']['maxCatchupDays']=100/E.ticks_per_day(cfg)
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',(json.dumps(cfg),s['code']))
    now[0]+=300*15
    first=A.econ_state({'token':[players[0]['token']]});assert first['tick']==100 and first['behind']
    second=A.econ_state({'token':[players[0]['token']]});assert second['tick']==200 and second['behind']
    third=A.econ_state({'token':[players[0]['token']]});assert third['tick']==300 and not third['behind']
    A.teacher(dict(teacher_token=teacher['teacher_token'],action='pause'));now[0]+=3600
    assert A.econ_state({'token':[players[0]['token']]})['tick']==300


def test_legacy_migration_retains_value_and_paid_build_queue(world):
    now,teacher,players=world;token=players[0]['token']
    legacy=dict(cash=1000,book=100000,taxPaid=100,tier=4,lv=67,auto=4,pend={'0':55,'1':30,'2':15},
                tick=0,build=dict(finishTick=100,**{'from':4}),queue=[5],lastLogin=0,catchupUntil=-1,
                checklist=dict(lv25=True,auto=True,goodSales=3,quiz=False),keepPercent=None)
    with A.connect() as conn:
        conn.execute('UPDATE sessions SET econ_config=? WHERE code=?',(json.dumps({'global':{'seed':7}}),teacher['code']))
        conn.execute('UPDATE players SET econ=?,econ_meta=? WHERE token=?',(json.dumps(legacy),'{}',token))
    payload=A.econ_state({'token':[token]})
    assert payload['cash']==1000 and payload['netWorth']==101100
    assert payload['buildingsOwned']==1 and payload['buildings'][0]['tier']==4 and payload['buildings'][0]['lv']==50
    assert payload['build']['tier']==5 and payload['queue'][0]['tier']==6
    with A.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ledger WHERE kind='v3_migration'").fetchone()[0]==1
    A.econ_state({'token':[token]})
    with A.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ledger WHERE kind='v3_migration'").fetchone()[0]==1
