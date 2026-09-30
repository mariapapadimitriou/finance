"""Seed data: transactions optionally shipped with the app.

There is no committed ledger any more. There was one, and the reason is worth
keeping because it explains the machinery that remains: a hosted deployment
had no durable disk, so a file in the repository was the only way the app
could show real spending rather than an empty dashboard. That stopped being
true when the ledger moved onto Postgres, where an upload persists on its own.

The loader still works, and `python -m seed_data.export` still writes the
file. It is useful for moving a ledger between machines, or for standing one
up to look at. But nothing is committed now, and two things follow.

Anything you do commit here is **public** to anyone who can reach the
repository. The exporter writes dates, merchants, amounts and categories —
never names, addresses or account numbers — but that is still a full picture
of where your money goes.

And an empty ledger is not always a new one. After a deliberate reset it is
empty because someone emptied it, so the reset leaves a marker and the seeder
respects it; otherwise the next cold start would quietly undo the reset.
"""
