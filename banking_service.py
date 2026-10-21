"""banking_service.py — the business rules of SmartBank.

The GUI never touches SQL. It asks this service to do things, and the
service either returns real data or raises BankingError with a friendly
message. All validation rules live here so they are easy to explain in a
viva and easy to test.
"""

import datetime

from database import DEPOSIT, WITHDRAWAL, _now_text
from models import Account, BankingError, parse_rupees_to_paise, format_paise


class BankingService:
    def __init__(self, repository):
        self._repo = repository  # depends on the abstraction in database.py

    # ------------------------------------------------------------------ #
    # 1. Create account
    # ------------------------------------------------------------------ #
    def create_account(self, holder_name, opening_amount_text, daily_limit_text):
        """Create an account and (if > 0) record the opening deposit."""
        name = (holder_name or "").strip()
        if not name:
            raise BankingError("Account holder name cannot be empty.")
        if not all(ch.isalnum() or ch.isspace() or ch in ".-'_," for ch in name):
            raise BankingError("Name can only contain letters, numbers, spaces and . - , ' _ characters.")

        opening_paise = parse_rupees_to_paise(opening_amount_text or "0")
        daily_limit_paise = parse_rupees_to_paise(daily_limit_text)

        account_no = self._generate_account_no()
        # stored with zero balance; the opening deposit (if any) is then
        # applied through apply_transaction, which also writes the ledger row
        account = Account(account_no, name, _now_text(), 0, daily_limit_paise)
        self._repo.add_account(account)

        if opening_paise > 0:
            self._repo.apply_transaction(
                account_no, DEPOSIT, opening_paise, note="Opening deposit"
            )
        return self._repo.get_account(account_no)

    def _generate_account_no(self):
        """SB + a zero-padded sequence, guaranteed unique in the database."""
        number = 1000 + self._repo.account_count() + 1
        while self._repo.account_exists(f"SB{number}"):
            number += 1
        return f"SB{number}"

    # ------------------------------------------------------------------ #
    # 2 & 3. Deposit / Withdraw money
    # ------------------------------------------------------------------ #
    def deposit(self, account_no, amount_text, note=""):
        amount_paise = self._positive_amount(amount_text)
        self._require_account(account_no)
        new_balance, occurred = self._repo.apply_transaction(
            account_no, DEPOSIT, amount_paise, note or "Cash deposit"
        )
        return new_balance, occurred

    def withdraw(self, account_no, amount_text, note=""):
        amount_paise = self._positive_amount(amount_text)
        account = self._require_account(account_no)

        # Rule 1: enough money in the account?
        if amount_paise > account.balance_paise:
            raise BankingError(
                f"Insufficient balance. Available: {account.balance}, requested: {format_paise(amount_paise)}."
            )

        # Rule 2: daily withdrawal limit for today's calendar date?
        used = self._repo.total_withdrawn_on(account_no, self._repo.today_text())
        remaining = account.daily_limit_paise - used
        if amount_paise > remaining:
            raise BankingError(
                f"Daily withdrawal limit exceeded.\n"
                f"Limit: {account.daily_limit}\n"
                f"Already withdrawn today: {format_paise(used)}\n"
                f"Remaining allowance today: {format_paise(max(remaining, 0))}"
            )

        return self._repo.apply_transaction(
            account_no, WITHDRAWAL, amount_paise, note or "Cash withdrawal"
        )

    # ------------------------------------------------------------------ #
    # 4. Daily withdrawal limit status (shown on the Account Info screen)
    # ------------------------------------------------------------------ #
    def daily_status(self, account_no):
        account = self._require_account(account_no)
        used = self._repo.total_withdrawn_on(account_no, self._repo.today_text())
        return {
            "today": self._repo.today_text(),
            "limit": account.daily_limit_paise,
            "used": used,
            "remaining": max(account.daily_limit_paise - used, 0),
        }

    # ------------------------------------------------------------------ #
    # 5 & 6. Balance enquiry / account information
    # ------------------------------------------------------------------ #
    def get_account(self, account_no, error_title="Account"):
        return self._require_account(account_no, error_title)

    def list_accounts(self):
        return self._repo.list_accounts()

    # ------------------------------------------------------------------ #
    # 7. Passbook (from–to)
    # ------------------------------------------------------------------ #
    def passbook(self, account_no, start_text, end_text):
        self._require_account(account_no)
        start = self._parse_date(start_text, "start")
        end = self._parse_date(end_text, "end")
        if start > end:
            raise BankingError("Invalid date range: the start date cannot be after the end date.")
        start_text = start.strftime("%Y-%m-%d")
        end_text = end.strftime("%Y-%m-%d")
        return self._repo.transactions_between(account_no, start_text, end_text)

    # ------------------------------------------------------------------ #
    # Dashboard
    # ------------------------------------------------------------------ #
    def dashboard_stats(self):
        return self._repo.summary()

    def recent_transactions(self, count=10):
        return self._repo.recent_transactions(count)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _positive_amount(self, amount_text):
        paise = parse_rupees_to_paise(amount_text)
        if paise <= 0:
            raise BankingError("Amount must be greater than zero.")
        return paise

    def _require_account(self, account_no, error_title="Account"):
        account = self._repo.get_account((account_no or "").strip())
        if account is None:
            raise BankingError(f"{error_title} number not found: {(account_no or '').strip() or '(empty)'}")
        return account

    @staticmethod
    def _parse_date(text, which):
        try:
            return datetime.datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
        except ValueError:
            raise BankingError(
                f"Invalid {which} date '{(text or '').strip() or '(empty)'}'. "
                f"Use the YYYY-MM-DD format, for example 2026-01-31."
            )
