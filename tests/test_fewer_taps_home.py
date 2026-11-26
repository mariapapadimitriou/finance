"""Fewer taps, Home and set-up (P12, P6; the tap audit, 2026-11-26).

Home asks "Is $5,850 from Acme your pay?" with Yes / No and Undo (P12a–c):
the found pay says when it came in and where, and each answer can be put
back as it was through POST /api/transactions/undo.
"""

from test_income_bills import client  # noqa: F401  (the fixture)


def found(c):
    return c.get("/api/income-bills").get_json()["candidates"]


def test_a_found_pay_says_when_it_came_in_and_where(client):
    [c] = found(client)
    assert c["seen"][0] == c["last"] and len(c["seen"]) == 2 and c["seen"][0] > c["seen"][1]
    assert c["account"]


def test_yes_undoes_back_to_a_question(client):
    d = client.post("/api/income-bills/pay/answer", json={"payer": "Northwind Ltd", "answer": "yes"}).get_json()
    assert d["pays"] and d["undo"]["marks"]["income_pays"]["pays"] == []
    assert client.post("/api/transactions/undo", json=d["undo"]).status_code == 200
    after = client.get("/api/income-bills").get_json()
    assert after["pays"] == [] and [c["payer"] for c in after["candidates"]] == ["Northwind Ltd"]
    assert after["checked"]["income"] is None


def test_no_undoes_back_to_a_question(client):
    d = client.post("/api/income-bills/pay/answer", json={"payer": "Northwind Ltd", "answer": "no"}).get_json()
    assert d["candidates"] == []
    assert client.post("/api/transactions/undo", json=d["undo"]).status_code == 200
    assert [c["payer"] for c in found(client)] == ["Northwind Ltd"]
