"""Automated tests for SmartBank (unittest).

Run from the smartbank folder with any of:
    python tests/test_smartbank.py
    python -m unittest discover tests

Every test uses its own temporary database file, so the real smartbank.db
used by the application is never touched.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseRepository
from models import BankingError, format_paise, parse_rupees_to_paise
from banking_service import BankingService


class SmartBankTestCase(unittest.TestCase):
    """Base class: a fresh temporary database + service for every test."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp_dir.name, "test_smartbank.db")
        self.repo = DatabaseRepository(self.db_path)
        self.service = BankingService(self.repo)

    def tearDown(self):
        self.repo.close()
        self._tmp_dir.cleanup()

    def make_account(self, name="Alice", opening="1000", limit="1000"):
        return self.service.create_account(name, opening, limit)


class MoneyHelperTests(SmartBankTestCase):
    def test_rupees_to_paise(self):
        self.assertEqual(parse_rupees_to_paise("1250"), 125000)
        self.assertEqual(parse_rupees_to_paise("1250.50"), 125050)
        self.assertEqual(parse_rupees_to_paise("1,250.5"), 125050)
        self.assertEqual(parse_rupees_to_paise("  0.01  "), 1)

    def test_invalid_amounts_rejected(self):
        for bad in ("", "abc", "-5", "12.345", "1.2.3", "1e3", None):
            with self.assertRaises(BankingError):
                parse_rupees_to_paise(bad)

    def test_format_paise(self):
        self.assertEqual(format_paise(125050), "₹1250.50")
        self.assertEqual(format_paise(5), "₹0.05")
        self.assertEqual(format_paise(0), "₹0.00")


class AccountTests(SmartBankTestCase):
    def test_create_account(self):
        account = self.make_account("Bob", "5000", "2000")
        self.assertTrue(account.account_no.startswith("SB"))
        self.assertEqual(account.holder_name, "Bob")
        self.assertEqual(account.balance_paise, 500000)
        self.assertEqual(account.daily_limit_paise, 200000)
        # opening deposit recorded in the ledger
        self.assertEqual(self.repo.count_transactions(account.account_no), 1)

    def test_create_account_zero_opening_no_ledger_entry(self):
        account = self.make_account("Carol", "0", "500")
        self.assertEqual(account.balance_paise, 0)
        self.assertEqual(self.repo.count_transactions(account.account_no), 0)

    def test_account_numbers_are_unique(self):
        first = self.make_account("A")
        second = self.make_account("B")
        self.assertNotEqual(first.account_no, second.account_no)

    def test_empty_name_rejected(self):
        with self.assertRaises(BankingError):
            self.service.create_account("   ", "100", "500")

    def test_invalid_opening_amount_rejected(self):
        with self.assertRaises(BankingError):
            self.service.create_account("Dan", "-100", "500")
        with self.assertRaises(BankingError):
            self.service.create_account("Dan", "10.005", "500")


class DepositTests(SmartBankTestCase):
    def test_successful_deposit(self):
        account = self.make_account(opening="100")  # ledger: opening deposit ₹100
        new_balance, _ = self.service.deposit(account.account_no, "250.50")
        self.assertEqual(new_balance, 10000 + 25050)
        self.assertEqual(self.repo.get_account(account.account_no).balance_paise,
                         10000 + 25050)

    def test_deposit_unknown_account(self):
        with self.assertRaises(BankingError):
            self.service.deposit("SB9999", "100")

    def test_deposit_zero_or_negative_rejected(self):
        account = self.make_account()
        for bad in ("0", "-50", "abc", ""):
            with self.assertRaises(BankingError):
                self.service.deposit(account.account_no, bad)
        # rejected deposit must not touch the balance or the ledger
        self.assertEqual(self.repo.get_account(account.account_no).balance_paise, 100000)
        self.assertEqual(self.repo.count_transactions(account.account_no), 1)  # opening only


class WithdrawTests(SmartBankTestCase):
    def test_successful_withdrawal(self):
        account = self.make_account(opening="1000", limit="500")
        new_balance, _ = self.service.withdraw(account.account_no, "300")
        self.assertEqual(new_balance, 100000 - 30000)
        self.assertEqual(
            self.repo.get_account(account.account_no).balance_paise, 70000)

    def test_insufficient_balance_rejected(self):
        account = self.make_account(opening="100", limit="5000")
        with self.assertRaises(BankingError):
            self.service.withdraw(account.account_no, "150")
        rejected = self.repo.get_account(account.account_no)
        self.assertEqual(rejected.balance_paise, 10000)
        self.assertEqual(self.repo.count_transactions(account.account_no), 1)  # opening only

    def test_withdraw_unknown_account(self):
        with self.assertRaises(BankingError):
            self.service.withdraw("SB9999", "10")

    def test_withdraw_zero_rejected(self):
        account = self.make_account()
        with self.assertRaises(BankingError):
            self.service.withdraw(account.account_no, "0")


class DailyLimitTests(SmartBankTestCase):
    def test_limit_blocks_excess_withdrawal(self):
        account = self.make_account(opening="2000", limit="500")
        self.service.withdraw(account.account_no, "300")
        # 300 already withdrawn; 300 more would take today's total to 600 > 500
        with self.assertRaises(BankingError) as ctx:
            self.service.withdraw(account.account_no, "300")
        self.assertIn("Daily withdrawal limit exceeded", str(ctx.exception))
        # balance and ledger untouched by the rejection
        self.assertEqual(self.repo.get_account(account.account_no).balance_paise, 170000)
        self.assertEqual(self.repo.count_transactions(account.account_no), 2)  # opening + first withdrawal

    def test_withdrawal_exactly_equal_to_remaining_allowed(self):
        account = self.make_account(opening="1000", limit="500")
        self.service.withdraw(account.account_no, "200")     # used 200
        new_balance, _ = self.service.withdraw(account.account_no, "300")  # exactly the remaining 300
        self.assertEqual(new_balance, 100000 - 50000)
        self.assertEqual(
            self.repo.total_withdrawn_on(account.account_no, self.repo.today_text()), 50000)
        # now the allowance is finished
        with self.assertRaises(BankingError):
            self.service.withdraw(account.account_no, "1")

    def test_limit_is_per_day_not_per_transaction(self):
        account = self.make_account(opening="5000", limit="300")
        for _ in range(3):
            self.service.withdraw(account.account_no, "100")
        with self.assertRaises(BankingError):
            self.service.withdraw(account.account_no, "1")


class BalanceConsistencyTests(SmartBankTestCase):
    def test_balance_matches_ledger_after_transactions(self):
        account = self.make_account(opening="1000", limit="1000")
        self.service.deposit(account.account_no, "250.50")
        self.service.withdraw(account.account_no, "100")
        self.service.deposit(account.account_no, "0.25")
        expected = 100000 + 25050 - 10000 + 25
        self.assertEqual(self.repo.get_account(account.account_no).balance_paise, expected)

        ledger = self.service.passbook(account.account_no, "2000-01-01", "2999-12-31")
        self.assertEqual(ledger[-1].balance_after_paise, expected)
        # every row must equal the previous row plus/minus its own amount
        running = 0
        for tx in ledger:
            running += tx.amount_paise if tx.transaction_type == "DEPOSIT" else -tx.amount_paise
            self.assertEqual(tx.balance_after_paise, running)


class PassbookTests(SmartBankTestCase):
    def test_passbook_date_filtering(self):
        account = self.make_account(opening="1000", limit="5000")
        # two transactions inside the target range, one outside, via direct
        # repository calls with controlled timestamps (keeps clock-independent)
        self.repo.apply_transaction(account.account_no, "DEPOSIT", 50000,
                                    "In range", occurred_at="2026-03-05 10:00:00")
        self.repo.apply_transaction(account.account_no, "WITHDRAWAL", 20000,
                                    "In range", occurred_at="2026-03-06 23:59:59")
        self.repo.apply_transaction(account.account_no, "DEPOSIT", 10000,
                                    "Before range", occurred_at="2026-03-04 09:00:00")

        rows = self.service.passbook(account.account_no, "2026-03-05", "2026-03-06")
        self.assertEqual([r.note for r in rows], ["In range", "In range"])
        self.assertEqual(rows[0].balance_after_paise, 150000)
        self.assertEqual(rows[1].transaction_type, "WITHDRAWAL")

    def test_passbook_invalid_range_rejected(self):
        account = self.make_account()
        with self.assertRaises(BankingError):
            self.service.passbook(account.account_no, "2026-05-01", "2026-04-01")
        with self.assertRaises(BankingError):
            self.service.passbook(account.account_no, "not-a-date", "2026-04-01")

    def test_passbook_empty_history(self):
        account = self.make_account("Empty", "0", "100")
        rows = self.service.passbook(account.account_no, "2026-01-01", "2026-12-31")
        self.assertEqual(rows, [])


class PersistenceTests(SmartBankTestCase):
    def test_data_survives_repository_reconnection(self):
        account = self.make_account("Persist", "700", "300")
        self.service.deposit(account.account_no, "100.25")
        self.service.withdraw(account.account_no, "50")
        old_no = account.account_no

        self.repo.close()  # simulate an application restart
        self.repo = DatabaseRepository(self.db_path)
        self.service = BankingService(self.repo)

        restored = self.service.get_account(old_no)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.holder_name, "Persist")
        self.assertEqual(restored.balance_paise, 70000 + 10025 - 5000)
        self.assertEqual(restored.daily_limit_paise, 30000)
        self.assertEqual(self.repo.count_transactions(old_no), 3)  # opening + deposit + withdrawal
        # withdrawal history must still count toward today's limit
        status = self.service.daily_status(old_no)
        self.assertEqual(status["used"], 5000)
        self.assertEqual(status["remaining"], 30000 - 5000)


if __name__ == "__main__":
    unittest.main()
