"""models.py — data classes and money helpers for SmartBank.

Money rule: every amount is stored as an INTEGER number of paise.
Rupees are only used at the edges (user input / display), never for
calculations, so there are no floating point rounding errors.
"""

import re


class BankingError(Exception):
    """Raised for any validation or business-rule problem.

    The GUI catches this exception and shows the message in a message box,
    so messages written here are user-facing (keep them friendly).
    """


# Matches: "1250", "1250.5", "1250.50" (with optional thousands commas / rupee sign)
_AMOUNT_RE = re.compile(r"^(\d+)(?:\.(\d{0,2}))?$")


def parse_rupees_to_paise(text):
    """Convert an amount typed in rupees into integer paise.

    Examples: "1250" -> 125000, "1250.50" -> 125050, "1,250" -> 125000.
    Raises BankingError for anything that is not a valid positive amount
    (empty text, negative numbers, more than two decimals, etc.).
    """
    if text is None:
        raise BankingError("Please enter an amount.")
    cleaned = str(text).replace(",", "").replace("\u20b9", "").strip()
    match = _AMOUNT_RE.match(cleaned)
    if match is None:
        raise BankingError(
            "Amount must be a positive number with at most two decimal "
            "places, for example 500 or 500.50."
        )
    whole, fraction = match.groups()
    fraction = ((fraction or "") + "00")[:2]  # ".5" -> "50"
    return int(whole) * 100 + int(fraction)


def format_paise(paise):
    """Format integer paise as a rupee string with two decimals, e.g. 125050 -> ₹1250.50."""
    paise = int(paise)
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    return f"{sign}\u20b9{paise // 100}.{paise % 100:02d}"


class Account:
    """One bank account. Just holds the row data from the accounts table."""

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"

    def __init__(self, account_no, holder_name, created_at, balance_paise, daily_limit_paise):
        self.account_no = account_no
        self.holder_name = holder_name
        self.created_at = created_at              # "YYYY-MM-DD HH:MM:SS"
        self.balance_paise = int(balance_paise)   # integer paise
        self.daily_limit_paise = int(daily_limit_paise)

    # Presentation helpers (encapsulation: the GUI never touches raw paise maths)
    @property
    def balance(self):
        return format_paise(self.balance_paise)

    @property
    def daily_limit(self):
        return format_paise(self.daily_limit_paise)

    @property
    def display_name(self):
        return f"{self.account_no}  |  {self.holder_name}"

    def __repr__(self):  # handy during debugging
        return (f"Account({self.account_no!r}, name={self.holder_name!r}, "
                f"balance={self.balance_paise}p, limit={self.daily_limit_paise}p)")


class Transaction:
    """One ledger entry from the transactions table."""

    def __init__(self, transaction_id, account_no, occurred_at, transaction_type,
                 amount_paise, balance_after_paise, note, holder_name=None):
        self.transaction_id = transaction_id
        self.account_no = account_no
        self.occurred_at = occurred_at          # "YYYY-MM-DD HH:MM:SS"
        self.transaction_type = transaction_type  # Account.DEPOSIT or Account.WITHDRAWAL
        self.amount_paise = int(amount_paise)
        self.balance_after_paise = int(balance_after_paise)
        self.note = note or ""
        self.holder_name = holder_name          # optional, filled by JOIN queries

    @property
    def date_text(self):
        """Just the calendar-day part, used for the daily limit and passbook."""
        return self.occurred_at[:10]

    @property
    def amount(self):
        return format_paise(self.amount_paise)

    @property
    def balance_after(self):
        return format_paise(self.balance_after_paise)
