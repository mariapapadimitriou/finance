# Ledger

Personal finance and budgeting across every credit card you own. Import the CSV
exports from each card, and Ledger normalizes them into one ledger, works out
where the money actually goes, and tells you specifically what to cut — with the
transactions behind every recommendation.

Everything runs locally. Your transaction history lives in a SQLite file on your
machine and never leaves it, apart from one optional feature that is off by
default and says exactly what it sends.

```bash
pip install -r requirements.txt
npm install

python app.py --demo     # API on :5050, preloaded with 14 months of sample data
npm run dev              # UI on :3000
```

Drop `--demo` once you're importing your own statements.

---

## What it does

**Aggregates every card.** Amex writes purchases as positive numbers, Chase
writes them as negative, Capital One splits them across two columns, and several
banks ship no header row at all. Ledger detects the issuer's layout, normalizes
the sign convention, and cleans `SQ *BLUE BOTTLE COFFEE 4471 OAKLAND CA` down to
`Blue Bottle Coffee` — so the same shop groups together across three cards and
two payment processors.

**Handles overlapping exports.** Download "last 90 days" in March and again in
April and the overlap re-delivers rows you already have, sometimes with a shifted
posting date. Those are recognized and dropped. Two genuinely identical $6.40
coffees on the same day are both kept, which is the case naive de-duplication
gets wrong.

**Finds recurring charges by their behaviour, not their name.** A charge becomes
a subscription because it repeats on a cadence with a stable amount. That also
catches subscriptions hiding inside a merchant you shop at normally — Amazon
Prime among Amazon orders — and notices when one quietly raises its price.

**Tells you what to cut, with numbers.** A ranked list of findings, each with an
estimated annual saving, a confidence score, a stated assumption, and the exact
charges it's based on. A recommendation you can't audit is just a guess.

**Budgets seeded from your own spending.** Discretionary categories start 10%
under your median — a nudge, not a cliff — while essentials start at your median,
since deciding to use less electricity doesn't make it so. Mid-month, budgets
project forward so you can act before the month closes rather than after.

---

## Importing your statements

Every major issuer lets you export CSV: sign in, find **Statements & Activity →
Download**, pick CSV and the widest date range offered. Then drag the files onto
the Import tab.

Recognized formats: American Express, Chase, Capital One, Citi, Discover, Bank of
America, RBC, Scotiabank, Wells Fargo and TD (both headerless). Anything else
falls back to keyword matching on the column names, which handles most exports;
the import report tells you how confident the match was and flags anything that
looks off.

Re-importing the same file is safe and idempotent.

### Correcting a category

Categorization is rules plus your corrections. When something lands in the wrong
bucket, click its category on the Transactions tab and choose **All \<merchant\>** —
that becomes a permanent override applied to every past charge from that merchant
and every future import.

---

## How the savings figures are calculated

Nine rules run over your ledger. Each states its assumption, and every estimate
errs low:

| Finding | What it looks for | Assumes |
|---|---|---|
| Fees & interest | Any fee or interest charge | Avoidable in full |
| Double charges | Same merchant, amount and day | Only if genuinely an error |
| Price creep | A subscription that repriced upward | Reverting, not cancelling |
| Long-running subscriptions | The 3 costliest flat, old subscriptions | Full saving only if cancelled |
| Overlapping services | 3+ active subscriptions in one category | Dropping only the cheapest |
| Frequent small habits | ≥4×/month, under $40 each | Halving the frequency |
| Delivery premium | Food delivery orders | 35% markup vs. pickup |
| Category drift | Two straight months ≥30% over your median | The new level persists |
| Subscription load | 4+ discretionary subscriptions | Cancelling a quarter by value |

The headline figure on the Savings tab is **confidence-weighted**. The raw sum is
also shown, but it adds a speculative finding to a certain one as though they
were equally real, so the weighted number is the honest one.

Two deliberate choices worth knowing about:

- **Refunds net against their category, and card payments are excluded from
  spending entirely.** Otherwise a $1,200 statement payment shows up as your
  biggest purchase of the month.
- **A partial current month is never compared against full-month baselines.** An
  export pulled on the 21st would otherwise manufacture a "you're spending less!"
  story every single month. Trend detection uses complete months only, and the UI
  labels the current month as in progress.

---

## Adding live sync

CSV import is the working path and needs no accounts or keys. Ledger is built so
sync is a configuration change rather than a rewrite: every source implements one
interface (`finance/ingest/base.py`), and nothing downstream — de-duplication,
categorization, analytics, insights — knows where a transaction came from.

The Plaid adapter (`finance/ingest/plaid_source.py`) is written and its payload
mapping is covered by tests. It needs only credentials:

```bash
pip install plaid-python
export PLAID_CLIENT_ID=... PLAID_SECRET=... PLAID_ENV=sandbox
```

Until those exist it reports itself as unconfigured and the Import tab shows the
setup steps rather than failing. Production access requires Plaid's approval and
is billed per connected account, which is why CSV remains the default.

To add a different source, implement `TransactionSource.status()` and `.fetch()`,
return `Transaction` objects, and call `register()`.

---

## The optional Claude summary

The rule engine computes every number on its own and runs entirely offline. If
you want the findings turned into a written read, set:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
```

**This is the only feature that sends anything anywhere.** It sends category
totals, merchant names and the finding summaries — never individual transactions,
account numbers, or raw card descriptors. `GET /api/narrative?preview=1` returns
the exact payload so you can inspect it before enabling anything, and a test
asserts that no raw descriptors or account numbers can appear in it.

---

## Layout

```
app.py                      Flask entry point
finance/
  models.py                 Transaction model, merchant normalization, parsing
  ingest/
    base.py                 The source interface every importer implements
    schemas.py              Per-issuer CSV column layouts and detection
    csv_source.py           CSV / statement import
    plaid_source.py         Plaid adapter (implemented, needs credentials)
  dedupe.py                 Cross-export de-duplication, double-charge detection
  categorize.py             Category rules, issuer mapping, user overrides
  analytics.py              Aggregations: monthly, category, merchant, baselines
  insights/
    recurring.py            Subscription and recurring-bill detection
    rules.py                The savings engine
  narrative.py              Optional Claude layer
  pipeline.py               source → dedupe → categorize → store
  store.py                  SQLite persistence
  api.py                    HTTP routes
src/                        React UI (Vite)
sample_data/generate.py     Realistic sample statements in three issuer formats
tests/                      139 tests
```

## Tests

```bash
python -m pytest
```

Covers the per-issuer sign conventions, messy and headerless CSVs, de-duplication
across overlapping exports, categorization precedence, recurring detection
including the price-change case, every savings rule, and the API end to end.

## API

`GET /api/summary` · `/api/breakdown` · `/api/transactions` · `/api/recurring` ·
`/api/insights` · `/api/budgets` · `/api/accounts` · `/api/sources` ·
`/api/imports`
`POST /api/import` · `/api/sync/<source>` · `/api/narrative` ·
`/api/insights/<id>/dismiss`
`PATCH /api/transactions/<id>` · `PUT /api/budgets` · `DELETE /api/transactions`

The server binds to `127.0.0.1` and is not intended to face a network.
