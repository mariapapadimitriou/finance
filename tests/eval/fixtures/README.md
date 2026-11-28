# Labelled cases for the signals replay (THL-310)

Each `*.json` here is one small ledger with the right answers, replayed by
`tests/eval/signals_replay.py` and held to a precision floor by
`tests/eval/test_signals_precision.py`.

Real cases go here: anonymised examples of what a detector got wrong (or
right), such as the transfer and card-payment mistakes from a second user.
One file per story. Before adding one:

- Replace every name, account number, mask, reference and memo with made-up
  ones. Keep only what the detector looks at: dates, amounts, which account,
  the account type, the bank's category, and the shape of the description
  (an e-Transfer still reads like one).
- Never copy a real person's name or a real account number.

## Format

```json
{
  "name": "short_name",
  "about": "What happened, in a sentence or two.",
  "today": "2026-11-15",
  "accounts": {"chq": {"name": "Chequing", "type": "depository", "subtype": "checking", "mask": "1001"}},
  "transactions": [
    {"ref": "a", "account_id": "chq", "date": "2026-10-03", "name": "BANK WORDING",
     "amount": 812.40, "personal_finance_category": {"primary": "...", "detailed": "..."}}
  ],
  "answers": [{"ref": "a", "category": "Coffee"}],
  "exhaustive": ["transfers.pairs"],
  "labels": [
    {"detector": "transfers.pairs", "refs": ["a", "b"], "kind": "card_payment", "truth": true}
  ]
}
```

- `transactions` are Plaid-shaped (amount positive = money out) and go
  through the real importer. Optional fields Plaid sends work too:
  `pending`, `payment_meta`, `counterparties`, `merchant_name`.
- `answers` are rows she sorted herself (what the pattern detectors learn from).
- A label matches a detection whose rows are exactly `refs` (or any of them,
  with `"match": "subset"`), and whose kind is `kind` when it says one.
- A detector in `exhaustive` has every right answer labelled, so anything
  else it finds in this ledger counts as wrong. Otherwise unlabelled
  detections are left out of the score.

After adding a case, run `python3 tests/eval/signals_replay.py`. If a
detector's precision drops below its floor, that's the mistake the case
shows: fix the detector under a new version in `finance/signals/registry.py`,
or, if the floor itself was set from too few cases, lower it in the test
with a note saying why.
