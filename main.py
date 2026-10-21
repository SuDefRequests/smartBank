"""main.py — entry point for SmartBank.

Run with:  python main.py
The SQLite database (smartbank.db) is created next to this file on first
run and is reused afterwards, so data survives restarts.
"""

import os
import sys
import tkinter as tk

import database
from banking_service import BankingService
from gui import SmartBankApp


def main():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartbank.db")
    repository = database.DatabaseRepository(db_path)
    service = BankingService(repository)

    try:
        app = SmartBankApp(service)
    except tk.TclError as error:  # no display available (e.g. headless server)
        sys.exit(f"Cannot open the SmartBank window: {error}\n"
                 f"Run SmartBank on a computer with a graphical display.")

    app.run()
    repository.close()


if __name__ == "__main__":
    main()
