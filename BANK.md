# Bank

`bank.html` is reachable from the shared GAME navigation. It uses the same
masthead, typography, navigation and terminal borders as the other business
pages. The banker image is decorative; all controls and balances are live HTML.

The reference-led layout keeps account actions, the banker and a slim business
loan strip, and exchange in three columns under the four-stat HUD. The next
payment strip sits below. Deposit, withdrawal, borrowing, lending and repayment
details open in accessible native dialogs rather than crowding the main screen.
On phones the banker moves above the two account/exchange columns. The Bank
fills the viewport without page scrolling; shorter landscape and phone layouts
compact their spacing without scaling the controls. Long help/history dialogs
retain internal scrolling for accessibility. Custom SVG icons replace emoji
and borrowed sprites for cash, loans, payments and transaction actions. A generated
black vault-hall background is scoped to Bank; other game pages are unchanged.

## Rules

All balances are owned by the server and saved to the seat. YM uses whole units;
USD uses integer cents. The exchange rate is a fictional fixed game rate:
**1 USD = 35.09 YM**. USD receipts round down to cents, YM receipts to whole YM.
A 1,000 YM round trip returns 999 YM; there is no rounding profit.

- Savings: deposit and withdraw at any time; 0.2% per class day, proportional to
  the ticks actually deposited. At class midnight whole-YM interest is paid to
  spendable cash. Fractional interest carries forward. Interest does not compound
  automatically because it goes to cash rather than back into savings.
- Borrowing: one outstanding business loan, minimum 100 YM, seven-day term,
  simple interest of 1% per day on remaining principal. Partial payments pay
  accrued interest first. Full repayment calculates the current debt at the
  server, including any interest since the browser's last refresh.
- Borrowing limit: minimum starter allowance 150 YM; otherwise
  `net worth × (credit score − 300) / 1100`, up to one billion YM per transaction.
  Borrowed money creates an equal liability and cannot inflate this base.
- Credit: starts at 720, maximum 850. An on-time payoff held for at least one
  class day earns 10 points. Missed maturity costs 50 points once per loan.
  A low score reduces the borrowing limit, but the 150 YM starter line remains
  available after all previous debt is paid. Players can rebuild credit through
  small on-time loans instead of needing their town reset.
- Loan maturity: automatically pay in full from spendable cash if sufficient.
  Otherwise retain the loan as overdue, continue simple interest, and retry
  automatically as class time advances. Savings, USD and lending notes are not
  liquidated to pay the debt. An overdue payoff does not earn on-time credit.
- Lending to the bank: 100 YM minimum, at most five active notes. Funds stay
  locked for seven class days. At maturity, principal plus 0.5% per day simple
  interest returns to spendable cash automatically; the whole interest payout
  rounds down to YM. No early cancellation or unearned future interest.

A day is 24 running hours on the existing classroom clock. Teacher pause stops
interest and maturities. Banking continues beyond the production offline cap;
settlement occurs when the server next advances that class. No money or time
comes from browser clocks. Assets and liabilities count in the existing town
net worth; unearned lending interest is excluded until maturity.

USD is a **separate game wallet**, not the existing Port trading balance. Port
starts with its own practice funds. Routing that wallet back into YM without
additional rules would let players import free starter capital into town.

## Persistence and access

`banking.py` stores bank state inside the existing `players.econ` JSON. Both
new-state creation and save migration initialize it at the current saved tick.
Existing classes receive empty accounts without resetting cash, businesses or
seats, and no interest is credited for time before an account existed.

`POST /api/game/bank` goes through the existing seat authentication, classroom
pause check, class lock, SQLite transaction and action ledger. It rejects
invalid numbers, stale revisions, insufficient funds and reused transaction
IDs with different instructions. The latest 64 request receipts are retained;
older revisions cannot be replayed after receipt eviction. Browser retries
retain the same ID across a page reload. Balances are never stored as authority
in browser storage. A class/player reset clears banking with the rest of the
town.

## Gameplay check — 2026-09-19

Reproduce with `.venv/bin/python previews/bank_balance_check.py`. This uses a
copy of the current startup configuration and a fresh engine state, never a live
database. Cash budgets below are representative scenarios, not asserted
milestones or predictions of how fast a class progresses.

| Spare cash | One day of savings | Seven-day bank-note interest | Borrowing limit at 720 credit, plus the starting farm |
| ---: | ---: | ---: | ---: |
| 1,000 YM | 2 YM | 35 YM | 420 YM |
| 10,000 YM | 20 YM | 350 YM | 3,856 YM |
| 100,000 YM | 200 YM | 3,500 YM | 38,220 YM |
| 1,000,000 YM | 2,000 YM | 35,000 YM | 381,856 YM |
| 10,000,000 YM | 20,000 YM | 350,000 YM | 3,818,220 YM |

Findings:

- **Borrowing is useful for timing purchases.** The fresh 150 YM credit line can
  pay for the 110 YM fish stall or 24 YM farm upgrades; it cannot skip straight
  to the 650 YM roastery. Later credit grows with the town instead of becoming
  irrelevant at a fixed 100,000 YM ceiling. Credit score changes that limit.
- **Savings and lending are secondary, longer-term choices.** In the actual
  engine, a fresh farm earned 756 YM over one running hour with no upgrades or
  manual deliveries. Depositing 1,000 YM earns only 2 YM per day. Active business
  play therefore remains far more valuable early on. Bank interest becomes
  noticeable on surplus funds and long absences, not during a short lesson.
- **There is a liquidity trade-off.** A 1,000 YM deposit pays 14 YM across seven
  full days while remaining withdrawable; a locked bank note pays 35 YM. The
  player gives up access to expansion money for the extra 21 YM.
- **Borrow-to-lend is unprofitable.** A seven-day 1,000 YM loan costs 70 YM,
  while lending those funds returns 35 YM interest: net loss 35 YM. Immediate
  borrow/repay cycles do not earn credit. Repeated receipts cannot mint cash.
- **FX is functional but strategically weak.** Holding USD has no yield or
  special purchasing power and the rate does not move. It teaches conversion
  and rounding, but it is not yet a meaningful alternate investment. A future
  USD spending purpose or carefully separated earned-funds Port bridge would
  change that; neither is silently assumed in this implementation.
- **Scope of evidence:** these are deterministic balance probes and engine/API
  tests, not a classroom playtest. In particular, the seven-day lock and credit
  penalties should be reviewed against actual class visit patterns.

## Verification and release

Bank tests cover conservation of net worth, fractional interest, bulk versus
tick-by-tick settlement, saves and migration, offline settlement, borrowing and
credit limits, early/partial/full repayment, maturity, overdue penalties,
lending, bidirectional FX, invalid amounts, stale requests, concurrent duplicate
requests, player isolation, teacher pause and reset.

Browser checks exercised the actual forms, keyboard withdrawal, reloaded the
saved account, and checked viewport and panel overflow at 1366×768, 1024×768,
844×390, 390×844, 375×667 and 320×568. Maximum-size exchange quotes retain all
digits while fitting their field. Long dialogs scroll internally; the main
screen does not. Full repository tests and JavaScript syntax checks are
required before release. Test the exact staged release separately when other
game changes share the working tree.

**Needs Manual Deploy** on Render after the changes are pushed. Existing saves
migrate in place; a class reset is not needed for this feature.
