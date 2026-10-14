# Security and privacy at Pearl

Pearl holds people's bank transactions, so three sets of rules apply, and this
file says how each one is met and where in the code. Review it whenever
something here changes. Last reviewed 2026-10-14.

## What applies

| Rule | Why it applies | What it asks |
|---|---|---|
| **PIPEDA** (Canada's federal privacy law), Schedule 1 | Pearl collects personal information in the course of commercial activity, across Canada. | Consent, limiting collection and use, accuracy, **safeguards** proportionate to sensitivity (financial data is sensitive), openness, individual access, challenging compliance; **breach of security safeguards**: report to the Privacy Commissioner and notify affected people when there is a real risk of significant harm, and keep a record of every breach. |
| **Quebec Law 25** (Act respecting the protection of personal information in the private sector, as amended) | Pearl serves Quebec residents. | A person responsible for personal information, a privacy policy in plain language, privacy by default, consent for each purpose, the right to deletion and portability, a privacy impact assessment for new systems handling personal information, and **confidentiality incident** reporting to the Commission d'accès à l'information and to the people affected when there is a risk of serious injury, plus an incident register. |
| **Plaid Developer Policy** | Pearl pulls transactions through Plaid. | Keep Plaid credentials and End User Data confidential, encrypt Account Information at rest and in transit, restrict access to people who need it, delete End User Data when a user asks, and report any suspected breach promptly to security@plaid.com. |

Pearl never sees a card number or processes a payment, so PCI DSS does not
apply. Plaid's Transactions product is the only product used; no
investment, liabilities or auth products.

## How the safeguards are met

**In transit.** Vercel terminates TLS for every request; HSTS
(`Strict-Transport-Security`, one year, subdomains) tells browsers never to
try plain HTTP again (`finance/security.py`). Neon's Postgres URL keeps
`sslmode=require` (`finance/db.py`).

**At rest.** Plaid access tokens are encrypted with Fernet (AES-128-CBC +
HMAC) under `SPENDIE_SECRET_KEY` before they reach the database; linking is
refused rather than storing one in the clear (`finance/secrets_box.py`,
`finance/plaid_link.py`). The key lives only in Vercel's environment
variables. Passwords are scrypt hashes (`finance/auth.py`); sign-in codes
and recovery codes are stored as hashes (`finance/signin_codes.py`,
`finance/devices.py`). Each account's ledger is its own Postgres schema
(`finance/store.py`), so one account's queries cannot reach another's rows.

**Sessions and sign-in.** Cookies are `HttpOnly`, `SameSite=Lax` and
`Secure` when hosted (`app.py`). A session unused for 20 minutes is over on
the server (`finance/security.py`, `IDLE_SECONDS`), beside the browser's
own 15-minute timer (A-14). Passwords need 10 characters. A new device must
be approved from a device already signed in, or with a recovery code
(A-07, A-08, `finance/devices.py`). Too many wrong codes pause sign-in for
15 minutes (`finance/signin_codes.py`). The reply to "send me a code" is
the same whether or not an account exists, so sign-in cannot be used to
find out who has one. Passkeys (WebAuthn) verify the origin and relying
party (`finance/passkeys.py`).

**Every request.** `finance/security.py` installs on every response:
`Content-Security-Policy` (only Pearl's own code and Plaid Link may run;
no framing), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Permissions-Policy`, and `Cache-Control: no-store` on
every API answer. A request that changes something must carry an `Origin`
of this site, or none (a tool, which cannot carry the cookie); a
cross-site one is refused. Request bodies are capped at 10 MB. All SQL is
parameterised; the only f-strings name tables and columns from fixed lists.

**Least data in logs.** Sign-in codes and email addresses are printed to
the terminal only when running locally without a mail server; a hosted
deployment refuses to send a code without mail configured and never prints
one (`app.py`, `finance/privacy_api.py`). Plaid access tokens are never
serialised (`Store.plaid_items` leaves them out).

**Access rights (PIPEDA principles 9 and 4.3.8; Law 25 deletion and
portability).** Profile › Your data: *Download a copy* gives every account
and transaction as a .zip (`finance/data_export.py`); *Delete your account*
disconnects banks at Plaid, deletes the ledger, sign-in and consent history
straight away, after a passkey, code or password confirms it
(`finance/account_deletion.py`). Consent for each purpose is recorded with
its time and version (Profile › Privacy and consent, `finance/consent.py`)
and can be withdrawn there.

**Dependencies.** `pip-audit -r requirements.txt` and `npm audit --omit=dev`
are clean as of the review date. Run both before each release.

## When something goes wrong (incident runbook)

1. **Contain** within the hour: rotate `SPENDIE_SECRET_KEY` only if the
   key itself leaked (it re-encrypts nothing on its own — tokens would have
   to be re-linked); otherwise rotate the Plaid secret in the Plaid
   dashboard, the Neon password, and Vercel's environment variables, and
   redeploy. Revoke affected Plaid Items (`plaid_link.unlink`).
2. **Record** it the same day in the incident register (date, what, whose
   data, how many, what was done), whether or not it meets a reporting
   threshold — both PIPEDA and Law 25 require the record.
3. **Assess** the risk of significant harm / serious injury: bank
   transaction history and tokens count as sensitive, so assume the
   threshold is met unless the data was encrypted and the key is safe.
4. **Notify**, as soon as feasible:
   - the Office of the Privacy Commissioner of Canada (PIPEDA breach report
     form), and each affected person, with what happened, when, what data,
     what Pearl did, what they can do, and a contact;
   - the Commission d'accès à l'information for anyone in Quebec, and the
     people affected — confirm the current CAI deadline with counsel; sources
     differ;
   - Plaid at security@plaid.com, promptly, for anything touching Plaid
     credentials or End User Data.
5. **Review** within a week: what safeguard failed, the fix, and this file.

## Owner

The person responsible for personal information (Law 25) is the founder,
Maria Papadimitriou, reachable through Profile › Help and support. Review
this file, the privacy policy (`src/pearl/docs.jsx`) and the consent
versions together whenever data handling changes.

## Not yet done

- A privacy impact assessment document for Plaid linking and for the
  hosted database (Law 25 asks for one for systems handling personal
  information); the design decisions above are its substance, but it
  should exist as its own signed document.
- Dev-only tooling (`vite`, `vitest`) has known advisories that only affect
  a developer's machine; upgrading means committing a new `node_modules`
  tree. Do it in its own change.
