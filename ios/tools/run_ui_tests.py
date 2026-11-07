#!/usr/bin/env python3
"""Run the iPhone UI tests in ios/PearlUITests, with real taps.

    python3 ios/tools/run_ui_tests.py

Everything it uses is temporary and goes away afterwards: a local server with a
throwaway database of Pearl's guesses, and a simulator of its own, so your data
and your simulators aren't touched. Exits non-zero if a test fails.

The app reaches that server through a proxy on port 5051 that delays each reply
by LATENCY, as the hosted server's replies are delayed. At localhost speed a
reply can land before SwiftUI draws, and that hid the blank category sheet: it
only failed once the replies arrived apart, as they do on a phone.
"""

from __future__ import annotations

import http.client
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PORT = 5051
SERVER_PORT = 5052
# Between the hosted replies seen on a phone (2026-11-06).
LATENCY = 0.3
DEVICE = "com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro"


def seed(db_path: str) -> None:
    """Guesses for two merchants, and today's Quick sort offer already used so
    it doesn't open on launch and hide what the tests walk through."""
    sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
    from finance import quick_sort
    from finance.store import Store
    from test_safe_to_spend import tx

    def guess(days_ago: int, merchant: str, amount: float, category: str):
        day = (date.today() - timedelta(days=days_ago)).isoformat()
        return tx(day, merchant, amount, category, category_source="issuer",
                  raw={"category_confidence": "LOW"})

    store = Store(db_path)
    store.add_transactions([
        guess(1, "Uber Eats", 25.00, "Dining"),
        guess(2, "Uber Eats", 18.40, "Dining"),
        guess(3, "Loblaws", 56.10, "Groceries"),
    ])
    store.set_setting(quick_sort.SHOWN_KEY, date.today().isoformat())


class SlowProxy(BaseHTTPRequestHandler):
    """Forwards to the test server, each reply LATENCY late. A test can POST to
    /__test/categories/fail or /ok to have the categories refused, or not."""

    refuse_categories = False

    def answer(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def forward(self) -> None:
        if self.path.startswith("/__test/categories/"):
            SlowProxy.refuse_categories = self.path.endswith("/fail")
            self.answer(200)
            return
        time.sleep(LATENCY)
        if SlowProxy.refuse_categories and self.path.startswith("/api/categories"):
            self.answer(503)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        upstream = http.client.HTTPConnection("localhost", SERVER_PORT, timeout=60)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection")}
        upstream.request(self.command, self.path, body, headers)
        reply = upstream.getresponse()
        content = reply.read()
        self.send_response(reply.status)
        for key, value in reply.getheaders():
            if key.lower() not in ("connection", "transfer-encoding", "content-length", "date", "server"):
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        upstream.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = forward

    def log_message(self, *args) -> None:
        pass


def newest_ios_runtime() -> str:
    out = subprocess.run(["xcrun", "simctl", "list", "runtimes"], capture_output=True, text=True, check=True).stdout
    found = [line.rsplit(" - ", 1)[-1].strip() for line in out.splitlines() if line.startswith("iOS ")]
    if not found:
        sys.exit("No iOS simulator runtime is installed.")
    return found[-1]


def wait_for_server(server: subprocess.Popen) -> None:
    for _ in range(60):
        if server.poll() is not None:
            sys.exit("The test server stopped while starting.")
        try:
            urllib.request.urlopen(f"http://localhost:{SERVER_PORT}/api/auth/status", timeout=1)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    sys.exit("The test server didn't start.")


def main() -> int:
    runtime = os.environ.get("PEARL_TEST_RUNTIME") or newest_ios_runtime()
    with tempfile.TemporaryDirectory(prefix="pearl-ui-tests") as tmp:
        db_path = os.path.join(tmp, "ledger.db")
        seed(db_path)
        env = {**os.environ, "LEDGER_DB": db_path, "PORT": str(SERVER_PORT), "PEARL_PWNED_CHECK": "0",
               "SPENDIE_SECRET_KEY": "ui-test-key-that-is-definitely-long-enough"}
        with open(os.path.join(tmp, "server.log"), "w") as log:
            server = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=log, stderr=log)
        udid = None
        proxy = ThreadingHTTPServer(("localhost", PORT), SlowProxy)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        try:
            wait_for_server(server)
            udid = subprocess.run(["xcrun", "simctl", "create", "Pearl UI tests", DEVICE, runtime],
                                  capture_output=True, text=True, check=True).stdout.strip()
            result = subprocess.run(
                ["xcodebuild", "test", "-project", "Pearl.xcodeproj", "-scheme", "Pearl",
                 "-destination", f"id={udid}", "-derivedDataPath", os.path.join(tmp, "build"),
                 *sys.argv[1:]],
                cwd=os.path.join(ROOT, "ios"), capture_output=True, text=True)
            keep = ("Test Case", "error:", "XCTAssert", "** TEST", "** BUILD", "Executed ")
            for line in result.stdout.splitlines() + result.stderr.splitlines():
                if any(k in line for k in keep):
                    print(line)
            return result.returncode
        finally:
            proxy.shutdown()
            server.terminate()
            server.wait(timeout=10)
            if udid:
                subprocess.run(["xcrun", "simctl", "shutdown", udid], capture_output=True)
                subprocess.run(["xcrun", "simctl", "delete", udid], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
