"""Read-only reproducible bank gameplay probes; no database or live seats."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banking
import game_api
import production_economy as E


def run():
    cfg = copy.deepcopy(game_api._startup_config)
    fresh = E.new_state(cfg, seed=71)
    samples = []
    # Representative budgets, not a claim that the class reaches them on a
    # particular day. Show the exact bank choice at each amount of spare cash.
    for cash in (100, 1000, 10000, 100000, 1000000, 10000000):
        st = E.new_state(cfg, seed=71)
        st['cash'] = cash
        samples.append(dict(spareYM=cash, overnightSavings=cash * banking.SAVINGS_BPS / 10000,
                            sevenDaySavings=cash * banking.SAVINGS_BPS * 7 / 10000,
                            sevenDayLending=cash * banking.LENDING_BPS * 7 // 10000,
                            sevenDayBorrowingCost=cash * banking.LOAN_BPS * 7 / 10000,
                            borrowingLimit=banking.borrow_limit(st)))
    # Real engine: fresh farm, no manual orders/upgrades. What does the starting
    # business earn while the bank's day clock is running?
    measured = copy.deepcopy(fresh)
    world = E.new_class(cfg, E.ticks_per_hour(cfg))
    E.advance_class(cfg, world, [measured], 0, E.ticks_per_hour(cfg))
    borrowed = copy.deepcopy(fresh)
    credit = banking.borrow_limit(borrowed)
    banking.act(cfg, borrowed, dict(action='borrow', amount=credit, revision=0, requestId='audit-borrow'))
    expansion = E.expand_options(cfg, borrowed)
    result = dict(
        rules=banking.payload(cfg, fresh)['rules'],
        budgets=samples,
        fresh=dict(netWorth=E.net_worth(fresh), borrowingLimit=credit,
                   farmCustomerUpgrade=E.upgrade_cost(cfg, fresh, 0, 'sales'),
                   farmProductionUpgrade=E.upgrade_cost(cfg, fresh, 0, 'production'),
                   nextBusinesses=[dict(name=cfg['tiers'][i]['name'], price=cfg['tiers'][i]['baseCost'],
                                        affordableWithLoan=cfg['tiers'][i]['baseCost'] <= borrowed['cash']) for i in expansion]),
        farmOneHour=dict(cashEarned=measured['cash'] - fresh['cash'],
                         protocol='One fresh farm, 60 running minutes, no upgrades or manual deliveries; real production engine.'),
        borrowedToLend7DayNetPer1000=1000 * (banking.LENDING_BPS - banking.LOAN_BPS) * 7 // 10000,
        fxRoundTrip1000YM=(1000 * 10000 // banking.FX) * banking.FX // 10000,
        fxUtility='Fixed denomination exchange only; USD is not connected to the separately seeded Port wallet.',
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
