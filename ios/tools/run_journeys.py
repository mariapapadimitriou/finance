#!/usr/bin/env python3
"""Run testingBOT's person journeys (ios/PearlUITests/PersonJourneysUITests.swift)
against Pearl's demo data, with real taps.

    python3 ios/tools/run_journeys.py                       # every journey
    python3 ios/tools/run_journeys.py testSplitADinnerEvenlyWithTwoFriends
    python3 ios/tools/run_journeys.py --text accessibility-extra-large testX
    python3 ios/tools/run_journeys.py --out /some/folder testX

Like run_ui_tests.py, everything is throwaway: a local server on a temporary
database (DATABASE_URL is removed from the environment, so the real database
can't be reached), the slow proxy on port 5051, and a simulator of its own.
The difference is the data: the demo ledger (sample_data.generate.load_demo,
about 1,000 card rows over 14 months) plus what the journeys need that the
demo cards don't have:

- a chequing account with two Interac e-Transfers in, to link as paybacks;
- a card that the joint journey sets to joint, with a $100.00 purchase on it;
- a few low-confidence guesses, so Quick sort and Needs a look have cards;
- a take-home pay and saving goal, so Home has an Allowance.

Each journey gets a fresh database and server, so they don't depend on each
other's order. Screenshots and the accessibility tree at each step go to
--out (default: a pearl-journey-shots folder in the system temp dir, never the
repo). The build is kept in --build so later runs skip it; pass --rebuild
after changing the app or the journeys.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, timedelta
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE]
import run_ui_tests as _R  # noqa: E402
from run_ui_tests import DEVICE, SlowProxy, newest_ios_runtime, wait_for_server  # noqa: E402
# testingBOT: its own ports, so it never meets engBOT's runs.
PORT = int(os.environ.get("PEARL_TBOT_PORT", "5051"))
SERVER_PORT = PORT + 1
_R.PORT, _R.SERVER_PORT = PORT, SERVER_PORT

SUITE = "PearlUITests/PersonJourneysUITests"
SIM_NAME = "Pearl journeys"


def seed(db_path: str) -> None:
    sys.path[:0] = [ROOT]
    from finance import quick_sort
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    from sample_data.generate import load_demo

    store = Store(db_path)
    load_demo(store)
    today = date.today()

    def day(n: int) -> str:
        return (today - timedelta(days=n)).isoformat()

    def load(rows, account, name, kind):
        txns = [Transaction(date=when, description=desc, amount=amt, account_id=account,
                            account_name=name, raw={"account_type": kind, **(raw or {})})
                for when, desc, amt, raw in rows]
        ingest(store, IngestResult(transactions=txns, account_id=account))

    low = {"category_confidence": "LOW"}
    # Money in from friends: what a payback looks like at a Canadian bank.
    load([(day(1), "E-TRANSFER FROM PRIYA SHAH", -42.50, None),
          (day(2), "INTERAC E-TRF FROM SAM LEE", -30.00, None)],
         "td_chq_2210", "TD Chequing ••2210", "depository")
    # The card the joint journey sets to joint.
    load([(day(3), "COSTCO WHOLESALE #552", 100.00, None),
          (day(5), "LOBLAWS #1123", 64.20, None)],
         "scotia_visa_8830", "Scotiabank Visa ••8830", "credit")
    # A dinner for the payback journeys: Priya's $42.50 and Sam's $30.00
    # above are their shares of it, and Jo's $15.00 never comes.
    load([(day(4), "TST* GUSTO 504", 127.50, None)], "amex_1004", "American Express ••1004", "credit")
    # Guesses Pearl isn't sure of: Quick sort's cards.
    load([(day(1), "SQ *CORNER STORE 22", 18.40, low),
          (day(2), "PAYPAL *MAKERSMKT", 56.10, low),
          (day(2), "TST* LUCKY NOODLE", 33.75, low),
          (day(4), "SP * NORTHSHOP CA", 89.00, low),
          (day(6), "CITY PARKING 0042", 12.00, low),
          (day(7), "BRIGHT DENTAL CLINIC", 140.00, low)],
         "amex_1004", "American Express ••1004", "credit")
    # testingBOT (TEST-18): Pizza Nova $120.00 split five ways; Priya, Sam
    # and Jo each send $25.00, Alex never does. TEST-18b: a $100.00 dinner
    # where Sam sends $20.00 and Priya $40.00.
    load([(day(3), "PIZZA NOVA #112", 120.00, None),
          (day(2), "BAR ISABEL TORONTO", 100.00, None)], "amex_1004", "American Express ••1004", "credit")
    load([(day(2), "E-TRANSFER FROM PRIYA SHAH", -25.00, None),
          (day(2), "INTERAC E-TRF FROM SAM LEE", -25.00, None),
          (day(1), "E-TRANSFER FROM JO PARK", -25.00, None),
          (day(1), "INTERAC E-TRF FROM SAM LEE", -20.00, None),
          (day(1), "E-TRANSFER FROM PRIYA SHAH", -40.00, None)],
         "td_chq_2210", "TD Chequing ••2210", "depository")
    # TEST-31: Pai Northern Thai $120.00 split with Sam ($60.00 each), and
    # Northwind (work) sending $60.00 for her share, not linked yet, so
    # What did this pay back? offers "Your share of Pai Northern Thai".
    load([(day(2), "PAI NORTHERN THAI", 120.00, None)], "amex_1004", "American Express ••1004", "credit")
    load([(day(1), "NORTHWIND LTD EXPENSES", -60.00, None)], "td_chq_2210", "TD Chequing ••2210", "depository")
    pai = next(t for t in store.all_transactions() if t.description == "PAI NORTHERN THAI")
    store.set_split(pai.fingerprint, "even", [{"name": "Sam", "amount": 60.0}], True)
    store.set_share(pai.fingerprint, 60.0)
    # TEST-31 Money back: Joey King St $90.00 split with Priya ($45.00 each),
    # and the restaurant's $45.00 back on her part, not linked yet.
    load([(day(3), "JOEY KING ST", 90.00, None)], "amex_1004", "American Express ••1004", "credit")
    load([(day(1), "JOEY KING ST REFUND", -45.00, None)], "amex_1004", "American Express ••1004", "credit")
    joey = next(t for t in store.all_transactions() if t.description == "JOEY KING ST")
    store.set_split(joey.fingerprint, "even", [{"name": "Priya", "amount": 45.0}], True)
    store.set_share(joey.fingerprint, 45.0)
    store.set_setting("monthly_income", 5200.0)
    store.set_setting("savings_target", 900.0)
    # Today's Quick sort offer already used, so it doesn't open on launch
    # and cover Home; the Home journey opens it with Sort now.
    store.set_setting(quick_sort.SHOWN_KEY, today.isoformat())


# Fewer taps (P5, P8, P11): money in with no name on it, for Who sent this?.
FEWER = "testFewer"


def seed_fewer(db_path: str) -> None:
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    store = Store(db_path)
    when = (date.today() - timedelta(days=1)).isoformat()
    ingest(store, IngestResult(transactions=[Transaction(
        date=when, description="INTERAC E-TRANSFER", amount=-60.00, account_id="td_chq_2210",
        account_name="TD Chequing ••2210", raw={"account_type": "depository"})], account_id="td_chq_2210"))
    # P15b (board gaps): gifts she bought at a pet shop, so searching the
    # shop's name says "Also try: Gifts & Charity".
    ingest(store, IngestResult(transactions=[Transaction(
        date=(date.today() - timedelta(days=d)).isoformat(), description="PETSMART 0412", amount=34.99,
        account_id="amex_1004", account_name="American Express ••1004", raw={"account_type": "credit"})
        for d in (9, 23)], account_id="amex_1004"))
    for t in store.all_transactions():
        if t.description == "PETSMART 0412":
            store.set_transaction_category(t.fingerprint, "Gifts & Charity")


# Journeys about the older ones (REFRESH-17) start from this bill too.
OLDER = "testOlderOnes"


def seed_older(db_path: str) -> None:
    """A bill from a joint account, a different amount each month: two still
    asked about, eight left as transfers for their age."""
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    store = Store(db_path)
    today = date.today()
    rows = [Transaction(date=(today - timedelta(days=15 + 30 * i)).isoformat(), description="MAPLE COURT",
                        amount=70.20 + 4 * i, account_id="joint_1123", account_name="Joint ••1123",
                        raw={"account_type": "depository",
                             "issuer_category": "TRANSFER_OUT_ACCOUNT_TRANSFER"}) for i in range(10)]
    ingest(store, IngestResult(transactions=rows, account_id="joint_1123"))
    # A name every transfer shares: no rule, and the page says so (T-03r).
    common = Transaction(date=(today - timedelta(days=3)).isoformat(), description="INTERNET WITHDRAWAL",
                         amount=95.0, account_id="td_chq_2210", account_name="TD Chequing ••2210",
                         raw={"account_type": "depository", "issuer_category": "TRANSFER_OUT_ACCOUNT_TRANSFER"})
    ingest(store, IngestResult(transactions=[common], account_id="td_chq_2210"))
    store.set_joint("joint_1123", "Sister")
    with store.conn() as c:
        c.execute("UPDATE joint_accounts SET share = 50, people = '[\"Sam\"]' WHERE account_id = 'joint_1123'")


# Overpaid and underpaid shares (REFRESH-18): Corner Bistro with Georgia Klev,
# and what she and the others sent, for each journey.
OVER = {
    "testOverRoundedUp": (59.54, {"Georgia Klev": 19.77, "Priya": 20.0}, [("Georgia Klev", 20.0)]),
    "testOverRoundedDown": (59.54, {"Georgia Klev": 19.77, "Priya": 20.0}, [("Priya", 19.0)]),
    "testOverSaidFromThePurchase": (80.0, {"Georgia Klev": 40.0}, [("Georgia Klev", 55.0)]),
    "testOverTwoPayments": (80.0, {"Georgia Klev": 40.0}, [("Georgia Klev", 25.0), ("Georgia Klev", 15.0)]),
    "testOverLetGoThenPaid": (80.0, {"Georgia Klev": 40.0}, [("Georgia Klev", 25.0), ("Georgia Klev", 15.0)]),
    "testOverTwoGeorgias": (120.0, {"Georgia Klev": 40.0, "Georgia Pappas": 40.0},
                            [("Georgia Klev", 55.0), ("Georgia Pappas", 25.0)]),
    "testOverDeposit": (80.0, {"Georgia Klev": 40.0}, [("Georgia Klev", 55.0)]),
    "testOverNeedsALook": (80.0, {"Georgia Klev": 40.0}, [("Georgia Klev", 55.0)]),
    # P16/P17 (TP-P16-OwedButton, TP-P17-Owed): Owed to you from the split
    # purchase and from Home; Priya pays her share, Georgia still owes.
    "testOverOwedOrganized": (90.0, {"Georgia Klev": 30.0, "Priya": 30.0}, []),
    # P17 on the simulator (board gaps, 2026-11-27): many people (the demo's
    # splits and this one), one person, and nobody, each with Paid back.
    "testOverOwedLooksMany": (90.0, {"Georgia Klev": 30.0, "Priya": 30.0}, []),
    "testOverOwedLooksOne": (90.0, {"Georgia Klev": 30.0, "Priya": 30.0}, []),
    "testOverOwedLooksNobody": (90.0, {"Georgia Klev": 30.0, "Priya": 30.0}, []),
}


def seed_over(db_path: str, journey: str) -> None:
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    whole, people, sent = OVER[journey]
    store = Store(db_path)
    today = date.today()
    # Only these people's money in is Suggested, so the demo's own goes.
    store.forget_rows({t.fingerprint for t in store.all_transactions()
                       if t.account_id == "td_chq_2210" and "PRIYA" in t.description.upper()})
    bistro = Transaction(date=(today - timedelta(days=1)).isoformat(), description="CORNER BISTRO", merchant="Corner Bistro",
                         amount=whole, category="Dining", account_id="amex_1004",
                         account_name="American Express ••1004", raw={"account_type": "credit"})
    ingest(store, IngestResult(transactions=[bistro], account_id="amex_1004"))
    ingest(store, IngestResult(transactions=[
        Transaction(date=today.isoformat() if i else (today - timedelta(days=1)).isoformat(),
                    description=f"E-TRANSFER FROM {name.upper()}", amount=-amount, account_id="td_chq_2210",
                    account_name="TD Chequing ••2210", raw={"account_type": "depository"})
        for i, (name, amount) in enumerate(sent)], account_id="td_chq_2210"))
    cid = next(t.fingerprint for t in store.all_transactions() if t.description == "CORNER BISTRO")
    store.set_split(cid, "amount", [{"name": n, "amount": a} for n, a in people.items()], True)
    store.set_share(cid, round(whole - sum(people.values()), 2))
    store.set_transaction_category(cid, "Dining")
    if journey == "testOverOwedOrganized" or journey.startswith("testOverOwedLooks"):
        # Priya paid her share in cash: Paid back this month, under Also.
        store.add_split_cash(cid, "Priya", 30.0, today.isoformat())
    if journey in ("testOverOwedLooksOne", "testOverOwedLooksNobody"):
        # Only Corner Bistro's split is left: Georgia owes (P17c), or has
        # paid too (P17d).
        for other in store.splits():
            if other != cid:
                store.clear_split(other)
        if journey == "testOverOwedLooksNobody":
            store.add_split_cash(cid, "Georgia Klev", 30.0, today.isoformat())


# Split my part in Options: Corner Bistro and Harbour Furniture on a joint
# card at 50/50, Lantern Books on one that's all hers unless she marks it.
JOINT = "testJointSplitInOptions"


def seed_joint(db_path: str) -> None:
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    store = Store(db_path)
    day = (date.today() - timedelta(days=1)).isoformat()
    for account, rows in (("joint_half", [("CORNER BISTRO", 80.0), ("HARBOUR FURNITURE", 120.0)]),
                          ("joint_mine", [("LANTERN BOOKS", 64.2)])):
        ingest(store, IngestResult(account_id=account, transactions=[
            Transaction(date=day, description=name, merchant=name.title(), amount=amount, category="Dining",
                        account_id=account, account_name="Joint Visa", raw={"account_type": "credit"})
            for name, amount in rows]))
        store.set_joint(account, "Sister")
    with store.conn() as c:
        c.execute("UPDATE joint_accounts SET people = '[\"Sam\"]'")
        c.execute("UPDATE joint_accounts SET share = 50 WHERE account_id = 'joint_half'")
    for t in store.all_transactions():
        if t.account_id in ("joint_half", "joint_mine"):
            store.set_transaction_category(t.fingerprint, "Dining")


# Ask Pearl (THL-308): two credit cards with limits and due days, for PC-26d.
# The server never has a real key here: no model is ever called. With
# PEARL_ASK_SIMPLE=1 it gets a key that is never sent and a $0 monthly cap,
# so every answer is the built-in one with PC-23's quiet line.
ASK = "testAskPearl"


def seed_ask(db_path: str) -> None:
    import json
    from finance.store import Store
    store = Store(db_path)
    today = date.today().isoformat()
    store.note_account("scotia_visa_8830", name="Scotiabank Visa ••8830", account_type="credit",
                       subtype="credit card")
    store.note_account("amex_1004", name="American Express ••1004", account_type="credit",
                       subtype="credit card")
    store.set_balance("scotia_visa_8830", 1840.00, None, 5000, "CAD", today)
    store.set_balance("amex_1004", 2710.00, None, 3000, "CAD", today)
    store.set_setting("debt_details", json.dumps({"scotia_visa_8830": {"due_day": 3},
                                                  "amex_1004": {"due_day": 14}}))


# AI Phase 4, part 1 (THL-309): a price rise on a bill she counts (WL-20),
# the demo's subscriptions she never answered (WL-21), a card payment that
# took six days (TR-30), and two trips months ago (TR-20).
AI = "testAIDetections"


def seed_ai(db_path: str) -> None:
    from finance import income_bills as ib, pattern_sort
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    store = Store(db_path)
    today = date.today()

    def day(n: int) -> str:
        return (today - timedelta(days=n)).isoformat()


    def load(rows, account, name, kind):
        ingest(store, IngestResult(transactions=[
            Transaction(date=when, description=desc, amount=amt, account_id=account, account_name=name,
                        raw={"account_type": kind, **(raw or {})}) for when, desc, amt, raw in rows],
            account_id=account))

    streaming = {"issuer_category": "ENTERTAINMENT_TV_AND_MOVIES"}
    load([(day(3 + 30 * n), "VIDEOSTREAM.COM 866", 18.99 if n == 0 else 16.49, streaming) for n in range(8, -1, -1)],
         "amex_1004", "American Express ••1004", "credit")
    # The six-day card payment: Pearl pairs within four by itself.
    load([(day(8), "ONLINE BANKING TRANSFER", 500.00, {"issuer_category": "TRANSFER_OUT_ACCOUNT_TRANSFER"})],
         "td_chq_2210", "TD Chequing ••2210", "depository")
    load([(day(2), "PAYMENT RECEIVED - THANK YOU", -500.00, {"issuer_category": "TRANSFER_IN_ACCOUNT_TRANSFER"})],
         "scotia_visa_8830", "Scotiabank Visa ••8830", "credit")
    # Two trips months ago: places she'd never been, and a flight before.
    for start, city, shops in ((240, "Lisbon", ["PASTELARIA BELEM", "TASCA DO CHICO", "MERCADO RIBEIRA",
                                                "TRAM 28 KIOSK", "LX FACTORY BOOKS"]),
                               (330, "Halifax", ["BLUENOSE DINER", "WATERFRONT LOBSTER", "SPRING GARDEN BOOKS",
                                                 "HALIFAX SEAPORT MKT"])):
        rows = [(day(start + 10), "SKYWAYS AIR 0142", 640.00, {"issuer_category": "TRAVEL_FLIGHTS"})]
        rows += [(day(start - i // 2), f"{s} {i}", 18.0 + 4.25 * i, {"city": city}) for i, s in enumerate(shops)]
        load(rows, "scotia_visa_8830", "Scotiabank Visa ••8830", "credit")
    # She counts the streaming bill (I-04), so its rise is worth a look.
    merchant = next(t.merchant for t in store.all_transactions() if t.description.startswith("VIDEOSTREAM"))
    state = ib.load(store)
    state["bills"][merchant] = {"state": "yes"}
    state["bills_on"] = day(200)
    ib.save(store, state)
    pattern_sort.switched_on(store)
    # Every other question skipped, so Quick sort is the new cards: the
    # recent trip, the pair, then the past trips (they come after the rest).
    from finance.quick_sort import questions
    from finance.review import for_store
    for key, _ in questions(for_store(store, today.isoformat())):
        if not key.startswith(("pair:", "trip:", "pat:")):
            store.skip_review(key)


# THL-309 (engBOT's SmartSortingUITests): Pearl sorts for you on Rules, a
# pattern she said yes to whose last row Smart sorted with Claude's words,
# and Smart's picks for the low-confidence guesses (a fake model, in the
# seed: no network). The journey turns Smart on, so they show.
SMART = "testSmartSorting"


def seed_smart(db_path: str) -> None:
    import json
    from finance import pattern_sort as ps
    from finance import smart_sort
    from finance.ai import client as client_mod
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    store = Store(db_path)
    today = date.today()

    def load(rows):
        ingest(store, IngestResult(transactions=[
            Transaction(date=(today - timedelta(days=n)).isoformat(), description=desc, amount=amt,
                        account_id="amex_1004", account_name="American Express ••1004",
                        raw={"account_type": "credit", "category_confidence": "LOW"})
            for n, desc, amt in rows], account_id="amex_1004"))

    load([(60 - i * 7, "NORTHSIDE PANTRY", 40.0 + i) for i in range(5)])
    for t in store.all_transactions():
        if t.description == "NORTHSIDE PANTRY":
            store.set_transaction_category(t.fingerprint, "Groceries")
    ps.switched_on(store)
    for ask in ps.pending(store, today.isoformat()):
        if ask["merchant"] and "Northside" in ask["merchant"]:
            ps.confirm(store, ask["id"], today.isoformat())
    load([(1, "NORTHSIDE PANTRY", 61.40)])

    class Fake:
        def send(self, *, model, system, messages, tools=None, max_tokens=1024, effort="low"):
            return client_mod.Reply(model=model, stop_reason="tool_use", tool_calls=[{
                "id": "t", "name": "pick", "input": {
                    "answer": tools[0]["input_schema"]["properties"]["answer"]["enum"][0],
                    "reason": "Your usual groceries, like your last [NUM1] at Northside Pantry."}}])

    store.set_setting(smart_sort.SMART_KEY, "1")
    smart_sort.run(store, today.isoformat(), base=store, user_id=0, client=Fake())
    store.set_setting(smart_sort.SMART_KEY, "")
    picks = {"SQ *CORNER STORE 22": "Groceries", "TST* LUCKY NOODLE": "Dining",
             "PAYPAL *MAKERSMKT": "Shopping", "SP * NORTHSHOP CA": "Shopping",
             "CITY PARKING 0042": "Transport", "BRIGHT DENTAL CLINIC": "Health"}
    guesses = smart_sort.guesses(store)
    for t in store.all_transactions():
        if t.description in picks:
            cat = picks[t.description]
            guesses[t.fingerprint] = {"case": "new", "allowed": [cat], "pick": cat, "agree": True,
                                      "answer": cat, "line": f"Looks like {t.merchant}, so {cat}.",
                                      "version": "1"}
    store.set_setting(smart_sort.GUESS_KEY, json.dumps(guesses, sort_keys=True))


# AP-HomeCalm (engBOT's GaugeUITests): a ledger with nothing to do, in place
# of the demo: three months of pay, rent and groceries, every row sorted.
CALM = "testGaugeCalm"


def seed_calm(db_path: str) -> None:
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.store import Store
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)
    store = Store(db_path)
    today = date.today()
    first = today.replace(day=1)
    rows = []
    for back in range(3, -1, -1):
        y, m = first.year, first.month - back
        while m < 1:
            y, m = y - 1, m + 12
        for d, desc, amt, cat in ((1, "NORTHWIND LTD PAYROLL", -2400.0, "Income"),
                                  (15, "NORTHWIND LTD PAYROLL", -2400.0, "Income"),
                                  (1, "PARKSIDE PROPERTIES", 1800.0, "Rent & Housing"),
                                  (3, "LOBLAWS", 120.0, "Groceries"), (9, "LOBLAWS", 135.0, "Groceries"),
                                  (12, "PAI NORTHERN THAI", 64.0, "Dining")):
            when = date(y, m, d)
            if when <= today:
                rows.append(Transaction(date=when.isoformat(), description=desc, amount=amt, account_id="td_chq_2210",
                                        account_name="TD Chequing ••2210", category=cat,
                                        raw={"account_type": "depository"}))
    ingest(store, IngestResult(transactions=rows, account_id="td_chq_2210"))
    by_desc = {r.description: r.category for r in rows}
    for t in store.all_transactions():
        store.set_transaction_category(t.fingerprint, by_desc.get(t.description, t.category or "Other"))
    store.set_setting("monthly_income", 4800.0)


def simulator(runtime: str, text: str, appearance: str = "light") -> str:
    # One simulator at a time (product owner): PEARL_SIM_UDID reuses one
    # that is already booted instead of booting "Pearl journeys" as well.
    udid = os.environ.get("PEARL_SIM_UDID") or None
    if udid is None:
        out = subprocess.run(["xcrun", "simctl", "list", "devices"], capture_output=True, text=True).stdout
        udid = next((line.split("(")[1].split(")")[0] for line in out.splitlines()
                     if line.strip().startswith(SIM_NAME + " (")), None)
    if udid is None:
        udid = subprocess.run(["xcrun", "simctl", "create", SIM_NAME, DEVICE, runtime],
                              capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["xcrun", "simctl", "boot", udid], capture_output=True)
    subprocess.run(["xcrun", "simctl", "bootstatus", udid, "-b"], capture_output=True)
    subprocess.run(["xcrun", "simctl", "ui", udid, "content_size", text], capture_output=True)
    subprocess.run(["xcrun", "simctl", "ui", udid, "appearance", appearance], capture_output=True)
    return udid


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("journeys", nargs="*", help="test method names; all if none")
    p.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "pearl-journey-shots"))
    p.add_argument("--build", default=None, help="derivedData folder (kept, so later runs skip the build)")
    p.add_argument("--text", default="large", help="Dynamic Type: large (the default), accessibility-extra-large, …")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--appearance", default="light", help="the simulator's light or dark")
    p.add_argument("--delete-simulator", action="store_true")
    p.add_argument("--suite", default=SUITE,
                   help="the test class, e.g. PearlUITests/Round1FixesUITests (engBOT's checks of the fixes)")
    args = p.parse_args()

    runtime = os.environ.get("PEARL_TEST_RUNTIME") or newest_ios_runtime()
    build = args.build or os.path.join(tempfile.gettempdir(), "pearl-journeys-build")
    ios = os.path.join(ROOT, "ios")
    if args.rebuild or not os.path.isdir(os.path.join(build, "Build", "Products")):
        r = subprocess.run(["xcodebuild", "build-for-testing", "-project", "Pearl.xcodeproj", "-scheme", "Pearl",
                            "-destination", "generic/platform=iOS Simulator", "-derivedDataPath", build],
                           cwd=ios, capture_output=True, text=True)
        if r.returncode:
            print("\n".join(l for l in r.stdout.splitlines() if "error:" in l) or r.stdout[-3000:])
            return r.returncode
    os.makedirs(args.out, exist_ok=True)
    udid = simulator(runtime, args.text, args.appearance)
    # No live AI calls from a journey (THL-308): the real key never reaches the server.
    env_base = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "ANTHROPIC_API_KEY")}

    proxy = ThreadingHTTPServer(("localhost", PORT), SlowProxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    journeys = args.journeys or [None]
    failed = 0
    try:
        for journey in journeys:
            with tempfile.TemporaryDirectory(prefix="pearl-journeys") as tmp:
                db_path = os.path.join(tmp, "ledger.db")
                seed(db_path)
                if journey and journey.startswith(OLDER):
                    seed_older(db_path)
                elif journey and journey.startswith(FEWER):
                    seed_fewer(db_path)
                elif journey == ASK:
                    seed_ask(db_path)
                    # PC-24 shows on a first open: nothing the app kept.
                    subprocess.run(["xcrun", "simctl", "uninstall", udid, "com.mariapapadimitriou.pearl"], capture_output=True)
                elif journey == AI:
                    seed_ai(db_path)
                    subprocess.run(["xcrun", "simctl", "uninstall", udid, "com.mariapapadimitriou.pearl"], capture_output=True)
                elif journey == CALM:
                    seed_calm(db_path)
                    subprocess.run(["xcrun", "simctl", "uninstall", udid, "com.mariapapadimitriou.pearl"], capture_output=True)
                elif journey == SMART:
                    seed_smart(db_path)
                    subprocess.run(["xcrun", "simctl", "uninstall", udid, "com.mariapapadimitriou.pearl"], capture_output=True)
                elif journey == JOINT:
                    seed_joint(db_path)
                    subprocess.run(["xcrun", "simctl", "uninstall", udid, "com.mariapapadimitriou.pearl"], capture_output=True)
                if journey in OVER:
                    seed_over(db_path, journey)
                    # Each has its own rows, so nothing the app kept is right.
                    subprocess.run(["xcrun", "simctl", "uninstall", udid, "com.mariapapadimitriou.pearl"], capture_output=True)
                env = {**env_base, "LEDGER_DB": db_path, "PORT": str(SERVER_PORT), "PEARL_PWNED_CHECK": "0",
                       "SPENDIE_SECRET_KEY": "ui-test-key-that-is-definitely-long-enough"}
                if journey == ASK and os.environ.get("PEARL_ASK_SIMPLE") == "1":
                    env.update({"ANTHROPIC_API_KEY": "sk-journey-never-sent", "PEARL_AI_MONTHLY_CAP_USD": "0"})
                log_path = os.path.join(args.out, f"server-{journey or 'all'}.log")
                with open(log_path, "w") as log:
                    server = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=log, stderr=log)
                try:
                    wait_for_server(server)
                    only = f"{args.suite}/{journey}" if journey else args.suite
                    test_env = {**env_base, "TEST_RUNNER_PEARL_SHOTS": args.out, "TEST_RUNNER_PEARL_PORT": str(PORT),
                                "TEST_RUNNER_PEARL_TEXT": args.text}
                    started = time.time()
                    r = subprocess.run(["xcodebuild", "test-without-building", "-project", "Pearl.xcodeproj",
                                        "-scheme", "Pearl", "-destination", f"id={udid}", "-derivedDataPath", build,
                                        f"-only-testing:{only}"],
                                       cwd=ios, capture_output=True, text=True, env=test_env)
                    keep = ("Test Case", "error:", "XCTAssert", "** TEST", "Executed ", "JOURNEY")
                    for line in r.stdout.splitlines() + r.stderr.splitlines():
                        if any(k in line for k in keep):
                            print(line)
                    print(f"-- {journey or 'all'}: exit {r.returncode} in {time.time() - started:.0f}s")
                    failed |= r.returncode != 0
                finally:
                    server.terminate()
                    server.wait(timeout=10)
    finally:
        proxy.shutdown()
        if args.delete_simulator:
            subprocess.run(["xcrun", "simctl", "shutdown", udid], capture_output=True)
            subprocess.run(["xcrun", "simctl", "delete", udid], capture_output=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
