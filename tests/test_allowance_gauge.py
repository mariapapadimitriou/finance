"""The Allowance gauge on Home (H-00r v2, n-home-gauge) and the meter on
Cash flow's month card (T-01r, n-cf-meter), both from the server's own
numbers: `allowance`, `spent`, `zone`, `shown`, `per_day`, `days_left`."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAUGE = (ROOT / "ios/Pearl/Views/Components/AllowanceGauge.swift").read_text(encoding="utf-8")
ADDS = (ROOT / "ios/Pearl/Views/Home/AddsUpView.swift").read_text(encoding="utf-8")
TV = (ROOT / "ios/Pearl/Views/Transactions/TransactionsView.swift").read_text(encoding="utf-8")
MODELS = (ROOT / "ios/Pearl/API/Models.swift").read_text(encoding="utf-8")


def test_the_app_reads_the_servers_numbers():
    for key in ('case total = "allowance"', 'case perDay = "per_day"', 'case billsPaid = "bills_paid"',
                "spent, zone, rows"):
        assert key in MODELS, key


def test_three_zones_and_their_words():
    assert 'case .ok: return "On track"' in GAUGE
    assert 'case .close: return "Getting close"' in GAUGE
    assert 'case .over: return "Over"' in GAUGE
    # 80 / 20 / 15 of the Allowance on both the gauge and the meter.
    assert "static let scale = 1.15" in GAUGE and "[80, 20, 15][i] / 115" in GAUGE


def test_over_says_so_and_shows_the_allowance():
    assert '"Over your Allowance"' in GAUGE and '"Your Allowance"' in GAUGE
    assert "Allowance" in GAUGE and "safe to spend" not in GAUGE.lower()


def test_cash_flow_card_is_this_months_allowance_only():
    assert "AllowanceMonthSummary(" in TV and "AddsUpRow { showingAddsUp = true }" in TV
    # A past month has no Allowance: it keeps Came in and Leftover.
    assert "a.month == m" in TV and "MonthSummary(month:" in TV
    assert ".navigationDestination(isPresented: $showingAddsUp) { AddsUpView() }" in TV


def test_how_it_adds_up_uses_the_rows():
    for words in ('"Came in"', '"Bills"', '"Moved to savings"', '"Allowance"', '"Spent so far"'):
        assert words in ADDS, words
    assert '(row("bills") ?? 0) + (allowance.billsPaid ?? 0)' in ADDS
