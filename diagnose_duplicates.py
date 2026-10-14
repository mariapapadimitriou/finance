"""Read-only: why are transactions doubled? Prints accounts and duplicate pairs.

    DATABASE_URL='postgres://…' python diagnose_duplicates.py

Only SELECTs; changes nothing. Prints no secrets: account names, last four
digits, connection ids (shortened), counts, and a few sample duplicates.
"""

import os
import sys
from collections import defaultdict

import psycopg
from psycopg.rows import dict_row

url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
if not url:
    sys.exit("Set DATABASE_URL first.")


def q(c, sql, *args):
    return c.execute(sql, args).fetchall()


with psycopg.connect(url, row_factory=dict_row) as c:
    c.read_only = True
    people = q(c, "SELECT id, owner FROM public.app_users ORDER BY id")
    for p in people:
        schema = "public" if p["owner"] else f"u_{p['id']}"
        exists = q(c, "SELECT 1 FROM information_schema.tables WHERE table_schema = %s "
                      "AND table_name = 'transactions'", schema)
        if not exists:
            continue
        s = f'"{schema}"'
        print(f"\n=== account {p['id']} ({schema}) ===")
        items = {r["item_id"]: r for r in q(c, f"SELECT item_id, institution, created_at, "
                                               f"error_code FROM {s}.plaid_items ORDER BY created_at")}
        print("connections:")
        for i in items.values():
            print(f"  {i['item_id'][:10]}…  {i['institution']}  created {i['created_at']}  "
                  f"error={i['error_code'] or '-'}")
        rules = {r["account_id"]: r for r in q(c, f"SELECT * FROM {s}.account_sync")}
        settings = {r["account_id"]: r for r in q(c, f"SELECT * FROM {s}.account_settings")}
        rows = q(c, f"SELECT id, date, amount, description, account_id, account_name, source "
                    f"FROM {s}.transactions")
        excluded = {r["txn_id"] for r in q(c, f"SELECT txn_id FROM {s}.txn_exclusions WHERE kept = 0")}
        dupes = {r["txn_id"]: r["state"] for r in q(c, f"SELECT txn_id, state FROM {s}.txn_duplicates")}
        by_acct = defaultdict(list)
        for t in rows:
            by_acct[t["account_id"]].append(t)
        print("accounts:")
        for aid in sorted(set(by_acct) | set(rules)):
            r, st = rules.get(aid, {}), settings.get(aid, {})
            item = r.get("item_id") or ""
            live = "live" if item in items else ("gone" if item else "no connection")
            name = r.get("account_name") or (by_acct[aid][0]["account_name"] if by_acct[aid] else "")
            src = by_acct[aid][0]["source"] if by_acct[aid] else "-"
            print(f"  {aid[:10]}…  {name!r}  type={r.get('account_type') or '-'}  "
                  f"conn={item[:10] or '-'} ({live})  syncs={r.get('enabled')}  "
                  f"removed={st.get('removed')}  nick={st.get('nickname') or '-'}  "
                  f"rows={len(by_acct[aid])}  source={src}")

        groups = defaultdict(list)
        for t in rows:
            if t["amount"] > 0 and t["id"] not in excluded:
                groups[(str(t["date"])[:10], f"{t['amount']:.2f}")].append(t)
        pairs, samples, within = defaultdict(int), defaultdict(list), 0
        for g in groups.values():
            accts = sorted({t["account_id"] for t in g})
            if len(g) > 1 and len(accts) == 1:
                within += 1
            if len(accts) > 1:
                key = tuple(accts[:2])
                pairs[key] += 1
                if len(samples[key]) < 3:
                    samples[key].append(" | ".join(
                        f"{t['description'][:24]} [{dupes.get(t['id'], '-')}]" for t in g[:2]))
        print(f"same day + same amount, one account: {within}")
        print("same day + same amount, two accounts:")
        for (a, b), n in sorted(pairs.items(), key=lambda x: -x[1])[:10]:
            print(f"  {a[:10]}… + {b[:10]}…  {n}")
            for line in samples[(a, b)]:
                print(f"      {line}")
