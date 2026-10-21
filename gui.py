"""gui.py — the SmartBank desktop GUI (Tkinter).

SmartBankApp builds one window with a left navigation panel and a content
area. Each navigation item builds its page inside the content area and
calls BankingService methods; every service call is wrapped so that
BankingError becomes a message box instead of a crash.
"""

import csv
import sqlite3
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from models import BankingError, format_paise

# ------------------------------------------------------------------ #
# Small theme table (navy / white / green)
# ------------------------------------------------------------------ #
NAVY = "#16305B"
NAVY_DARK = "#0E2140"
GREEN = "#1E8449"
BG = "#F4F6FA"
CARD = "#FFFFFF"
BORDER = "#DCE3ED"
TEXT = "#1C2A3A"
MUTED = "#5D6B7E"
RED = "#C0392B"

FONT = ("Helvetica", 10)
FONT_BOLD = ("Helvetica", 10, "bold")
FONT_H1 = ("Helvetica", 17, "bold")
FONT_H2 = ("Helvetica", 12, "bold")
FONT_BIG = ("Helvetica", 22, "bold")
FONT_SMALL = ("Helvetica", 9)

NAV_ITEMS = [
    ("Dashboard", "Dashboard"),
    ("Create Account", "Create Account"),
    ("Deposit Money", "Deposit"),
    ("Withdraw Money", "Withdraw"),
    ("Balance Enquiry", "Balance"),
    ("Account Info", "AccountInfo"),
    ("Passbook (From–To)", "Passbook"),
]


class SmartBankApp:
    def __init__(self, service, root=None):
        self.service = service
        self.root = root or tk.Tk()
        self.root.title("SmartBank - Banking Management System")
        self.root.geometry("1100x700")
        self.root.minsize(950, 620)
        self.root.configure(bg=BG)
        self._nav_buttons = {}
        self._build_layout()
        self._configure_treeview_style()
        self.show_page("Dashboard")

    def run(self):
        self.root.mainloop()

    # ================================================================== #
    # Window frame: sidebar + content container
    # ================================================================== #
    def _build_layout(self):
        sidebar = tk.Frame(self.root, bg=NAVY, width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="🏦 SmartBank", bg=NAVY, fg="white",
                 font=("Helvetica", 16, "bold")).pack(pady=(22, 2))
        tk.Label(sidebar, text="Banking Management System", bg=NAVY,
                 fg="#9FB3D1", font=FONT_SMALL).pack(pady=(0, 18))

        for label, key in NAV_ITEMS:
            button = tk.Button(
                sidebar, text="  " + label,
                bd=0, fg="white", bg=NAVY, font=FONT, anchor="w",
                activebackground=NAVY_DARK, activeforeground="white",
                padx=16, pady=8, cursor="hand2",
                command=lambda k=key: self.show_page(k),
            )
            button.pack(fill="x")
            self._nav_buttons[key] = button

        tk.Button(sidebar, text="  Exit", bd=0, fg="#F5B7B1", bg=NAVY,
                  font=FONT, anchor="w", padx=16, pady=8, cursor="hand2",
                  activebackground=NAVY_DARK,
                  command=self._confirm_exit).pack(side="bottom", fill="x")

        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(side="right", fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._confirm_exit)

    def _configure_treeview_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=26, font=FONT)
        style.configure("Treeview.Heading", background=NAVY, foreground="white",
                        font=FONT_BOLD, padding=4)

    # ================================================================== #
    # Page plumbing
    # ================================================================== #
    def show_page(self, key):
        for widget in self.container.winfo_children():
            widget.destroy()
        self._mark_active(key)
        if key == "Dashboard":
            self._dashboard_page()
        elif key == "Create Account":
            self._create_account_page()
        elif key in ("Deposit", "Withdraw"):
            self._money_page(key)
        elif key == "Balance":
            self._balance_page()
        elif key == "AccountInfo":
            self._account_info_page()
        elif key == "Passbook":
            self._passbook_page()

    def _mark_active(self, key):
        for item_key, button in self._nav_buttons.items():
            button.configure(bg=GREEN if item_key == key else NAVY,
                             font=FONT_BOLD if item_key == key else FONT)

    def _page(self):
        """A fresh page frame inside the container: navy header + content body."""
        page = tk.Frame(self.container, bg=BG)
        page.pack(fill="both", expand=True)
        return page

    def _page_header(self, page, title, subtitle):
        header = tk.Frame(page, bg=NAVY)
        header.pack(fill="x")
        tk.Label(header, text=title, bg=NAVY, fg="white",
                 font=FONT_H1).pack(anchor="w", padx=24, pady=(16, 2))
        tk.Label(header, text=subtitle, bg=NAVY, fg="#9FB3D1",
                 font=FONT).pack(anchor="w", padx=24, pady=(0, 14))
        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=20)
        return body

    def _card(self, parent):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        return card

    # ================================================================== #
    # Shared widgets
    # ================================================================== #
    def _account_picker(self, parent):
        """A labelled combobox of accounts. Returns (combo, accounts)."""
        accounts = self.service.list_accounts()
        labels = [a.display_name for a in accounts]

        tk.Label(parent, text="Select account", bg=CARD, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w", pady=(8, 2))
        combo = ttk.Combobox(parent, values=labels, state="readonly",
                             width=34, font=FONT)
        combo.pack(fill="x", ipady=3)
        if labels:
            combo.current(0)
        return combo, accounts

    def _chosen_account(self, combo, accounts):
        if not accounts:
            raise BankingError("No accounts exist yet. Create an account first.")
        index = combo.current()
        if index < 0:
            raise BankingError("Please select an account.")
        return accounts[index]

    def _form_field(self, parent, label, width=26):
        tk.Label(parent, text=label, bg=CARD, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w", pady=(9, 2))
        entry = tk.Entry(parent, font=FONT, width=width,
                         bg="white", highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=NAVY,
                         relief="flat")
        entry.pack(fill="x", ipady=4)
        return entry

    def _tree(self, parent, columns, heading_map):
        """Treeview with a vertical scrollbar, returns the tree widget."""
        holder = tk.Frame(parent, bg=CARD)
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=columns, show="headings", height=8)
        for column, (heading, width, anchor) in heading_map.items():
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor=anchor)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.tag_configure("DEPOSIT", foreground=GREEN)
        tree.tag_configure("WITHDRAWAL", foreground=RED)
        return tree

    @staticmethod
    def _type_label(transaction_type):
        return "Deposit" if transaction_type == "DEPOSIT" else "Withdrawal"

    # ================================================================== #
    # Dashboard
    # ================================================================== #
    def _dashboard_page(self):
        page = self._page()
        body = self._page_header(page, "Dashboard", "Live overview of your bank")
        stats = self.service.dashboard_stats()

        cards_frame = tk.Frame(body, bg=BG)
        cards_frame.pack(fill="x", pady=(0, 18))
        cards = [
            ("Total Accounts", str(stats["accounts_count"]), NAVY),
            ("Total Balance", format_paise(stats["total_balance_paise"]), GREEN),
            ("Transactions Today", str(stats["transactions_today"]), NAVY),
            ("Withdrawn Today", format_paise(stats["withdrawn_today_paise"]), RED),
        ]
        for index, (title, value, color) in enumerate(cards):
            cards_frame.columnconfigure(index, weight=1)
            card = self._card(cards_frame)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 14 if index < 3 else 0))
            tk.Label(card, text=title.upper(), bg=CARD, fg=MUTED,
                     font=FONT_SMALL).pack(anchor="w", padx=16, pady=(14, 2))
            tk.Label(card, text=value, bg=CARD, fg=color,
                     font=FONT_BIG).pack(anchor="w", padx=16, pady=(0, 4))
            tk.Frame(card, bg=color, height=3).pack(fill="x", side="bottom")

        panel = self._card(body)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="Recent Transactions", bg=CARD, fg=TEXT,
                 font=FONT_H2).pack(anchor="w", padx=16, pady=(14, 4))
        tree = self._tree(
            panel,
            ["occurred", "account", "type", "amount", "balance"],
            {
                "occurred": ("Date & Time", 150, "w"),
                "account": ("Account / Holder", 210, "w"),
                "type": ("Type", 100, "w"),
                "amount": ("Amount", 110, "e"),
                "balance": ("Balance After", 110, "e"),
            },
        )
        transactions = self.service.recent_transactions(10)
        if not transactions:
            tk.Label(panel, text="No transactions yet. Create an account and make your first deposit.",
                     bg=CARD, fg=MUTED, font=FONT).pack(anchor="w", padx=16, pady=12)
            return
        for tx in transactions:
            account_text = f"{tx.account_no} — {tx.holder_name}"
            sign = "+" if tx.transaction_type == "DEPOSIT" else "−"
            tree.insert("", "end", tags=(tx.transaction_type,), values=(
                tx.occurred_at, account_text, self._type_label(tx.transaction_type),
                f"{sign}{format_paise(tx.amount_paise)}", tx.balance_after,
            ))

    # ================================================================== #
    # Create Account
    # ================================================================== #
    def _create_account_page(self):
        page = self._page()
        body = self._page_header(page, "Create Account", "Open a new SmartBank account")
        form = self._card(body)
        form.pack(anchor="n", fill="x")
        inner = tk.Frame(form, bg=CARD)
        inner.pack(padx=22, pady=12, anchor="w")

        name_entry = self._form_field(inner, "Account holder name", 30)
        opening = self._form_field(inner, "Opening deposit (₹)", 30)
        opening.insert(0, "0")
        limit = self._form_field(inner, "Daily withdrawal limit (₹)", 30)
        limit.insert(0, "10000")

        submit = tk.Button(form, text="Create Account", bg=GREEN, fg="white",
                           font=FONT_BOLD, relief="flat", cursor="hand2",
                           activebackground="#166B3A", padx=18, pady=6,
                           command=lambda: self._submit_create_account(
                               name_entry, opening, limit))
        submit.pack(anchor="w", padx=22, pady=(0, 16))

    def _submit_create_account(self, name_entry, opening, limit):
        try:
            account = self.service.create_account(
                name_entry.get(), opening.get(), limit.get())
        except (BankingError, sqlite3.Error) as error:
            messagebox.showerror("SmartBank", _error_text(error), parent=self.root)
            return
        name_entry.delete(0, "end")
        opening.delete(0, "end")
        opening.insert(0, "0")
        messagebox.showinfo(
            "Account Created",
            f"Account created successfully!\n\n"
            f"Account Number : {account.account_no}\n"
            f"Holder Name    : {account.holder_name}\n"
            f"Opening Balance: {account.balance}\n"
            f"Daily Limit    : {account.daily_limit}",
            parent=self.root)

    # ================================================================== #
    # Deposit / Withdraw (shared layout, different service call)
    # ================================================================== #
    def _money_page(self, kind):
        is_deposit = kind == "Deposit"
        page = self._page()
        subtitle = ("Add money to an existing account" if is_deposit
                    else "Take money out, respecting the daily limit")
        body = self._page_header(page, f"{kind} Money", subtitle)

        form = self._card(body)
        form.pack(anchor="n", fill="x")
        inner = tk.Frame(form, bg=CARD)
        inner.pack(padx=22, pady=12, anchor="w")
        combo, accounts = self._account_picker(inner)
        amount = self._form_field(inner, "Amount (₹)")
        note = self._form_field(inner, "Note (optional)")
        note.insert(0, "Cash deposit" if is_deposit else "Cash withdrawal")
        submit = tk.Button(form, text=f"{kind} Money", bg=GREEN, fg="white",
                           font=FONT_BOLD, relief="flat", cursor="hand2",
                           activebackground="#166B3A", padx=18, pady=6,
                           command=lambda: self._submit_money(
                               kind, combo, accounts, amount, note))
        submit.pack(anchor="w", padx=22, pady=(0, 16))

        hint = ("Tip: the deposit is recorded in the passbook immediately."
                if is_deposit else
                "Tip: withdrawals are combined with today's earlier withdrawals\n"
                "and may never exceed the account's daily limit.")
        tk.Label(body, text=hint, bg=BG, fg=MUTED, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(12, 0))

    def _submit_money(self, kind, combo, accounts, amount_entry, note_entry):
        amount_text = amount_entry.get()
        try:
            account = self._chosen_account(combo, accounts)
            service_call = (self.service.deposit if kind == "Deposit"
                            else self.service.withdraw)
            new_balance, occurred = service_call(
                account.account_no, amount_text, note_entry.get())
        except (BankingError, sqlite3.Error) as error:
            messagebox.showerror("SmartBank", _error_text(error), parent=self.root)
            return
        amount_entry.delete(0, "end")
        messagebox.showinfo(
            f"{kind} Successful",
            f"{kind} successful for {account.account_no}.\n\n"
            f"Amount        : ₹{amount_text.strip()}\n"
            f"New Balance   : {format_paise(int(new_balance))}\n"
            f"Recorded At   : {occurred}",
            parent=self.root)

    # ================================================================== #
    # Balance Enquiry
    # ================================================================== #
    def _balance_page(self):
        page = self._page()
        body = self._page_header(page, "Balance Enquiry", "Check the current balance of any account")
        result = tk.Frame(body, bg=BG)
        result.pack(fill="x")
        self._balance_result_area = result
        self._render_balance_area(None)

    def _render_balance_area(self, account):
        area = self._balance_result_area
        for widget in area.winfo_children():
            widget.destroy()
        card = self._card(area)
        card.pack(anchor="w", fill="x")
        if account is None:
            tk.Label(card, text="Select an account below and press “Check Balance”.",
                     bg=CARD, fg=MUTED, font=FONT).pack(anchor="w", padx=20, pady=18)
        else:
            tk.Label(card, text=account.holder_name + "  ·  " + account.account_no,
                     bg=CARD, fg=MUTED, font=FONT).pack(anchor="w", padx=20, pady=(16, 2))
            tk.Label(card, text=account.balance, bg=CARD, fg=GREEN,
                     font=("Helvetica", 30, "bold")).pack(anchor="w", padx=20, pady=(0, 14))
        form = self._card(area)
        form.pack(anchor="w", fill="x", pady=(16, 0))
        combo, accounts = self._account_picker(form)
        button = tk.Button(form, text="Check Balance", bg=GREEN, fg="white",
                           font=FONT_BOLD, relief="flat", cursor="hand2",
                           activebackground="#166B3A", padx=18, pady=6,
                           command=lambda: self._check_balance(combo, accounts))
        button.pack(anchor="w", padx=20, pady=(4, 16))

    def _check_balance(self, combo, accounts):
        try:
            account = self._chosen_account(combo, accounts)
        except (BankingError, sqlite3.Error) as error:
            messagebox.showerror("SmartBank", _error_text(error), parent=self.root)
            return
        self._render_balance_area(self.service.get_account(account.account_no))

    # ================================================================== #
    # Account Information
    # ================================================================== #
    def _account_info_page(self):
        page = self._page()
        body = self._page_header(page, "Account Information",
                                 "Full details of one account")
        self._info_result_area = tk.Frame(body, bg=BG)
        self._info_result_area.pack(fill="x")
        self._render_info_area(None)

    def _render_info_area(self, account):
        area = self._info_result_area
        for widget in area.winfo_children():
            widget.destroy()
        card = self._card(area)
        card.pack(anchor="w", fill="x")
        if account is None:
            tk.Label(card, text="Select an account below and press “Show Details”.",
                     bg=CARD, fg=MUTED, font=FONT).pack(anchor="w", padx=20, pady=18)
        else:
            status = self.service.daily_status(account.account_no)
            rows = [
                ("Account Number", account.account_no),
                ("Holder Name", account.holder_name),
                ("Created On", account.created_at),
                ("Current Balance", account.balance),
                ("Daily Withdrawal Limit", account.daily_limit),
                (f"Withdrawn on {status['today']}", format_paise(status["used"])),
                ("Remaining Allowance Today", format_paise(status["remaining"])),
            ]
            inner = tk.Frame(card, bg=CARD)
            inner.pack(padx=24, pady=16, anchor="w")
            for label, value in rows:
                row = tk.Frame(inner, bg=CARD)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=label, bg=CARD, fg=MUTED, font=FONT, width=28,
                         anchor="w").pack(side="left")
                tk.Label(row, text=value, bg=CARD, fg=TEXT,
                         font=FONT_BOLD, anchor="w").pack(side="left")
        form = self._card(area)
        form.pack(anchor="w", fill="x", pady=(16, 0))
        combo, accounts = self._account_picker(form)
        button = tk.Button(form, text="Show Details", bg=GREEN, fg="white",
                           font=FONT_BOLD, relief="flat", cursor="hand2",
                           activebackground="#166B3A", padx=18, pady=6,
                           command=lambda: self._show_details(combo, accounts))
        button.pack(anchor="w", padx=20, pady=(4, 16))

    def _show_details(self, combo, accounts):
        try:
            account = self._chosen_account(combo, accounts)
        except (BankingError, sqlite3.Error) as error:
            messagebox.showerror("SmartBank", _error_text(error), parent=self.root)
            return
        self._render_info_area(self.service.get_account(account.account_no))

    # ================================================================== #
    # Passbook (From–To)
    # ================================================================== #
    def _passbook_page(self):
        page = self._page()
        body = self._page_header(page, "Passbook (From–To)",
                                 "Statement of transactions for a date range")

        options = self._card(body)
        options.pack(fill="x")
        top = tk.Frame(options, bg=CARD)
        top.pack(fill="x", padx=20, pady=12)

        today = datetime.date.today()
        default_start = today.replace(day=1).strftime("%Y-%m-%d")

        combo, accounts = self._account_picker(top)
        date_row = tk.Frame(top, bg=CARD)
        date_row.pack(fill="x", pady=(10, 0))

        start_entry, end_entry = self._date_fields(date_row, default_start)

        button = tk.Button(options, text="Show Statement", bg=GREEN, fg="white",
                           font=FONT_BOLD, relief="flat", cursor="hand2",
                           activebackground="#166B3A", padx=18, pady=6,
                           command=lambda: self._show_passbook(
                               body, combo, accounts, start_entry, end_entry))
        button.pack(anchor="w", padx=20, pady=(0, 14))

    def _date_fields(self, parent, default_start):
        today = datetime.date.today().strftime("%Y-%m-%d")
        fields = []
        for title, value in (("From date (YYYY-MM-DD)", default_start),
                             ("To date (YYYY-MM-DD)", today)):
            box = tk.Frame(parent, bg=CARD)
            box.pack(side="left", padx=(0, 20))
            tk.Label(box, text=title, bg=CARD, fg=MUTED,
                     font=FONT_SMALL).pack(anchor="w")
            entry = tk.Entry(box, font=FONT, width=14, bg="white",
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=NAVY, relief="flat")
            entry.insert(0, value)
            entry.pack(ipady=4)
            fields.append(entry)
        return fields[0], fields[1]

    def _show_passbook(self, body, combo, accounts, start_entry, end_entry):
        try:
            account = self._chosen_account(combo, accounts)
            rows = self.service.passbook(
                account.account_no, start_entry.get(), end_entry.get())
        except (BankingError, sqlite3.Error) as error:
            messagebox.showerror("SmartBank", _error_text(error), parent=self.root)
            return
        start_text, end_text = start_entry.get(), end_entry.get()

        # only clear the old statement AFTER the account, dates and rows were
        # resolved, because clearing removes the widgets this handler reads from
        for widget in body.winfo_children():
            widget.destroy()

        panel = self._card(body)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text=f"Passbook — {account.account_no} ({account.holder_name})"
                             f"   {start_text} to {end_text}",
                 bg=CARD, fg=TEXT, font=FONT_H2).pack(anchor="w", padx=16, pady=(14, 4))

        tree = self._tree(
            panel,
            ["date", "type", "note", "debit", "credit", "balance"],
            {
                "date": ("Date & Time", 150, "w"),
                "type": ("Type", 90, "w"),
                "note": ("Description", 220, "w"),
                "debit": ("Debit", 100, "e"),
                "credit": ("Credit", 100, "e"),
                "balance": ("Balance After", 110, "e"),
            },
        )
        footer = tk.Frame(panel, bg=CARD)
        footer.pack(fill="x", padx=16, pady=(2, 14))

        if not rows:
            tk.Label(panel, text="No transactions found in this date range.",
                     bg=CARD, fg=MUTED, font=FONT).pack(anchor="w", padx=16, pady=10)
            return

        total_debit = total_credit = 0
        for tx in rows:
            debit = format_paise(tx.amount_paise) if tx.transaction_type == "WITHDRAWAL" else ""
            credit = format_paise(tx.amount_paise) if tx.transaction_type == "DEPOSIT" else ""
            if tx.transaction_type == "WITHDRAWAL":
                total_debit += tx.amount_paise
            else:
                total_credit += tx.amount_paise
            tree.insert("", "end", tags=(tx.transaction_type,), values=(
                tx.occurred_at, self._type_label(tx.transaction_type), tx.note or "—",
                debit, credit, tx.balance_after))

        summary = (f"Transactions: {len(rows)}    "
                   f"Total Credit: {format_paise(total_credit)}    "
                   f"Total Debit: {format_paise(total_debit)}")
        tk.Label(footer, text=summary, bg=CARD, fg=MUTED, font=FONT).pack(side="left")
        export = tk.Button(footer, text="Export to CSV", bg=NAVY, fg="white",
                           font=FONT_BOLD, relief="flat", cursor="hand2",
                           activebackground=NAVY_DARK, padx=14, pady=4,
                           command=lambda: self._export_passbook_csv(
                               account, rows))
        export.pack(side="right")

    def _export_passbook_csv(self, account, rows):
        default_name = f"passbook_{account.account_no}.csv"
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export passbook to CSV",
            defaultextension=".csv", initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Account Number", account.account_no])
                writer.writerow(["Holder Name", account.holder_name])
                writer.writerow([])
                writer.writerow(["Date & Time", "Type", "Description",
                                 "Debit", "Credit", "Balance After"])
                for tx in rows:
                    debit = tx.amount if tx.transaction_type == "WITHDRAWAL" else ""
                    credit = tx.amount if tx.transaction_type == "DEPOSIT" else ""
                    writer.writerow([tx.occurred_at, self._type_label(tx.transaction_type),
                                     tx.note, debit, credit, tx.balance_after])
        except OSError as error:
            messagebox.showerror("SmartBank", f"Could not save file:\n{error}",
                                 parent=self.root)
            return
        messagebox.showinfo("Export Complete",
                            f"Passbook exported to:\n{path}", parent=self.root)

    # ================================================================== #
    def _confirm_exit(self):
        if messagebox.askokcancel("SmartBank", "Exit SmartBank?", parent=self.root):
            self.root.destroy()


def _error_text(error):
    return str(error) if isinstance(error, BankingError) else f"Database error: {error}"
