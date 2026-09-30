# Spendie

Personal finance and budgeting across every credit card you own. Import the CSV
exports from each card, and Spendie normalizes them into one ledger, works out
where the money actually goes, and tells you specifically what to cut — with the
transactions behind every recommendation.

Runs locally against a SQLite file, and deploys to Vercel. The deployed build
ships a committed copy of the ledger in `seed_data/transactions.json`, which is
**public by design** — see [Deploying](#deploying). Anything you import locally
stays local until you export it there.

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
banks ship no header row at all. Spendie detects the issuer's layout, normalizes
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

**One number for today, with the arithmetic shown.** A daily allowance that rolls
over: underspend on Monday and Tuesday's number is bigger, and the carried-in
amount is displayed as its own term so the figure is never magic. Overspending
gets two honest options rather than a warning — spread the shortfall across the
days left, or cover it from a named bucket (Fun, Savings), each with the
consequence spelled out. Only discretionary spending counts, because no amount of
restraint on a Tuesday changes the hydro bill.

**Streaks and badges that can only be earned by spending less.** Points come from
days under the allowance, days with nothing spent, and months finished inside
budget. Nothing pays out for spending, so the mechanics can never nudge you
toward a purchase; and a day outside the imported range reads as *no data*, never
as a quiet day, so no badge is ever awarded for a statement you didn't upload.

**Projections, with their own error bars.** Two lines — your current pace, and the
same pace with the found cuts applied — plus how many months of data are behind
them. The surplus is stated as a ceiling, because spending that never touches an
imported card isn't in it.

**Typing a purchase in before it posts.** Manual entries run the same duplicate
check an import runs, only looser, and report near-matches instead of silently
merging them. Going the other way, a statement row supersedes the placeholder you
typed — the statement knows the real date, descriptor and card.

---

## Importing your statements

Drag PDF statements or CSV exports onto the Import tab. The format is detected
automatically and re-importing the same file is safe and idempotent.

**PDF statements.** Scotiabank's layout is implemented: the statement period
supplies the year that transaction lines omit, wallet markers like `(APPLE PAY)`
are ignored, and a trailing minus marks a credit. Every import is reconciled
against the statement's own declared purchase and credit totals. Text-based
statements only — a scanned image needs OCR first, and the importer says so
rather than silently returning nothing.

**CSV exports.** American Express, Chase, Capital One, Citi, Discover, Bank of
America, RBC, Scotiabank, Wells Fargo and TD (both headerless). Anything else
falls back to keyword matching on the column names, which handles most exports;
the import report says how confident the match was.

### Gaps matter

Statements are usually downloaded a few at a time, which leaves holes. A hole
quietly corrupts anything that reasons about months — a monthly average divides
by months you never imported, and a subscription whose charges straddle a gap
looks quarterly rather than monthly. So gaps are detected, excluded from
averages, and shown at the top of the Overview rather than left to distort the
numbers silently.

### Correcting a category

Categorization is rules plus your corrections. When something lands in the wrong
bucket, click its category on the Transactions tab and choose **All \<merchant\>** —
that becomes a permanent override applied to every past charge from that merchant
and every future import.

---

## How the savings figures are calculated

Ten rules run over your ledger. Each states its assumption, and every estimate
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
| Category habit | A category ≥15% of spending over 12+ purchases | Trimming it by a quarter |
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

CSV import is the working path and needs no accounts or keys. Spendie is built so
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

## Deploying

The app runs on Vercel as a single origin: Flask serves the API, and the built
frontend is packaged into the function.

A serverless filesystem is read-only apart from `/tmp`, which belongs to one
instance and is discarded when that instance recycles — so a deployment with
nothing committed would show an empty dashboard to every visitor. The ledger
is therefore committed to `seed_data/transactions.json` and loaded on cold
start.

**That file is public.** It holds dates, merchants, amounts and categories —
deliberately not names, addresses or account numbers, none of which reach the
ledger in the first place. Regenerate it after importing new statements:

```bash
python -m seed_data.export        # rewrite the committed ledger
python -m seed_data.export --check  # see what would be written first
```

### Making uploads durable

Without a database, edits made on the deployment — an upload, a budget, a
recategorization — last only as long as the instance that received them, and a
request served by a different instance never sees them at all. The Import tab
says so in as many words when it detects that state, because an upload that
quietly disappears an hour later is worse than one that is refused.

Attaching a Postgres fixes it, and needs no code change:

1. In the Vercel project: **Storage → Create Database → Postgres** (Neon's free
   tier is ample — this ledger is a few hundred rows).
2. Connect it to the project. Vercel injects `DATABASE_URL` itself.
3. Redeploy.

`finance/db.py` picks the connection string up, `/tmp` stops being used, and the
committed ledger seeds the database once — after which uploads persist and every
instance sees the same data. `/api/health` reports which mode is live:
`postgres`, `ephemeral` or `sqlite`.

Locally nothing changes: with no `DATABASE_URL` set the ledger is still a SQLite
file that never leaves the machine.

### One store, two databases

Every query is written once, in SQLite's dialect, and `finance/db.py` rewrites
the handful of constructs Postgres spells differently — placeholders,
`INSERT OR IGNORE`, `AUTOINCREMENT`, `REAL`, and `LIKE` (SQLite's ignores ASCII
case and Postgres' does not, so the merchant search would quietly stop
matching). The rewriter is unit-tested rule by rule, and the whole suite can be
run against a live server, which is how the two differences a rewriter can't
see were found:

```bash
SPENDIE_TEST_DATABASE_URL=postgresql://... python -m pytest
```

---

## Layout

```
app.py                      Flask entry point
finance/
  models.py                 Transaction model, merchant normalization, parsing
  ingest/
    base.py                 The source interface every importer implements
    schemas.py              Per-issuer CSV column layouts and detection
    csv_source.py           CSV export import
    pdf_source.py           PDF statement import
    plaid_source.py         Plaid adapter (implemented, needs credentials)
  dedupe.py                 Cross-export de-duplication, double-charge detection
  categorize.py             Category rules, issuer mapping, user overrides
  analytics.py              Aggregations: monthly, category, merchant, baselines
  insights/
    recurring.py            Subscription and recurring-bill detection
    rules.py                The savings engine
  trips.py                  Declared date ranges whose spending reads as Travel
  spend_plan.py             Safe to spend: the rolling daily allowance
  gamify.py                 Streaks, points and badges — restraint only
  projections.py            Forward projections under two scenarios
  manual.py                 Hand-typed rows, and keeping imports off them
  narrative.py              Optional Claude layer
  pipeline.py               source → dedupe → categorize → store
  db.py                     SQLite locally, Postgres when DATABASE_URL is set
  store.py                  Persistence, written once in SQLite's dialect
  api.py                    HTTP routes
src/                        React UI (Vite)
  components/Logo.jsx       The Spendie mark, inline SVG
static/favicon.svg          Favicon, copied into the build
seed_data/
  transactions.json         The committed ledger — public by design
  export.py                 Write it from the local ledger, and load it back
sample_data/generate.py     Realistic sample statements in three issuer formats
tests/                      285 tests
```

## Tests

```bash
python -m pytest
```

Covers the per-issuer sign conventions, messy and headerless CSVs, de-duplication
across overlapping exports, categorization precedence, recurring detection
including the price-change case, every savings rule, and the API end to end.
`tests/test_plan.py` covers the newer half: rollover arithmetic, spreading and
bucket covering, manual entry colliding with an import in both directions, and
the honesty rules in the scoring — chiefly that a partly-imported month can never
come in "under budget".

## API

`GET /api/health` (reports the storage mode) · `/api/summary` · `/api/breakdown` · `/api/transactions` · `/api/recurring` ·
`/api/insights` · `/api/budgets` · `/api/accounts` · `/api/sources` ·
`/api/imports` · `/api/trips` · `/api/plan` · `/api/progress` · `/api/projections`
`POST /api/import` · `/api/sync/<source>` · `/api/narrative` ·
`/api/insights/<id>/dismiss` · `/api/transactions` · `/api/trips` ·
`/api/plan/simulate` · `/api/buckets/<id>/cover`
`PATCH /api/transactions/<id>` · `/api/trips/<id>`
`PUT /api/budgets` · `/api/plan` · `/api/buckets` · `/api/projections/income`
`DELETE /api/transactions` · `/api/transactions/<id>` · `/api/trips/<id>` ·
`/api/buckets/<id>`

The server binds to `127.0.0.1` and is not intended to face a network.
