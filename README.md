# SmartBank — Banking Management System

SmartBank is a small desktop banking application built for an Object-Oriented
Programming (OOP) mini project. It demonstrates the seven core banking
operations from the syllabus using **Python 3, Tkinter (GUI) and SQLite
(database)** — no web frameworks and no external dependencies beyond the
standard library.

## Features

| # | Operation | Where in the app |
|---|-----------|------------------|
| 1 | Create Account (auto account number, opening deposit, daily limit) | "Create Account" |
| 2 | Deposit Money | "Deposit Money" |
| 3 | Withdraw Money (balance + daily-limit checks) | "Withdraw Money" |
| 4 | Daily Withdrawal Limit (per account, per calendar day) | enforced on withdrawal; status shown in "Account Info" |
| 5 | Check Balance | "Balance Enquiry" |
| 6 | Display Account Information | "Account Info" |
| 7 | Passbook Print (From–To) with CSV export | "Passbook (From–To)" |

The **Dashboard** shows live summary cards (accounts, total balance,
transactions today, withdrawn today) and the ten most recent transactions,
all computed from the actual database — an empty database shows zeros and an
empty state.

## How to run

Requires Python 3.8+ with Tkinter (included with standard CPython on
Windows/macOS; on Linux install it with e.g. `sudo dnf install python3-tkinter`
if missing).

```bash
cd smartbank
python3 main.py
```

On first run the app creates `smartbank.db` next to the source files. That file
is the entire database — all accounts and transactions survive restarts. Delete
it to start with a completely empty bank.

## How to test

The automated `unittest` suite never touches the real `smartbank.db`; each test
uses its own temporary database.

```bash
cd smartbank
python3 tests/test_smartbank.py          # or:
python3 -m unittest discover tests
```

## Project structure (same as the suggested layout)

```
smartbank/
├── main.py                 # entry point: wires DB → service → GUI
├── models.py               # Account, Transaction, money helpers (rupees ⇄ paise)
├── database.py             # DatabaseRepository: all SQL, table creation
├── banking_service.py      # BankingService: business rules & validation
├── gui.py                  # SmartBankApp: Tkinter window, pages, message boxes
├── tests/test_smartbank.py # 23 automated tests (temporary DBs)
└── smartbank.db            # SQLite database, generated automatically at runtime
```

### OOP concepts demonstrated

* **Classes & encapsulation** — `Account` and `Transaction` are simple data
  classes; money is always stored as integer **paise** and only exposed as
  formatted rupees (`₹1250.50`) through properties. The GUI never does money
  arithmetic itself.
* **Abstraction / separation of responsibilities** — the GUI knows nothing
  about SQL; `DatabaseRepository` knows nothing about business rules;
  `BankingService` holds the rules (limits, validations) and raises
  `BankingError` with user-friendly messages.
* **Modularity** — each module can be imported on its own, which is what makes
  the service layer testable without Tkinter.
* No artificial inheritance or design patterns were added just for show.

### Notable implementation details

* All SQL is **parameterized**; enabling `PRAGMA foreign_keys = ON` enforces the
  `transactions.account_no → accounts.account_no` foreign key.
* A deposit/withdrawal updates the balance **and** writes the ledger row inside
  one SQLite transaction (`with self._conn:`), so they commit or roll back
  together. A rejected transaction changes nothing.
* The daily limit sums the account's successful `WITHDRAWAL` rows whose
  timestamp falls on the **local calendar date today**; a withdrawal exactly
  equal to the remaining allowance is allowed.
* Dates run `YYYY-MM-DD`, timestamps `YYYY-MM-DD HH:MM:SS`, so they sort and
  filter reliably with plain string comparisons.
* The passbook page filters an inclusive From–To date range, shows
  credit/debit/balance-after columns, and can export the exact table to CSV.

## Out of scope (per the project brief)

Online banking, authentication, cloud/remote databases, web deployment — none
of these are included. SmartBank is deliberately a single-user, single-file
local desktop application.
