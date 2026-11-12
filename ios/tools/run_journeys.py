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
from run_ui_tests import DEVICE, PORT, SERVER_PORT, SlowProxy, newest_ios_runtime, wait_for_server  # noqa: E402

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
    store.set_setting("monthly_income", 5200.0)
    store.set_setting("savings_target", 900.0)
    # Today's Quick sort offer already used, so it doesn't open on launch
    # and cover Home; the Home journey opens it with Sort now.
    store.set_setting(quick_sort.SHOWN_KEY, today.isoformat())


def simulator(runtime: str, text: str) -> str:
    out = subprocess.run(["xcrun", "simctl", "list", "devices"], capture_output=True, text=True).stdout
    udid = next((line.split("(")[1].split(")")[0] for line in out.splitlines()
                 if line.strip().startswith(SIM_NAME + " (")), None)
    if udid is None:
        udid = subprocess.run(["xcrun", "simctl", "create", SIM_NAME, DEVICE, runtime],
                              capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["xcrun", "simctl", "boot", udid], capture_output=True)
    subprocess.run(["xcrun", "simctl", "bootstatus", udid, "-b"], capture_output=True)
    subprocess.run(["xcrun", "simctl", "ui", udid, "content_size", text], capture_output=True)
    subprocess.run(["xcrun", "simctl", "ui", udid, "appearance", "light"], capture_output=True)
    return udid


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("journeys", nargs="*", help="test method names; all if none")
    p.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "pearl-journey-shots"))
    p.add_argument("--build", default=None, help="derivedData folder (kept, so later runs skip the build)")
    p.add_argument("--text", default="large", help="Dynamic Type: large (the default), accessibility-extra-large, …")
    p.add_argument("--rebuild", action="store_true")
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
    udid = simulator(runtime, args.text)
    env_base = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}

    proxy = ThreadingHTTPServer(("localhost", PORT), SlowProxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    journeys = args.journeys or [None]
    failed = 0
    try:
        for journey in journeys:
            with tempfile.TemporaryDirectory(prefix="pearl-journeys") as tmp:
                db_path = os.path.join(tmp, "ledger.db")
                seed(db_path)
                env = {**env_base, "LEDGER_DB": db_path, "PORT": str(SERVER_PORT), "PEARL_PWNED_CHECK": "0",
                       "SPENDIE_SECRET_KEY": "ui-test-key-that-is-definitely-long-enough"}
                log_path = os.path.join(args.out, f"server-{journey or 'all'}.log")
                with open(log_path, "w") as log:
                    server = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=log, stderr=log)
                try:
                    wait_for_server(server)
                    only = f"{args.suite}/{journey}" if journey else args.suite
                    test_env = {**env_base, "TEST_RUNNER_PEARL_SHOTS": args.out,
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
