"""Generate realistic sample statements in three different issuer formats.

The point is not just to fill the screen: the generated history deliberately
contains every pattern the savings engine looks for — a subscription that raises
its price, a stack of streaming services, a daily coffee habit, delivery orders,
interest charges, a double-bill, and a category that drifts upward in the final
month. Running `--demo` should therefore produce a Savings tab with real
findings rather than an empty state.

    python -m sample_data.generate          # write CSVs to sample_data/
    python app.py --demo                    # generate and import in one step
"""

from __future__ import annotations

import csv
import io
import os
import random
from datetime import date, timedelta

SEED = 20260821
MONTHS = 14

HERE = os.path.dirname(os.path.abspath(__file__))


# ── Spending model ───────────────────────────────────────────────────────────
# (descriptor, low, high, times per month, which card)

AMEX, CHASE, CAPONE = "amex", "chase", "capone"

HABITS = [
    # Daily-ish coffee: the classic invisible annual cost.
    ("SQ *BLUE BOTTLE COFFEE 4471 OAKLAND CA", 5.25, 7.90, 17, AMEX),
    ("STARBUCKS STORE 08812 SAN FRANCISCO CA", 4.75, 9.40, 6, CHASE),
    # Groceries
    ("WHOLE FOODS MKT 10229 SAN FRANCISCO CA", 42.00, 165.00, 5, AMEX),
    ("TRADER JOE'S #178 SAN FRANCISCO CA", 28.00, 96.00, 3, CHASE),
    # Dining and delivery
    ("TST* NOPA RESTAURANT SAN FRANCISCO CA", 48.00, 190.00, 2, AMEX),
    ("CHIPOTLE 1892 SAN FRANCISCO CA", 12.50, 24.00, 3, CHASE),
    ("DOORDASH*THAI HOUSE SAN FRANCISCO CA", 28.00, 62.00, 4, CHASE),
    ("UBER EATS SAN FRANCISCO CA", 24.00, 71.00, 3, AMEX),
    # Transport
    ("UBER TRIP SAN FRANCISCO CA", 11.00, 38.00, 6, CHASE),
    ("LYFT *RIDE SAN FRANCISCO CA", 9.00, 31.00, 3, AMEX),
    ("SHELL OIL 57444103 SAN FRANCISCO CA", 38.00, 74.00, 2, CAPONE),
    # Shopping
    ("AMZN Mktp US*RT4XY9012 AMZN.COM/BILL WA", 14.00, 128.00, 6, AMEX),
    ("TARGET 00023981 SAN FRANCISCO CA", 22.00, 140.00, 2, CAPONE),
    # Bars
    ("ZEITGEIST BAR SAN FRANCISCO CA", 26.00, 78.00, 2, CHASE),
    # Health & personal
    ("WALGREENS #3841 SAN FRANCISCO CA", 8.00, 46.00, 2, CAPONE),
]

# (descriptor, amount, day of month, card, optional price change after N months)
SUBSCRIPTIONS = [
    ("NETFLIX.COM 866-579-7172 CA", 15.49, 4, AMEX, (7, 22.99)),   # price creep
    ("SPOTIFY USA NEW YORK NY", 11.99, 9, AMEX, (9, 13.99)),        # price creep
    ("HULU 877-8244858 CA", 17.99, 12, CHASE, None),
    ("DISNEY PLUS 888-9057888 CA", 13.99, 15, CHASE, None),
    ("HBO MAX 877-3512122 NY", 16.99, 18, AMEX, None),
    ("ADOBE *CREATIVE CLOUD SAN JOSE CA", 59.99, 21, CHASE, None),
    ("GITHUB.COM SAN FRANCISCO CA", 21.00, 6, AMEX, None),
    ("NOTION LABS INC SAN FRANCISCO CA", 10.00, 24, AMEX, None),
    ("EQUINOX SAN FRANCISCO CA", 215.00, 2, CAPONE, None),          # the zombie
    ("CLASSPASS NEW YORK NY", 79.00, 27, CAPONE, None),
    ("NYTIMES DIGITAL 800-6981234 NY", 17.00, 11, CHASE, None),
    ("APPLE.COM/BILL 866-712-7753 CA", 2.99, 19, AMEX, None),
]

FIXED_BILLS = [
    ("COMCAST CALIFORNIA 800-COMCAST", 89.99, 8, CAPONE),
    ("AT&T WIRELESS 800-331-0500 TX", 94.30, 14, CAPONE),
    ("PG&E ELECTRIC PAYMENT CA", 62.00, 20, CAPONE),
    ("STATE FARM INSURANCE 800-STATEFARM", 138.00, 3, CAPONE),
]

# Fees and interest: the highest-conviction finding the engine can produce.
FEES = [
    ("INTEREST CHARGE ON PURCHASES", 31.40, 26, CHASE),
    ("ANNUAL MEMBERSHIP FEE", 250.00, None, AMEX),      # once a year
    ("FOREIGN TRANSACTION FEE", 4.85, None, CHASE),     # occasional
    ("LATE FEE - PAYMENT DUE", 39.00, None, CHASE),     # occasional
]

INCOME = ("DIRECT DEPOSIT PAYROLL ACME CORP", 5850.00, 15)
PAYMENTS = ("ONLINE PAYMENT - THANK YOU", None, 25)


def _amt(rng, low, high):
    return round(rng.uniform(low, high), 2)


def _month_starts(months: int) -> list[date]:
    today = date.today()
    starts = []
    y, m = today.year, today.month
    for _ in range(months):
        starts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(starts)


def _safe_day(d: date, day: int) -> date:
    import calendar
    last = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, min(day, last))


def build_rows(seed: int = SEED) -> dict[str, list[dict]]:
    """Generate per-card transaction rows: {card: [{date, description, amount}]}."""
    rng = random.Random(seed)
    rows: dict[str, list[dict]] = {AMEX: [], CHASE: [], CAPONE: []}
    starts = _month_starts(MONTHS)
    today = date.today()

    def add(card, d: date, desc: str, amount: float):
        if d > today:
            return
        rows[card].append({"date": d, "description": desc, "amount": round(amount, 2)})

    for idx, start in enumerate(starts):
        is_last_month = idx == len(starts) - 1
        import calendar
        days_in = calendar.monthrange(start.year, start.month)[1]

        # ── Habits ──
        for desc, low, high, per_month, card in HABITS:
            count = max(0, int(rng.gauss(per_month, per_month * 0.22)))
            # Deliberate drift: dining and delivery climb in the final month so
            # the trend rule has something real to catch.
            if is_last_month and ("DOORDASH" in desc or "UBER EATS" in desc
                                  or "NOPA" in desc):
                count = int(count * 1.9)
            for _ in range(count):
                day = rng.randint(1, days_in)
                add(card, date(start.year, start.month, day), desc, _amt(rng, low, high))

        # ── Subscriptions ──
        for desc, base_amount, day, card, change in SUBSCRIPTIONS:
            amount = base_amount
            if change:
                after_months, new_amount = change
                if idx >= after_months:
                    amount = new_amount
            add(card, _safe_day(start, day), desc, amount)

        # ── Fixed bills (small realistic variance on utilities) ──
        for desc, base_amount, day, card in FIXED_BILLS:
            jitter = rng.uniform(-0.07, 0.12) if "PG&E" in desc else rng.uniform(-0.01, 0.01)
            add(card, _safe_day(start, day), desc, base_amount * (1 + jitter))

        # ── Income and card payments ──
        desc, amount, day = INCOME
        add(CAPONE, _safe_day(start, day), desc, -amount)
        add(CAPONE, _safe_day(start, day + 14 if day + 14 <= 28 else 28), desc, -amount)

        for card in (AMEX, CHASE):
            add(card, _safe_day(start, PAYMENTS[2]), PAYMENTS[0],
                -_amt(rng, 900, 2400))

        # ── Fees ──
        for desc, amount, day, card in FEES:
            if day is not None:
                # Interest every month once a balance starts being carried.
                if idx >= 3:
                    add(card, _safe_day(start, day), desc, amount * rng.uniform(0.8, 1.35))
            elif "ANNUAL" in desc:
                if idx == 2:
                    add(card, _safe_day(start, 7), desc, amount)
            elif rng.random() < 0.22:
                add(card, _safe_day(start, rng.randint(1, 28)), desc, amount)

        # ── A travel month, because real years have them ──
        if idx in (5, 11):
            add(AMEX, _safe_day(start, 8), "UNITED AIRLINES 016 CHICAGO IL",
                _amt(rng, 340, 620))
            add(AMEX, _safe_day(start, 10), "MARRIOTT HOTELS NEW YORK NY",
                _amt(rng, 280, 520))

    # ── A double charge worth disputing ──
    if rows[CHASE]:
        dupe_day = _safe_day(starts[-2], 16)
        add(CHASE, dupe_day, "TST* NOPA RESTAURANT SAN FRANCISCO CA", 96.40)
        add(CHASE, dupe_day, "TST* NOPA RESTAURANT SAN FRANCISCO CA", 96.40)

    for card in rows:
        rows[card].sort(key=lambda r: r["date"])
    return rows


# ── Issuer-specific CSV writers ──────────────────────────────────────────────
# Each writes the same underlying transactions in that issuer's real layout and
# sign convention, so the importer's format detection is genuinely exercised.

def write_amex(rows) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Description", "Card Member", "Account #", "Amount"])
    for r in rows:
        # Amex: charges positive, credits negative.
        w.writerow([r["date"].strftime("%m/%d/%Y"), r["description"],
                    "M PAPADIMITRIOU", "-31004", f"{r['amount']:.2f}"])
    return out.getvalue()


def write_chase(rows) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Transaction Date", "Post Date", "Description", "Category",
                "Type", "Amount", "Memo"])
    for r in rows:
        post = r["date"] + timedelta(days=random.Random(
            r["date"].toordinal()).randint(1, 3))
        cat = "Sale" if r["amount"] > 0 else "Payment"
        # Chase: purchases negative.
        w.writerow([r["date"].strftime("%m/%d/%Y"), post.strftime("%m/%d/%Y"),
                    r["description"], "", cat, f"{-r['amount']:.2f}", ""])
    return out.getvalue()


def write_capital_one(rows) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Transaction Date", "Posted Date", "Card No.", "Description",
                "Category", "Debit", "Credit"])
    for r in rows:
        post = r["date"] + timedelta(days=2)
        # Capital One: separate debit and credit columns, both positive.
        debit = f"{r['amount']:.2f}" if r["amount"] > 0 else ""
        credit = f"{abs(r['amount']):.2f}" if r["amount"] < 0 else ""
        w.writerow([r["date"].strftime("%Y-%m-%d"), post.strftime("%Y-%m-%d"),
                    "7781", r["description"], "", debit, credit])
    return out.getvalue()


WRITERS = {
    AMEX: ("amex_platinum.csv", write_amex),
    CHASE: ("chase_sapphire.csv", write_chase),
    CAPONE: ("capital_one_quicksilver.csv", write_capital_one),
}


def generate_files(directory: str = HERE, seed: int = SEED) -> list[str]:
    rows = build_rows(seed)
    written = []
    for card, (filename, writer) in WRITERS.items():
        path = os.path.join(directory, filename)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            fh.write(writer(rows[card]))
        written.append(path)
    return written


def load_demo(store, seed: int = SEED) -> int:
    """Generate the sample statements and run them through the real importer."""
    from finance.ingest import parse_csv
    from finance.pipeline import ingest

    rows = build_rows(seed)
    total = 0
    for card, (filename, writer) in WRITERS.items():
        parsed = parse_csv(content=writer(rows[card]), filename=filename)
        result = ingest(store, parsed, filename=filename)
        total += result["imported"]
    return total


if __name__ == "__main__":
    paths = generate_files()
    for p in paths:
        print("wrote", p)
