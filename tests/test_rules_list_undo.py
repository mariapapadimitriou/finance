"""TEST-47: Categories and rules › a rule › Change › Save › Undo. The list
says the new category at once and the old one again after Undo, and only
the latest load lands, so a slower earlier one can't put back what Undo
changed (2026-11-19). The server side: Undo really restores the rule."""

from __future__ import annotations

from pathlib import Path

from test_trips import add, client, tx  # noqa: F401  (client is a fixture)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ios/Pearl/Views/Profile/CategoriesRulesView.swift"


def test_the_list_shows_the_change_and_its_undo_at_once():
    src = SRC.read_text()
    assert "let onSaved: (String, String, JSONValue?) -> Void" in src
    assert "category, reply.undo)" in src
    assert "shown[rule.id] = category" in src
    assert "await MainActor.run { shown[rule.id] = was }" in src
    assert "book.rules.map { r in shown[r.id].map { r.with(category: $0) } ?? r }" in src


def test_only_the_latest_load_lands():
    src = SRC.read_text()
    load = src[src.index("private func load() async {"):src.index("private func undoCall")]
    assert "loads += 1" in load and "let mine = loads" in load
    guard = load.index("guard mine == loads else { return }")
    assert guard < load.index("book = rules") and guard < load.index("learned = ")
    assert "shown = [:]" in load


def test_undo_puts_the_rule_back_on_the_server(client):  # noqa: F811
    add(client, tx("PAI NORTHERN THAI", 60.0, "2026-11-10", category="Dining"))
    client.st.set_override("pai northern thai", "Dining", move_rows=True)
    rid = "merchant:pai northern thai"

    def category():
        return next(r["category"] for r in client.get("/api/rules").get_json()["rules"] if r["id"] == rid)

    reply = client.put(f"/api/rules/{rid}", json={"category": "Coffee"}).get_json()
    assert category() == "Coffee"
    assert client.post("/api/transactions/undo", json=reply["undo"]).status_code == 200
    assert category() == "Dining"
