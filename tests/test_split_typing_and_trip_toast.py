"""TEST-48 (round 5 re-test):
* How to split with the number pad up: the purchase and the method switch
  are pinned above the rows, the status line rides above Save, and the row
  being typed in is scrolled into view.
* Every amount well has cents: "60.00", never "60".
* Quick sort's trip Yes says "Trip to Montréal made" with an Undo that
  takes the trip away and brings the card back (G7-TripAsk), 2026-11-19."""

from __future__ import annotations

from pathlib import Path

from test_trips import away, client, home  # noqa: F401  (client is a fixture)

ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / "ios/Pearl/Views/Transactions/SplitFlow.swift"
QUICK = ROOT / "ios/Pearl/Views/Review/QuickSortView.swift"


def test_header_and_switch_stay_while_typing():
    src = FLOW.read_text()
    assert "private var pinned: Bool { step == 1 && focused != nil }" in src
    body = src[src.index("var body: some View {"):src.index("ScrollViewReader { scroller in")]
    assert "if pinned {" in body and "head" in body and "methodControl" in body
    assert "if !pinned { head }" in src and "if !pinned { methodControl }" in src
    footer = src[src.index("private var footer: some View {"):src.index("private func save() async")]
    assert "if pinned && mode != \"unknown\"" in footer and "status" in footer
    assert "scroller.scrollTo(key, anchor: .center)" in src
    assert "scrollTo(Self.statusID" not in src


def test_amount_wells_have_cents():
    src = FLOW.read_text()
    assert "v[p.name] = Self.plainCents(Int((p.share * 100).rounded()))" in src
    assert 'values[k] = mode == "amount" ? Self.plainCents(c) : Self.plain(Double(c) / 100)' in src
    carry = (ROOT / "ios/Pearl/Views/Transactions/SplitCarry.swift").read_text()
    assert 'String(format: "%.2f", Double(r.cents) / 100)' in carry


def test_quick_sort_trip_yes_can_be_undone():
    """Quick sort has no toast since 2026-11-20 (it sat over Skip and Yes);
    the trip just made is the card's Undo, at its top right."""
    src = QUICK.read_text()
    assert "case trip(MadeTrip)" in src and "case .trip(let made): await undoTrip(made)" in src
    assert 'api.delete("api/trips/\\(made.trip)", query: ["undo": "1"])' in src
    assert "tripAt = max(tripAt - 1, 0)" in src


def test_undoing_a_trip_brings_its_question_back(client):  # noqa: F811
    home(client)
    away(client)
    [ask] = client.get("/api/trips/asks").get_json()["asks"]
    made = client.post(f"/api/trips/asks/{ask['id']}/yes").get_json()["trip"]
    assert made["name"] == "Trip to Montréal"
    assert client.get("/api/trips/asks").get_json()["asks"] == []
    assert client.delete(f"/api/trips/{made['id']}?undo=1").status_code == 200
    [again] = client.get("/api/trips/asks").get_json()["asks"]
    assert again["id"] == ask["id"]
