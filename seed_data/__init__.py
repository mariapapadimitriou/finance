"""Seed data: transactions shipped with the app.

A hosted deployment has no durable disk — the serverless filesystem is
read-only apart from /tmp, which belongs to one function instance and is
discarded when that instance recycles. So a deployment that relied on someone
uploading statements would greet every visitor with an empty dashboard.

Instead the ledger is committed here as JSON and loaded into a fresh database
on cold start. The deployed app then always shows the same real spending,
whichever instance answers the request.

What this means, plainly: everything in `transactions.json` is public to anyone
who can reach the deployment or the repository. It holds dates, merchants,
amounts and categories — not names, addresses or account numbers. Regenerate it
with:

    python -m seed_data.export
"""
