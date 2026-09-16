"""Basic-supply rewards observe real milestones once and respect their budgets."""
from __future__ import annotations

import copy

import crafting
import crafting_pilot as pilot
import production_economy as economy


def town(seed=71):
    cfg = pilot.configure(economy.load_config())
    state = economy.new_state(cfg, seed=seed)
    pilot.ensure(cfg, state)
    return cfg, state


def rewards(state):
    return state['craftingPilot']['rewards']


def check_pack(cfg, state, budget, reason):
    pack = rewards(state)['recent'][-1]
    assert pack['reason'] == reason
    assert 0 < pack['value'] <= budget
    assert pack['value'] == sum(item['quantity'] * crafting.SUPPLIES[item['id']]['unitPrice']
                                for item in pack['items'])
    assert all(item['id'] in crafting.SUPPLIES and type(item['quantity']) is int and item['quantity'] > 0
               for item in pack['items'])
    return pack


def test_existing_quests_and_focus_do_not_receive_retroactive_rewards():
    cfg = economy.load_config()
    state = economy.new_state(cfg, seed=71)
    state['businessProgression']['quests']['farm-plan'] = dict(completed=True)
    state['workforce']['teams']['farm'] = dict(nodes=['orientation', 'production'])
    pilot.configure(cfg)
    pilot.ensure(cfg, state)
    before = copy.deepcopy(state['crafting'])
    pilot.observe_rewards(cfg, state)
    pilot.visit(cfg, state)
    assert rewards(state)['sequence'] == 0
    assert state['crafting'] == before


def test_new_quest_pays_one_basic_supply_pack_even_after_repeat_observation():
    cfg, state = town()
    before_cash = state['cash']
    before_items = copy.deepcopy(state['crafting']['items'])
    before_assets = copy.deepcopy(state['craftingPilot']['assets'])
    state['businessProgression']['quests']['farm-plan'] = dict(completed=True)
    pilot.observe_rewards(cfg, state)
    pack = check_pack(cfg, state, cfg['craftingPilot']['rewards']['questBudget'], 'Quest completed')
    assert state['cash'] == before_cash
    assert state['crafting']['items'] == before_items
    assert state['craftingPilot']['assets'] == before_assets
    assert crafting.stored_value(state) == pack['value']
    before = copy.deepcopy(state)
    pilot.observe_rewards(cfg, state)
    assert state == before


def test_each_new_focus_node_pays_once_and_reward_history_cannot_be_replayed():
    cfg, state = town()
    state['workforce']['teams']['farm'] = dict(nodes=['orientation', 'production'])
    pilot.observe_rewards(cfg, state)
    assert rewards(state)['sequence'] == 2
    check_pack(cfg, state, cfg['craftingPilot']['rewards']['focusBudget'], 'Focus progress')
    value = crafting.stored_value(state)
    state['workforce']['teams']['farm']['nodes'] = []
    pilot.observe_rewards(cfg, state)
    state['workforce']['teams']['farm']['nodes'] = ['orientation', 'production']
    pilot.observe_rewards(cfg, state)
    assert rewards(state)['sequence'] == 2
    assert crafting.stored_value(state) == value


def test_every_third_completed_order_pays_once_and_counts_each_business_once():
    cfg, state = town()
    requirements = [dict(goodId='farm_eggs', quantity=2), dict(goodId='farm_tomatoes', quantity=3)]
    pilot.record_order(cfg, state, requirements)
    pilot.record_order(cfg, state, requirements)
    assert rewards(state)['sequence'] == 0
    pilot.record_order(cfg, state, requirements)
    assert rewards(state)['sequence'] == 1
    assert state['craftingPilot']['ordersByBusiness']['farm'] == 3
    check_pack(cfg, state, cfg['craftingPilot']['rewards']['orderBudget'], 'Manual-order milestone')
    before = copy.deepcopy(state)
    pilot.observe_rewards(cfg, state)
    assert state == before
    for _ in range(3):
        pilot.record_order(cfg, state, requirements)
    assert rewards(state)['sequence'] == 2
    assert state['craftingPilot']['ordersTotal'] == 6


def test_welcome_back_uses_real_visits_and_awards_once_after_four_hours():
    cfg, state = town()
    pilot.visit(cfg, state)
    deadline = cfg['craftingPilot']['rewards']['welcomeAbsenceSeconds'] // cfg['global']['tick']
    state['tick'] = deadline
    # Other server activity and milestone observation do not count as a visit.
    pilot.tick(cfg, state, deadline)
    pilot.observe_rewards(cfg, state)
    assert rewards(state)['lastVisit'] == 0
    pilot.visit(cfg, state)
    assert rewards(state)['sequence'] == 1
    check_pack(cfg, state, cfg['craftingPilot']['rewards']['welcomeBudget'], 'Welcome back')
    before = copy.deepcopy(state)
    pilot.visit(cfg, state)
    assert state == before


def test_frequent_visits_cannot_farm_welcome_back_packs():
    cfg, state = town()
    deadline = cfg['craftingPilot']['rewards']['welcomeAbsenceSeconds'] // cfg['global']['tick']
    for moment in range(0, deadline * 3, max(1, deadline // 2)):
        state['tick'] = moment
        pilot.visit(cfg, state)
    assert rewards(state)['sequence'] == 0
    assert state['crafting']['supplies'] == {}


def test_reward_selection_does_not_depend_on_owned_businesses():
    cfg, state = town()
    other = copy.deepcopy(state)
    other['tierOf'] = list(range(len(cfg['tiers'])))
    other['b'] = [economy._building(tier) for tier in other['tierOf']]
    for target in (state, other):
        target['businessProgression']['quests']['farm-plan'] = dict(completed=True)
        pilot.observe_rewards(cfg, target)
    assert state['crafting']['supplies'] == other['crafting']['supplies']


def test_reward_invalidates_an_unapplied_old_purchase_quote():
    cfg, state = town()
    state['cash'] = 1000
    body = dict(action='buy_supply', supplyId='wooden_boards', quantity=1,
                requestId='before-quest-reward', revision=state['crafting']['revision'])
    state['businessProgression']['quests']['farm-plan'] = dict(completed=True)
    pilot.observe_rewards(cfg, state)
    before = copy.deepcopy(state)
    assert not crafting.act(cfg, state, body)['ok']
    assert state == before


def test_flag_off_prevents_all_new_reward_hooks_from_changing_the_save():
    cfg = economy.load_config()
    state = economy.new_state(cfg, seed=71)
    before = copy.deepcopy(state)
    pilot.observe_rewards(cfg, state)
    pilot.visit(cfg, state)
    pilot.record_order(cfg, state, [dict(goodId='farm_eggs', quantity=2)])
    assert state == before
