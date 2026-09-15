"""Play complete event paths and check conservation, replay, and persistence."""
import copy
import pytest
import breakfast_event as B


def call(st, now, action, **kw):
    result = B.act(st, now, dict(action=action, **kw))
    assert result['ok'], result
    return result


@pytest.mark.parametrize('order', ['coffee', 'pastry'])
@pytest.mark.parametrize('upgrade', ['coffee', 'pastry'])
def test_complete_four_orders_without_free_stock_or_town_spending(order, upgrade):
    st = dict(materials=7, cash=5000, inventory={'town_goods': 20})
    call(st, 0, 'start')
    now = 0
    for order_id in ('first', order, 'mixed', 'final'):
        if order_id == 'final':
            call(st, now, 'upgrade', recipe=upgrade)
        p = B.payload(st, now)
        target = next(o for o in p['orders'] if o['id'] == order_id)
        for name, qty in target['needs'].items():
            while st['breakfastEvent']['stock'][name] < qty:
                call(st, now, 'make', recipe=name)
                while st['breakfastEvent']['active'] or st['breakfastEvent']['queued']:
                    now += 15
                    B.advance(st, now)
                    assert now <= 900
        call(st, now, 'deliver', orderId=order_id)
        assert not B.act(st, now, dict(action='deliver', orderId=order_id))['ok']
    assert st['materials'] == 7
    assert st['cash'] == 5000 and st['inventory'] == {'town_goods': 20}
    assert B.payload(st, now)['status'] == 'done'
    assert st['breakfastEvent']['coins'] == 0
    assert '+25%' in B.payload(st, now)['townPerk']
    assert 300 <= now <= 600
    saved = copy.deepcopy(st)
    call(st, now + 86400, 'start')
    B.advance(st, now + 86400)
    assert saved == st
    print(order, upgrade, 'completion seconds:', now)


def test_queue_charges_on_start_catches_up_and_cannot_cancel_active():
    st = dict(materials=0)
    call(st, 0, 'start')
    call(st, 0, 'make', recipe='coffee')
    assert st['breakfastEvent']['stock']['beans'] == 2
    call(st, 0, 'make', recipe='pastry')
    e = st['breakfastEvent']
    assert e['stock']['honey'] == 1
    queued = e['queued']['id']
    assert not B.act(st, 0, dict(action='make', recipe='coffee'))['ok']
    B.advance(st, 30)
    assert e['stock']['coffee'] == 2 and e['stock']['honey'] == 0
    assert not B.act(st, 30, dict(action='cancel', jobId=queued))['ok']
    B.advance(st, 100000000)
    assert e['stock'] == dict(beans=12, eggs=12, honey=12, coffee=2, pastry=1)
    assert not e['active'] and not e['queued']


def test_bulk_replay_matches_every_tick_and_waiting_queue_can_cancel():
    st = dict(materials=0)
    call(st, 0, 'start')
    call(st, 0, 'make', recipe='pastry')
    call(st, 0, 'make', recipe='pastry')
    bulk = copy.deepcopy(st)
    for now in range(15, 121, 15):
        B.advance(st, now)
    B.advance(bulk, 120)
    assert st == bulk
    call(st, 120, 'make', recipe='pastry')
    call(st, 120, 'make', recipe='pastry')
    before = copy.deepcopy(st['breakfastEvent']['stock'])
    call(st, 120, 'cancel', jobId=st['breakfastEvent']['queued']['id'])
    assert before == st['breakfastEvent']['stock']


def test_bad_requests_cannot_buy_upgrade_or_fabricate_delivery():
    st = dict(materials=0)
    call(st, 0, 'start')
    for request in (dict(action='upgrade', recipe='coffee'), dict(action='deliver', orderId='final'),
                    dict(action='make', recipe=[]), dict(action='cancel', jobId=True),
                    dict(action='give_coins'), dict(action='deliver', orderId='first')):
        before = copy.deepcopy(st)
        assert not B.act(st, 0, request)['ok']
        assert st == before
