"""database.py — all SQLite access for SmartBank lives in this one class.

Responsibilities (abstraction for the rest of the program):
  * create the two tables on first run
  * insert / read accounts
  * apply a deposit or withdrawal ATOMICALLY (balance update + ledger entry
    are committed together, or rolled back together)
  * answer read-only queries: daily withdrawn total, passbook range,
    recent transactions, dashboard summary
"""

import datetime
import sqlite3

from models import Account, Transaction, BankingError

DEPOSIT = "DEPOSIT"
WITHDRAWAL = "WITHDRAWAL"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_no        TEXT PRIMARY KEY,
    holder_name       TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    balance_paise     INTEGER NOT NULL DEFAULT 0,
    daily_limit_paise INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_no          TEXT NOT NULL REFERENCES accounts(account_no),
    occurred_at         TEXT NOT NULL,           -- "YYYY-MM-DD HH:MM:SS"
    transaction_type    TEXT NOT NULL CHECK (transaction_type IN ('DEPOSIT', 'WITHDRAWAL')),
    amount_paise        INTEGER NOT NULL,
    balance_after_paise INTEGER NOT NULL,
    note                TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_tx_account_date
    ON transactions (account_no, occurred_at);
"""


def _now_text():
    """One consistent timestamp format for every row we write."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_text():
    """The local calendar date, used for the daily withdrawal limit."""
    return datetime.date.today().strftime("%Y-%m-%d")


class DatabaseRepository:
    """Owns one SQLite connection. Every SQL string lives here."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        # Enforce FOREIGN KEY ... REFERENCES on every connection.
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    # ------------------------------------------------------------------ #
    # Accounts
    # ------------------------------------------------------------------ #
    def add_account(self, account):
        with self._conn:  # commit on exit, rollback on any error
            self._conn.execute(
                "INSERT INTO accounts (account_no, holder_name, created_at,"
                " balance_paise, daily_limit_paise) VALUES (?, ?, ?, ?, ?)",
                (account.account_no, account.holder_name, account.created_at,
                 account.balance_paise, account.daily_limit_paise),
            )

    def get_account(self, account_no):
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE account_no = ?", (account_no,)
        ).fetchone()
        return Account(**row) if row is not None else None

    def account_exists(self, account_no):
        return self.get_account(account_no) is not None

    def account_count(self):
        row = self._conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()
        return row["c"]

    @staticmethod
    def today_text():
        """The local calendar date, so the service shares one source of truth."""
        return _today_text()

    def list_accounts(self):
        rows = self._conn.execute(
            "SELECT * FROM accounts ORDER BY account_no"
        ).fetchall()
        return [Account(**row) for row in rows]

    # ------------------------------------------------------------------ #
    # Transactions (the core money movement)
    # ------------------------------------------------------------------ #
    def apply_transaction(self, account_no, transaction_type, amount_paise, note="", occurred_at=None):
        """Update the balance and write the ledger row in ONE atomic step.

        Returns (new_balance_paise, occurred_at). Raises BankingError if the
        account is unknown or a withdrawal would go below zero — in that case
        nothing is committed and the balance is untouched.
        """
        with self._conn:
            row = self._conn.execute(
                "SELECT balance_paise FROM accounts WHERE account_no = ?", (account_no,)
            ).fetchone()
            if row is None:
                raise BankingError(f"Account {account_no} does not exist.")

            balance = row["balance_paise"]
            if transaction_type == DEPOSIT:
                new_balance = balance + amount_paise
            else:
                new_balance = balance - amount_paise

            if new_balance < 0:
                raise BankingError(
                    f"Insufficient balance. Available: {Account(account_no, '', '', balance, 0).balance}."
                )

            self._conn.execute(
                "UPDATE accounts SET balance_paise = ? WHERE account_no = ?",
                (new_balance, account_no),
            )
            occurred = occurred_at or _now_text()
            self._conn.execute(
                "INSERT INTO transactions (account_no, occurred_at, transaction_type,"
                " amount_paise, balance_after_paise, note) VALUES (?, ?, ?, ?, ?, ?)",
                (account_no, occurred, transaction_type, amount_paise, new_balance, note),
            )
        return new_balance, occurred

    def count_transactions(self, account_no=None):
        if account_no is None:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE account_no = ?", (account_no,)
            ).fetchone()
        return row["c"]

    def total_withdrawn_on(self, account_no, date_text):
        """Sum of successful WITHDRAWAL rows for one account on one calendar day."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_paise), 0) AS total FROM transactions"
            " WHERE account_no = ? AND transaction_type = ?"
            " AND substr(occurred_at, 1, 10) = ?",
            (account_no, WITHDRAWAL, date_text),
        ).fetchone()
        return row["total"]

    def transactions_between(self, account_no, start_date, end_date):
        """Inclusive date range on the calendar-day part of occurred_at."""
        rows = self._conn.execute(
            "SELECT t.*, a.holder_name FROM transactions t"
            " JOIN accounts a ON a.account_no = t.account_no"
            " WHERE t.account_no = ? AND substr(t.occurred_at, 1, 10) BETWEEN ? AND ?"
            " ORDER BY t.transaction_id",
            (account_no, start_date, end_date),
        ).fetchall()
        return [Transaction(**row) for row in rows]

    def recent_transactions(self, count=10):
        rows = self._conn.execute(
            "SELECT t.*, a.holder_name FROM transactions t"
            " JOIN accounts a ON a.account_no = t.account_no"
            " ORDER BY t.transaction_id DESC LIMIT ?",
            (count,),
        ).fetchall()
        return [Transaction(**row) for row in rows]

    # ------------------------------------------------------------------ #
    # Dashboard summary (always computed from real data, never fabricated)
    # ------------------------------------------------------------------ #
    def summary(self):
        today = _today_text()
        accounts = self._conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(balance_paise), 0) AS total FROM accounts"
        ).fetchone()
        today_tx = self._conn.execute(
            "SELECT COUNT(*) AS n,"
            " COALESCE(SUM(CASE WHEN transaction_type = 'DEPOSIT' THEN amount_paise ELSE 0 END), 0) AS deposits,"
            " COALESCE(SUM(CASE WHEN transaction_type = 'WITHDRAWAL' THEN amount_paise ELSE 0 END), 0) AS withdrawals"
            " FROM transactions WHERE substr(occurred_at, 1, 10) = ?",
            (today,),
        ).fetchone()
        return {
            "today": today,
            "accounts_count": accounts["n"],
            "total_balance_paise": accounts["total"],
            "transactions_today": today_tx["n"],
            "deposited_today_paise": today_tx["deposits"],
            "withdrawn_today_paise": today_tx["withdrawals"],
        }
