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
days left, or borrow it from a piggy bank, each with the consequence spelled
out. Only discretionary spending counts, because no amount of restraint on a
Tuesday changes the hydro bill. The figure itself is derived from the Plan tab
on every request rather than stored, so changing your pay or a commitment moves
it immediately — and the page shows the whole chain from the plan's leftover
down to the daily number, since those are different figures on purpose.

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
category, click it on the Transactions tab and choose **All \<merchant\>** —
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
- **Spending charged to a piggy bank is excluded too**, because it was budgeted
  over the months leading up to it. See below.

Alongside the rules, the Savings tab shows **observations about the plan itself**
— that your commitments are 65% of your pay, that last month ran over, that a
year of travel is budgeted nowhere. These are written in advance in
`finance/insights/profile.py`, each with the condition that makes it true, and
shown only when it holds. They cost nothing to run, say the same thing twice when
asked twice, and take their figures from the same functions as the tab each one
links to, so following one never lands you on a page that contradicts it.

---

## Piggy banks

A monthly budget handles rent well and a holiday badly. The holiday costs $3,000
once a year, so eleven months report a surplus that isn't real and the twelfth
reports a catastrophe that was entirely predictable. Car maintenance, insurance
paid annually, Christmas and a dentist you see twice a year all have the same
shape.

A piggy bank fixes both halves of that:

- **Going in.** The target is divided by the months available and that share is
  subtracted from every month's budget, exactly like rent — so it reduces the
  Plan's leftover and with it the daily number. A holiday in June is a bill you
  are already paying.
- **Coming out.** A charge allocated to a bank on the Transactions tab leaves the
  month it fell in: it is not in the Overview, the budgets, the trends or the
  daily number. June doesn't look like a disaster, because June was never asked
  to pay for the holiday.

Both figures are derived rather than stored — the monthly contribution from the
target and the horizon, the balance from how many months have passed less what
has been charged — so there is no number anywhere that has to be kept up to
date. Two shapes, because two shapes of cost: `annual` recurs forever and
refills after it is spent (target ÷ 12), and `once` has a date and stops
collecting when it arrives (what is still needed ÷ months left).

Spending ahead of a bank is allowed — sometimes you have to fly before you have
finished saving for the flight — and reported, because the overdraft comes out of
the month after all.

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

## Deploying

The app runs on Vercel as a single origin: Flask serves the API, and the built
frontend is packaged into the function.

A serverless filesystem is read-only apart from `/tmp`, which belongs to one
instance and is discarded when that instance recycles — so a deployment with
nothing committed would show an empty dashboard to every visitor. The ledger
is therefore committed to `seed_data/transactions.json` and loaded on cold
start.

No ledger is committed now — that was needed when the deployment had no
durable disk, and stopped being needed when it moved onto Postgres, where an
upload persists on its own. The exporter still works and is useful for moving
a ledger between machines. **Anything you do commit is public**: it holds
dates, merchants, amounts and categories — deliberately not names, addresses
or account numbers, none of which reach the ledger in the first place.

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

### On a phone

Below 860px the sidebar becomes a tab bar fixed to the bottom of the screen,
where a thumb can reach it, and the icons come back because at that size they
are what you navigate by. The ledger stops being a five-column table and
becomes two lines a row — what it was and what it cost, then the details
underneath — while staying a real table, so its headers still reach a screen
reader.

Three iOS specifics the layout accounts for. Safari zooms the page when you
focus an input whose text is under 16px, so form controls are exactly 16px
there. `100vh` is the height with the browser chrome hidden, which leaves a
strip you can scroll to but never see, so the shell uses `100dvh`. And
`viewport-fit=cover` plus `env(safe-area-inset-bottom)` keeps the tab bar clear
of the home indicator.

The bug worth naming, because it is the one that makes a layout "not
responsive" while every media query looks right: a flex or grid item defaults
to `min-width: auto` and refuses to shrink below its content. A row of eleven
tabs with `overflow-x: auto` therefore forced the entire page three times wider
than the phone. `min-width: 0` on the strip is what fixes it.

### Locking the deployment

Everything — the UI and every API route — sits behind one password. Not a user
system: there is one person here, so there is one secret, and no accounts,
signup or reset flow to get wrong.

```bash
python -c "from finance.auth import hash_password; print(hash_password('your password'))"
```

Put the result in `SPENDIE_PASSWORD_HASH` and redeploy. A hosted deployment
with no password set **refuses to serve anything** rather than quietly staying
open, because forgetting the variable is the likely mistake and it must not be
the one that leaves a bank connection exposed. Running locally is unaffected:
no password set means no password asked for.

The session cookie is signed with a key derived from the password hash, so it
is stable across serverless instances without a second variable to keep in
sync — and changing your password signs every existing session out, which is
what you would want it to do.

### Starting fresh

The **Accounts** tab can empty the ledger: every transaction, and the budgets,
trips, merchant corrections and dismissed findings worked out from them. Your
piggy banks survive, since they are decisions about the future rather than a
record of the past, but whatever was charged to them goes with the
transactions. Your password and Plaid credentials are untouched, and bank connections
are kept unless you say otherwise — but their sync cursors are rewound either
way, since a cursor pointing past an emptied ledger would make the next sync
report nothing new and leave the cards empty for good.

It asks you to type `erase`, because against a hosted database there is no
undo.

One subtlety it has to handle: the seeder loads a committed ledger into an
*empty* database on cold start, and after a reset the database is very much
empty. So a reset leaves a marker and the seeder respects it; otherwise a
serverless instance starting cold would quietly put everything back.

### Only the cards

Linking a bank hands over everything it holds — chequing, savings, an
investment account. Syncing keeps only credit accounts, because a chequing
account records the payment that settles the card and importing both counts
the same money twice. Set `plaid_cards_only` to `0` to take everything.

The **Accounts** tab lists every account in the ledger with its kind, where it
came from and what it holds, and removes the ones that shouldn't be there. It
also reports possible overlap: the same amount within five days under two
different account ids, which is what a card imported by statement *and* later
connected through Plaid looks like. The importer never merges across accounts
— two $12 lunches on two cards are two lunches — so these are reported and you
decide.

### Connecting a bank

Plaid Link handles the bank login; Spendie never sees your credentials. What it
stores is an access token that can read transactions, and that token is
encrypted before it reaches the database — so a leaked database dump yields
ciphertext, since the key lives in the environment instead.

```bash
python -m finance.secrets_box      # generate SPENDIE_SECRET_KEY
```

Set `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` (`sandbox` or `production`)
and `SPENDIE_SECRET_KEY`, redeploy, then connect each card on the **Banks** tab.
Linking is refused outright if the encryption key is missing — storing a bank
credential in the clear is not a fallback.

Syncing uses `/transactions/sync`, which returns only what changed since a
stored cursor. That matters for more than speed: when a pending charge posts,
Plaid removes the pending row and adds the posted one, and an importer that
only ever added would keep both and count the purchase twice. The cursor
advances only once the rows it covers are stored, so a failed sync re-fetches
its window rather than skipping it — a repeat is caught by the fingerprint,
where a gap would be silent and permanent.

`PLAID_COUNTRY_CODES` defaults to `CA`.

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
    profile.py              Insights written in advance, shown when they apply
    rules.py                The savings engine
  trips.py                  Declared date ranges whose spending reads as Travel
  spend_plan.py             Safe to spend: the rolling daily allowance
  projections.py            Forward projections under two scenarios
  manual.py                 Hand-typed rows, and keeping imports off them
  piggy.py                  Piggy banks: annual costs collected monthly
  pipeline.py               source → dedupe → categorize → store
  db.py                     SQLite locally, Postgres when DATABASE_URL is set
  store.py                  Persistence, written once in SQLite's dialect
  auth.py                   The single password in front of everything
  secrets_box.py            Encrypts Plaid tokens before they are stored
  plaid_link.py             Linking a bank, and the incremental sync
  audit.py                  Charges that may be in the ledger twice
  api.py                    HTTP routes
src/                        React UI (Vite)
  components/Logo.jsx       The Spendie mark, inline SVG
static/favicon.svg          Favicon, copied into the build
seed_data/
  transactions.json         The committed ledger — public by design
  export.py                 Write it from the local ledger, and load it back
sample_data/generate.py     Realistic sample statements in three issuer formats
tests/                      393 tests
```

## Tests

```bash
python -m pytest
```

Covers the per-issuer sign conventions, messy and headerless CSVs, de-duplication
across overlapping exports, categorization precedence, recurring detection
including the price-change case, every savings rule, and the API end to end.
`tests/test_plan.py` covers the newer half: rollover arithmetic, spreading and
borrowing from a piggy bank, manual entry colliding with an import in both
directions, and the honesty rules — chiefly that a partly-imported month can
never come in "under budget". `tests/test_piggy.py` covers the piggy-bank
arithmetic and, more importantly, that a charge allocated to one leaves every
total that should no longer include it. `tests/test_consistency.py` covers the
figures agreeing across tabs after an edit, including that the daily number
follows the plan without anything being re-applied.

## API

`GET /api/health` (reports the storage mode) · `/api/auth/status` ·
`/api/plaid/items` · `/api/summary` · `/api/breakdown` · `/api/transactions` · `/api/recurring` ·
`/api/insights` · `/api/budgets` · `/api/accounts` · `/api/sources` ·
`/api/imports` · `/api/trips` · `/api/plan` · `/api/plan/setup` · `/api/piggy` ·
`/api/projections` · `/api/nudge`
`POST /api/import` · `/api/sync/<source>` · `/api/insights/<id>/dismiss` ·
`/api/transactions` · `/api/trips` · `/api/plan/simulate` ·
`/api/plan/setup/apply` · `/api/piggy` · `/api/piggy/<id>/allocate` ·
`/api/piggy/<id>/cover` · `/api/auth/login` · `/api/auth/logout` ·
`/api/plaid/link-token` · `/api/plaid/exchange` · `/api/plaid/sync`
`PATCH /api/transactions/<id>` · `/api/trips/<id>` · `/api/piggy/<id>`
`PUT /api/budgets` · `/api/plan/setup` · `/api/projections/income`
`DELETE /api/transactions` · `/api/transactions/<id>` · `/api/trips/<id>` ·
`/api/piggy/<id>` · `/api/piggy/allocations/<txn_id>` · `/api/plaid/items/<id>`

There is deliberately no route that sets the daily spending figure. It is
derived from the plan on every request — see `money_plan.monthly_allowance` —
because a stored copy went stale the moment income or a commitment changed.

Every route is behind the password when one is configured, which a hosted
deployment always is.
