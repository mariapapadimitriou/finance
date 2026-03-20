# MacroLens — Macro Dashboard

A Bloomberg-connected macro dashboard with Equities and Fixed Income tabs for US and Canadian markets.

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the backend
```bash
python app.py
# Runs on http://localhost:5050
```

### 3. Open the frontend
```bash
open index.html
# Or serve it: python -m http.server 8080
```

---

## Bloomberg Integration

The backend wraps a `bdh()` function in `app.py`. By default it uses mock data so you can develop and test without a Bloomberg Terminal.

**To connect real Bloomberg data:**

1. Install `blpapi` from Bloomberg's developer portal
2. Install the `xbbg` wrapper: `pip install xbbg`
3. In `app.py`, uncomment the Bloomberg block inside `bdh()` and comment out the mock block:

```python
def bdh(securities, fields, start_date, end_date):
    from xbbg import blp
    df = blp.bdh(tickers=securities, flds=fields,
                 start_date=start_date, end_date=end_date)
    df = df.stack(level=0).reset_index()
    df.columns = ['date', 'security'] + fields
    return df
```

4. Make sure your Bloomberg Terminal is open and the API session is active.

The `bdh()` function signature is identical to Bloomberg's, accepting:
- `securities` — list of Bloomberg tickers (e.g. `["XLK US Equity", "SPY US Equity"]`)
- `fields` — list of Bloomberg fields (e.g. `["PX_LAST", "PX_VOLUME"]`)
- `start_date` / `end_date` — `"YYYYMMDD"` strings

---

## Features

### Equities Tab
- **Sector Returns Bar Chart** — horizontal bars showing % return for each sector over the selected lookback period
- **Indexed Performance Line Chart** — all sectors normalized to 100 at period start, showing relative performance
- **Up/Down Volume Flow** — per-sector breakdown of volume on up days vs down days, with flow ratio (>1 = bullish flow)
- **Dollar Volume Bar Chart** — average daily dollar volume by sector, colored green/red by flow ratio
- **Daily Return Heatmap** — color-coded matrix of each sector's daily returns over the period

### Fixed Income Tab
- **Yield Curve Chart** — start vs end curve overlaid, showing steepening/flattening visually
- **Key Spreads** — 2s10s and 3m10y in bps, with change over period and curve shape label
- **Tenor Snapshot Table** — all tenors with start yield, end yield, and basis point change
- **2s10s Time Series** — daily spread with zero line for inversion reference
- **AI Analysis** — Claude-powered written analysis of curve dynamics, macro drivers, and implications

### Controls
- **Market toggle** — US 🇺🇸 / CA 🇨🇦 (switches all tickers and yield curve benchmarks)
- **Lookback selector** — 5D / 1M / 3M / 6M / 1Y

---

## Securities Used

### US Equities (SPDR Sector ETFs)
| Sector | Ticker |
|---|---|
| Technology | XLK US Equity |
| Financials | XLF US Equity |
| Health Care | XLV US Equity |
| Energy | XLE US Equity |
| Industrials | XLI US Equity |
| Consumer Discretionary | XLY US Equity |
| Consumer Staples | XLP US Equity |
| Utilities | XLU US Equity |
| Real Estate | XLRE US Equity |
| Materials | XLB US Equity |
| Communication Services | XLC US Equity |

### CA Equities (iShares/BMO Sector ETFs)
| Sector | Ticker |
|---|---|
| Technology | XIT CN Equity |
| Financials | XFN CN Equity |
| Energy | XEG CN Equity |
| Materials | XMA CN Equity |
| Real Estate | XRE CN Equity |
| Broad Market | XIU CN Equity |
| Utilities | XUT CN Equity |
| Health Care | XHC CN Equity |

### Yield Curves
- **US**: USGG3M–USGG30Y (Bloomberg Generic US Government)
- **CA**: GCAN3M–GCAN30Y (Bloomberg Generic Canada Government)
