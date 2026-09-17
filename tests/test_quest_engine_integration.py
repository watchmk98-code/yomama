"""Quests observe the real economy and spend real rewards through its own paths."""
from __future__ import annotations

import copy

import production_economy as economy
import quest_engine as quests


def played(ticks=600, seed=11, cash=5000, configure=True):
    cfg = quests.configure(economy.load_config()) if configure else economy.load_config()
    state = economy.new_state(cfg, seed=seed)
    state['cash'] = cash
    for tick in range(1, ticks):
        state['tick'] = tick
        economy._produce(cfg, state, tick)
        economy._retail(cfg, state, tick)
    return cfg, state


def test_real_production_and_retail_reach_the_counters():
    cfg, state = played()
    counters = state['questEngine']['counters']
    assert counters['produce:farm_tomatoes'] > 0
    assert counters['sell:farm_tomatoes'] > 0
    assert counters['sell:business:farm'] == counters['sell:any']
    assert counters['sell:source:walkIns'] == counters['sell:any']


def test_the_engine_stays_out_of_a_class_that_did_not_opt_in():
    cfg, state = played(configure=False)
    assert not quests.enabled(cfg)
    assert 'questEngine' not in state


def test_a_claim_pays_through_the_players_own_cash():
    cfg, state = played()
    before = state['cash']
    result = quests.act(cfg, state, dict(action='quest_claim', questId='first-crop'))
    assert result['ok'], result
    assert state['cash'] >= before + 40


def test_a_granted_building_makes_the_real_expansion_quote_free():
    cfg, state = played()
    assert economy.expansion_quote(cfg, state, 1)['cost'] == cfg['tiers'][1]['baseCost']
    quests._grant(cfg, state, dict(type='grant_building', businessId='fish_stall'))
    quote = economy.expansion_quote(cfg, state, 1)
    assert quote['cost'] == 0 and quote['constructionGrant']
    assert quote['fundedValue'] == cfg['tiers'][1]['baseCost']


def test_a_voucher_pays_a_real_upgrade_and_the_asset_still_books_at_full_value():
    cfg, state = played()
    cost = economy.upgrade_cost(cfg, state, 0, 'production')
    quests._grant(cfg, state, dict(type='upgrade_voucher', amount=cost))
    cash, book = state['cash'], state['book']
    result = economy.buy_upgrade(cfg, state, 0, 'production')
    assert result['ok'] and result['voucherPaid'] == cost
    assert state['cash'] == cash                      # the voucher paid, not the player
    assert state['book'] == book + cost               # the upgrade is still worth its price
    assert state['questEngine']['counters']['act:upgrade'] == 1


def test_a_boost_multiplies_a_real_order_payout_once_per_charge():
    cfg, state = played()
    quests._grant(cfg, state, dict(type='boost', metric='order_payout', multiplier=2, charges=1))
    paid, multiplier = quests.apply_boost(cfg, state, 'order_payout', 250)
    assert (paid, multiplier) == (500, 2)
    assert quests.apply_boost(cfg, state, 'order_payout', 250) == (250, 0)


def test_opening_a_business_is_observed_through_the_real_expand_path():
    cfg, state = played(cash=100000)
    economy.expand(cfg, state, 1, state['tick'])
    assert state['questEngine']['counters']['act:open_business'] == 1


def test_an_unaffordable_upgrade_never_spends_the_voucher():
    cfg, state = played(cash=0)
    state['cash'] = 0
    cost = economy.upgrade_cost(cfg, state, 0, 'production')
    quests._grant(cfg, state, dict(type='upgrade_voucher', amount=max(1, cost // 4)))
    before = copy.deepcopy(state['questEngine']['vouchers'])
    assert not economy.buy_upgrade(cfg, state, 0, 'production')['ok']
    assert state['questEngine']['vouchers'] == before


def test_regular_buyer_decisions_are_observed_through_the_real_path():
    cfg, state = played(cash=50000)
    customer = next(c for c in economy._customer_catalog(cfg, state) if c['available'])
    assert economy.manage_customer_contract(cfg, state, 0, 'accept', customer_id=customer['id'])['ok']
    assert state['questEngine']['counters']['act:set_regular'] == 1
    contract = state['customerContracts']['active'][0]
    contract['deliveries'] = 3
    assert economy.manage_customer_contract(cfg, state, 0, 'upgrade', contract_id=contract['id'])['ok']
    assert state['questEngine']['counters']['act:upgrade_regular'] == 1


def test_every_counter_the_content_asks_for_is_one_the_engine_records():
    cfg, _ = played(ticks=2)
    recorded = {'produce', 'sell', 'deliver', 'deliver:order',
                'act:upgrade', 'act:open_business', 'act:focus_node',
                'act:set_regular', 'act:upgrade_regular', 'act:quiz_pass',
                'act:craft_unlock', 'act:buy_asset', 'act:assign_asset',
                'act:craft_sale', 'act:pause_business', 'act:resume_business',
                'act:salvage_business'}
    for quest in quests.quests(cfg).values():
        for objective in quest['objectives']:
            counter = objective.get('counter')
            if counter is None:
                continue
            assert counter.split(':')[0] in recorded or counter in recorded, \
                '%s wants %s, which nothing records' % (quest['id'], counter)


def test_feature_unlocks_gate_operations_and_the_port():
    cfg, state = played()
    assert not quests.has_feature(cfg, state, 'operations')
    assert not quests.has_feature(cfg, state, 'port_trading')
    quests._grant(cfg, state, dict(type='unlock_feature', feature='port_trading'))
    assert quests.has_feature(cfg, state, 'port_trading')
    assert not quests.has_feature(cfg, state, 'operations')


def test_a_class_without_the_engine_is_never_feature_gated():
    cfg, state = played(configure=False)
    # has_feature is False for everything, so callers must check enabled() first;
    # this is the contract game_api's Port gate relies on.
    assert not quests.enabled(cfg)
    assert not quests.has_feature(cfg, state, 'port_trading')


def strong_town(sectors, level=1, ticks=500):
    """A deliberately well-run town, for checking that a target is reachable."""
    import business_operations as ops
    cfg = quests.configure(economy.load_config())
    state = economy.new_state(cfg, seed=11)
    state['cash'] = 10 ** 9
    tiers = {t['id']: i for i, t in enumerate(cfg['tiers'])}
    state['tierOf'] = [tiers[s] for s in sectors]
    state['b'] = [economy._building(t) for t in state['tierOf']]
    ops.ensure(cfg, state, new=True)
    for slot in range(len(state['b'])):
        for _ in range(level - 1):
            for kind in ('production', 'sales', 'storage'):
                economy.buy_upgrade(cfg, state, slot, kind)
    state['cash'] = 5000
    for tick in range(1, ticks):
        state['tick'] = tick
        economy._produce(cfg, state, tick)
        economy._retail(cfg, state, tick)
    return cfg, state


HIGH_MARGIN = ('solar_coop', 'turbine_field', 'generator', 'relay_station', 'data_center', 'solar_array')


def test_the_margin_targets_are_actually_reachable():
    """The first draft asked for a 30% margin and 25% take-home. The economy
    designs margins at 6-23% per business, so neither could ever be hit. These
    assertions exist so a retuned target can never become impossible again."""
    cfg, state = strong_town(HIGH_MARGIN)
    targets = {}
    for quest in quests.quests(cfg).values():
        for objective in quest['objectives']:
            if objective.get('kind') == 'state' and objective['check'] in ('margin:town', 'margin:business', 'takehome:percent'):
                targets[objective['check']] = objective['target']
    assert set(targets) == {'margin:town', 'margin:business', 'takehome:percent'}
    for check, target in targets.items():
        reached = quests._live(cfg, state, check)
        assert reached >= target, '%s asks for %s; a strong town reaches %.1f' % (check, target, reached)


def test_the_income_and_net_worth_targets_are_reachable():
    cfg, state = strong_town(HIGH_MARGIN, level=4)
    assert quests._live(cfg, state, 'income:perMinute') >= 1000
    assert quests._live(cfg, state, 'netWorth') >= 1_000_000


def test_a_low_margin_portfolio_falls_short_so_the_lesson_has_teeth():
    """If any portfolio cleared the margin goal, the quest would teach nothing."""
    cfg, state = strong_town(('farm', 'fish_stall', 'roastery', 'garage', 'cannery', 'freight_terminal'))
    assert quests._live(cfg, state, 'margin:town') < 16
