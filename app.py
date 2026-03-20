"""
MacroLens Backend v2
Wraps blpapi BDH. Falls back to realistic mock data if Bloomberg is unavailable.
Markets: US, CA, MX, BR, CL
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# ─── Bloomberg BDH wrapper ────────────────────────────────────────────────────
def bdh(securities, fields, start_date, end_date):
    """
    Wraps Bloomberg BDH. Returns DataFrame: security | date | <fields...>

    To use real Bloomberg, uncomment below and comment the mock block:

    from xbbg import blp
    df = blp.bdh(tickers=securities, flds=fields,
                 start_date=start_date, end_date=end_date)
    df = df.stack(level=0).reset_index()
    df.columns = ['date', 'security'] + fields
    return df
    """
    return _mock_bdh(securities, fields, start_date, end_date)


# ─── Market definitions ───────────────────────────────────────────────────────

# Bloomberg ticker note:
#   US  — S&P 500 GICS sector sub-indices (S5XXXX Index) — confirmed format
#   CA  — S&P/TSX GICS sector sub-indices (STSEXXXX Index) — verify on terminal
#   MX  — S&P/BMV IPC sector sub-indices (BMBVXXXX Index) — verify on terminal
#   BR  — B3/Bovespa official sector indices — confirmed format
#   CL  — S&P/IPSA sector sub-indices (CLXXX Index) — verify on terminal

SECTORS = {
    "US": {
        "Technology":    "S5INFT Index",
        "Financials":    "S5FINL Index",
        "Health Care":   "S5HLTH Index",
        "Energy":        "S5ENRS Index",
        "Industrials":   "S5INDU Index",
        "Cons. Discr.":  "S5COND Index",
        "Cons. Staples": "S5CONS Index",
        "Utilities":     "S5UTIL Index",
        "Real Estate":   "S5REAL Index",
        "Materials":     "S5MATR Index",
        "Comm. Svcs":    "S5TELS Index",
    },
    "CA": {
        "Energy":        "STSENRGS Index",
        "Financials":    "STSEFINL Index",
        "Materials":     "STSEMATR Index",
        "Industrials":   "STSEINDUS Index",
        "Technology":    "STSEINFT Index",
        "Cons. Discr.":  "STSECOND Index",
        "Cons. Staples": "STSECONS Index",
        "Utilities":     "STSEUTIL Index",
        "Health Care":   "STSEHLTH Index",
        "Real Estate":   "STSEREAL Index",
        "Comm. Svcs":    "STSTELS Index",
    },
    "MX": {
        "Broad Market":  "MEXBOL Index",
        "Financials":    "BMBVFINL Index",
        "Consumer":      "BMBVCONS Index",
        "Materials":     "BMBVMATR Index",
        "Industrials":   "BMBVINDUS Index",
        "Telecom":       "BMBVTELS Index",
        "Real Estate":   "BMBVREAL Index",
    },
    "BR": {
        "Broad Market":  "IBOV Index",
        "Financials":    "IFNC Index",
        "Materials":     "IMAT Index",
        "Utilities":     "UTIL Index",
        "Consumer":      "ICON Index",
        "Real Estate":   "IMOB Index",
        "Energy":        "IENEE Index",
    },
    "CL": {
        "Broad Market":  "IPSA Index",
        "Financials":    "CLXFINL Index",
        "Utilities":     "CLXUTIL Index",
        "Materials":     "CLXMATR Index",
        "Consumer":      "CLXCOND Index",
        "Real Estate":   "CLXREAL Index",
        "Energy":        "CLXENRS Index",
    },
}

# Set of all sector index tickers — used to prevent mock engine from treating them as yields
SECTOR_TICKERS = {t for secs in SECTORS.values() for t in secs.values()}

YIELD_CURVES = {
    "US": {"3M":"USGG3M Index","6M":"USGG6M Index","1Y":"USGG12M Index",
           "2Y":"USGG2Y Index","3Y":"USGG3Y Index","5Y":"USGG5Y Index",
           "7Y":"USGG7Y Index","10Y":"USGG10Y Index","20Y":"USGG20Y Index","30Y":"USGG30Y Index"},
    "CA": {"3M":"GCAN3M Index","6M":"GCAN6M Index","1Y":"GCAN12M Index",
           "2Y":"GCAN2Y Index","3Y":"GCAN3Y Index","5Y":"GCAN5Y Index",
           "7Y":"GCAN7Y Index","10Y":"GCAN10Y Index","20Y":"GCAN20Y Index","30Y":"GCAN30Y Index"},
    "MX": {"3M":"MXBM3M Index","6M":"MXBM6M Index","1Y":"MXBM12M Index",
           "2Y":"MXBM2Y Index","3Y":"MXBM3Y Index","5Y":"MXBM5Y Index",
           "10Y":"MXBM10Y Index","20Y":"MXBM20Y Index","30Y":"MXBM30Y Index"},
    "BR": {"3M":"BZSTWI3M Index","6M":"BZSTWI6M Index","1Y":"BZSTWI1Y Index",
           "2Y":"BZSTWI2Y Index","5Y":"BZSTWI5Y Index","10Y":"BZSTWI10Y Index"},
    "CL": {"3M":"CHSWAPRATE3M Index","1Y":"CHSWAPRATE1Y Index",
           "2Y":"CHSWAPRATE2Y Index","5Y":"CHSWAPRATE5Y Index","10Y":"CHSWAPRATE10Y Index"},
}

YIELD_BASES = {
    "US": [5.25,5.20,5.00,4.70,4.50,4.30,4.25,4.20,4.35,4.40],
    "CA": [4.80,4.75,4.60,4.30,4.10,3.95,3.90,3.88,3.95,3.98],
    "MX": [11.2,11.0,10.8,10.5,10.3,10.1,9.9,9.8,9.9,10.0],
    "BR": [11.5,11.2,11.0,10.8,10.6,10.5],
    "CL": [5.5,5.3,5.1,4.9,4.7,4.5],
}

SECTOR_BASES = {
    # Approximate index levels (2024); update on Bloomberg connect
    "US":  [3900, 680, 1580, 730, 1080, 1280, 830, 330, 220, 540, 290],  # 11 S&P 500 GICS
    "CA":  [2800, 1800, 1500, 1200, 900, 950, 750, 1600, 650, 1900, 480], # 11 S&P/TSX GICS
    "MX":  [52000, 1800, 1200, 3500, 2200, 1600, 1800],                   # 7 BMV sectors
    "BR":  [125000, 13000, 5000, 4000, 2800, 900, 6500],                  # 7 B3 sectors
    "CL":  [6800, 2200, 4500, 3200, 1800, 2100, 2800],                    # 7 IPSA sectors
}

DIFFICULTY_TICKERS = {
    "VIX":          "VIX Index",
    "VVIX":         "VVIX Index",
    "PutCall":      "PCRATIO Index",
    "HYSpread":     "LF98OAS Index",
    "TED":          "TEDSP Index",
    "SkewIndex":    "SKEW Index",
    "CorrelBreak":  "JCJ Index",
    "ATR_SPX":      "SPX Index",
    "RealizedVol":  "SPX Index",
    "BidAskProxy":  "BASPREAD Index",
    "Dispersion":   "CBOEDISP Index",
    "FundingStress":"SOFR1Y Index",
    "BreadthDecay": "NYAD Index",
}

FACTOR_PAIRS = [
    ("Large vs Small Cap",     "SPY US Equity",  "IWM US Equity",  "Large outperforms", "Small outperforms"),
    ("Value vs Growth",        "IVE US Equity",  "IVW US Equity",  "Value outperforms", "Growth outperforms"),
    ("Gold vs Gold Miners",    "GLD US Equity",  "GDX US Equity",  "Gold leads miners", "Miners lead gold"),
    ("Oil/Gas vs Energy Stks", "USO US Equity",  "XLE US Equity",  "Commodity leads",   "Stocks lead commodity"),
    ("Momentum vs Broad",      "MTUM US Equity", "SPY US Equity",  "Momentum working",  "Momentum fading"),
    ("Quality vs High Beta",   "QUAL US Equity", "SPHB US Equity", "Risk-off quality",  "Risk-on beta"),
    ("Low Vol vs High Beta",   "USMV US Equity", "SPHB US Equity", "Defensive bid",     "Risk appetite strong"),
    ("EM vs DM",               "EEM US Equity",  "EFA US Equity",  "EM outperforms",    "DM outperforms"),
    ("Defensive vs Cyclical",  "XLU US Equity",  "XLY US Equity",  "Risk-off bid",      "Cyclical strength"),
    ("Bonds vs Equities",      "TLT US Equity",  "SPY US Equity",  "Flight to safety",  "Risk-on equities"),
    ("Dollar vs EM FX",        "UUP US Equity",  "EEM US Equity",  "Dollar strength",   "EM carry working"),
    ("Semis vs Broad Tech",    "SOXX US Equity", "XLK US Equity",  "Semis leading",     "Semis lagging"),
    ("Small Value vs Growth",  "IWN US Equity",  "IWO US Equity",  "Value cycle",       "Growth cycle"),
    ("Dividend vs Growth",     "DVY US Equity",  "IWO US Equity",  "Income defensive",  "Growth momentum"),
]

# ─── Mock data engine ─────────────────────────────────────────────────────────

def _get_dates(start_date, end_date):
    start = datetime.strptime(start_date, "%Y%m%d")
    end   = datetime.strptime(end_date,   "%Y%m%d")
    return [start + timedelta(d) for d in range((end-start).days+1)
            if (start + timedelta(d)).weekday() < 5]

def _simulate_price(base, n, rng, drift=0.0003, vol=0.012):
    ret = rng.normal(drift, vol, n)
    p = [base]
    for r in ret[1:]: p.append(p[-1]*(1+r))
    return np.array(p)

def _simulate_yields(base, n, rng, vol=0.005):
    ch = rng.normal(0, vol, n)
    y = [base]
    for c in ch[1:]: y.append(max(0.01, y[-1]+c))
    return np.array(y)

def _get_base(sec):
    known = {
        "SPY US Equity":420,"IWM US Equity":190,"IVE US Equity":168,
        "IVW US Equity":185,"GLD US Equity":185,"GDX US Equity":32,
        "USO US Equity":72,"MTUM US Equity":185,"QUAL US Equity":148,
        "USMV US Equity":78,"SPHB US Equity":84,"EEM US Equity":42,
        "EFA US Equity":78,"XCS CN Equity":20,"XCV CN Equity":36,
        "XCG CN Equity":38,"SMLL11 BZ Equity":90,"IGPA CI Index":25000,
        "TLT US Equity":92,"UUP US Equity":28,"SOXX US Equity":520,
        "IWN US Equity":160,"IWO US Equity":245,"DVY US Equity":125,
        "VIX Index":18,"VVIX Index":90,"PCRATIO Index":0.85,
        "LF98OAS Index":350,"TEDSP Index":0.25,"SKEW Index":120,
        "JCJ Index":0.6,"BASPREAD Index":0.4,
        "CBOEDISP Index":14,"SOFR1Y Index":4.8,"NYAD Index":0.58,
    }
    if sec in known: return known[sec]
    for mkt, secs in SECTORS.items():
        for i,(name,ticker) in enumerate(secs.items()):
            if ticker == sec:
                bases = SECTOR_BASES.get(mkt,[100]*20)
                return bases[i] if i < len(bases) else 100
    for mkt, tenors in YIELD_CURVES.items():
        for j,(tenor,ticker) in enumerate(tenors.items()):
            if ticker == sec:
                bases = YIELD_BASES.get(mkt,[5.0]*10)
                return bases[j] if j < len(bases) else 5.0
    return 100

def _mock_bdh(securities, fields, start_date, end_date):
    rng   = np.random.default_rng(42)
    dates = _get_dates(start_date, end_date)
    rows  = []
    for sec in securities:
        base = _get_base(sec)
        is_vol_idx = any(k in sec for k in ["VIX","VVIX","PCRATIO","LF98OAS","TEDSP","SKEW","JCJ","BASPREAD","CBOEDISP","NYAD"])
        is_yield   = ("Index" in sec and not is_vol_idx and "SPX" not in sec
                      and sec not in SECTOR_TICKERS)
        if is_vol_idx:
            vol_map = {"VIX":0.8,"VVIX":2.5,"PCRATIO":0.03,"LF98OAS":8,"TEDSP":0.02,"SKEW":3,"JCJ":0.02,"BASPREAD":0.03,"CBOEDISP":1.2,"NYAD":0.025}
            v = next((v for k,v in vol_map.items() if k in sec), 0.05)
            prices = _simulate_yields(base, len(dates), rng, vol=v)
        elif is_yield:
            prices = _simulate_yields(base, len(dates), rng)
        else:
            prices = _simulate_price(base, len(dates), rng)
        for i,dt in enumerate(dates):
            row = {"security": sec, "date": dt.strftime("%Y-%m-%d")}
            for field in fields:
                row[field] = round(float(prices[i]), 4)
            rows.append(row)
    return pd.DataFrame(rows)

def _trim(arr, n):
    return arr[-n:] if len(arr) > n else arr

def _parse_params():
    market   = request.args.get("market", "US")
    lookback = int(request.args.get("lookback", 20))
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=lookback + 40)
    return market, lookback, start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/api/equities/returns")
def equities_returns():
    market, lookback, start_date, end_date = _parse_params()
    sectors = SECTORS.get(market, SECTORS["US"])
    df = bdh(list(sectors.values()), ["PX_LAST"], start_date, end_date)
    df["date"] = pd.to_datetime(df["date"])
    results = []
    for name, sec in sectors.items():
        sub = df[df["security"]==sec].sort_values("date")
        if len(sub) < 2: continue
        prices = _trim(sub["PX_LAST"].values, lookback)
        dates  = _trim(sub["date"].dt.strftime("%Y-%m-%d").tolist(), lookback)
        pct    = (prices[-1]-prices[0])/prices[0]*100
        daily  = [round((prices[i]-prices[i-1])/prices[i-1]*100,4) for i in range(1,len(prices))]
        results.append({"sector":name,"ticker":sec,"return_pct":round(pct,2),
                        "prices":[round(p,2) for p in prices],"dates":dates,"daily_returns":daily})
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    return jsonify({"market":market,"lookback":lookback,"sectors":results})


@app.route("/api/equities/volume")
def equities_volume():
    market, lookback, start_date, end_date = _parse_params()
    sectors = SECTORS.get(market, SECTORS["US"])
    df = bdh(list(sectors.values()), ["PX_LAST","PX_VOLUME"], start_date, end_date)
    df["date"] = pd.to_datetime(df["date"])
    results = []
    for name, sec in sectors.items():
        sub = df[df["security"]==sec].sort_values("date")
        if len(sub) < 2: continue
        prices = _trim(sub["PX_LAST"].values, lookback)
        vols   = _trim(sub["PX_VOLUME"].values if "PX_VOLUME" in sub.columns else np.ones(len(sub))*1e6, lookback)
        dates  = _trim(sub["date"].dt.strftime("%Y-%m-%d").tolist(), lookback)
        dvol   = [round(p*v/1e9,3) for p,v in zip(prices,vols)]
        up_v   = sum(v for i,v in enumerate(dvol[1:],1) if prices[i]>prices[i-1])
        dn_v   = sum(v for i,v in enumerate(dvol[1:],1) if prices[i]<prices[i-1])
        results.append({"sector":name,"ticker":sec,"dollar_volume":dvol,"dates":dates,
                        "avg_vol_bn":round(np.mean(dvol),3),"up_volume":round(up_v,2),
                        "down_volume":round(dn_v,2),"flow_ratio":round(up_v/dn_v,3) if dn_v>0 else 9.99})
    results.sort(key=lambda x: x["flow_ratio"], reverse=True)
    return jsonify({"market":market,"lookback":lookback,"sectors":results})


@app.route("/api/equities/factors")
def equities_factors():
    market, lookback, start_date, end_date = _parse_params()
    all_secs = list({s for _,a,b,_,_ in FACTOR_PAIRS for s in [a,b]})
    df = bdh(all_secs, ["PX_LAST"], start_date, end_date)
    df["date"] = pd.to_datetime(df["date"])
    results = []
    for name, sec_a, sec_b, pos_lbl, neg_lbl in FACTOR_PAIRS:
        sa = df[df["security"]==sec_a].sort_values("date")
        sb = df[df["security"]==sec_b].sort_values("date")
        if len(sa)<2 or len(sb)<2: continue
        n  = min(len(sa), len(sb), lookback)
        pa = sa["PX_LAST"].values[-n:]
        pb = sb["PX_LAST"].values[-n:]
        dates = sa["date"].dt.strftime("%Y-%m-%d").tolist()[-n:]
        ra    = pa/pa[0]*100
        rb    = pb/pb[0]*100
        spread = [round(a-b,4) for a,b in zip(ra,rb)]
        cur   = spread[-1]
        results.append({"name":name,"spread":spread,"dates":dates,
                        "current":round(cur,2),"period_change":round(cur-spread[0],2),
                        "regime":pos_lbl if cur>=0 else neg_lbl,
                        "ticker_a":sec_a,"ticker_b":sec_b})
    return jsonify({"market":market,"lookback":lookback,"factors":results})


@app.route("/api/fixedincome/yields")
def fixed_income_yields():
    market, lookback, start_date, end_date = _parse_params()
    tenors = YIELD_CURVES.get(market, YIELD_CURVES["US"])
    df = bdh(list(tenors.values()), ["PX_LAST"], start_date, end_date)
    df["date"] = pd.to_datetime(df["date"])
    curve_start, curve_end, time_series = {}, {}, {}
    for label, sec in tenors.items():
        sub = df[df["security"]==sec].sort_values("date")
        if sub.empty: continue
        vals  = sub["PX_LAST"].values
        dates = sub["date"].dt.strftime("%Y-%m-%d").tolist()
        n = min(lookback, len(vals))
        curve_start[label] = round(float(vals[-n]),4)
        curve_end[label]   = round(float(vals[-1]),4)
        time_series[label] = {"dates":dates[-n:],"yields":[round(float(v),4) for v in vals[-n:]]}
    ks, ke = curve_start, curve_end
    sk = "3M" if "3M" in ks else list(ks.keys())[0]
    lk = "10Y" if "10Y" in ks else list(ks.keys())[-1]
    mk = "2Y"  if "2Y"  in ks else list(ks.keys())[len(ks)//2]
    def spr(c,a,b): return round(c.get(b,0)-c.get(a,0),4)
    return jsonify({
        "market":market,"lookback":lookback,
        "curve_start":curve_start,"curve_end":curve_end,"time_series":time_series,
        "spreads":{"2s10s_start":spr(ks,mk,lk),"2s10s_end":spr(ke,mk,lk),
                   "3m10y_start":spr(ks,sk,lk),"3m10y_end":spr(ke,sk,lk),
                   "steepening":spr(ke,mk,lk)>spr(ks,mk,lk),"inverted":spr(ke,mk,lk)<0}
    })


@app.route("/api/difficulty")
def trading_difficulty():
    market, lookback, start_date, end_date = _parse_params()
    diff_secs = list(dict.fromkeys(DIFFICULTY_TICKERS.values()))
    df = bdh(diff_secs, ["PX_LAST"], start_date, end_date)
    df["date"] = pd.to_datetime(df["date"])

    components = {}
    dates_ref  = None
    WEIGHTS    = {"VIX":0.22,"VVIX":0.10,"PutCall":0.07,"HYSpread":0.13,
                  "TED":0.08,"SkewIndex":0.05,"CorrelBreak":0.07,
                  "ATR_SPX":0.05,"RealizedVol":0.04,"BidAskProxy":0.04,
                  "Dispersion":0.07,"FundingStress":0.04,"BreadthDecay":0.04}
    LABELS     = {"VIX":"VIX (Implied Vol)","VVIX":"VVIX (Vol of Vol)",
                  "PutCall":"Put/Call Ratio","HYSpread":"HY Credit Spread",
                  "TED":"TED Spread","SkewIndex":"SKEW Index",
                  "CorrelBreak":"Correl. Breakdown","ATR_SPX":"ATR (SPX)",
                  "RealizedVol":"Realized Volatility","BidAskProxy":"Bid-Ask Proxy",
                  "Dispersion":"Sector Dispersion","FundingStress":"Funding Stress",
                  "BreadthDecay":"Breadth Decay"}

    for name, sec in DIFFICULTY_TICKERS.items():
        sub = df[df["security"]==sec].sort_values("date")
        if sub.empty: continue
        vals  = _trim(sub["PX_LAST"].values, lookback)
        dates = _trim(sub["date"].dt.strftime("%Y-%m-%d").tolist(), lookback)
        if dates_ref is None or len(dates)>len(dates_ref): dates_ref = dates

        if name == "RealizedVol" and len(vals) >= 5:
            rets = np.diff(np.log(np.maximum(vals, 1e-6)))
            rvol = []
            for i in range(len(rets)):
                w = rets[max(0,i-19):i+1]
                rvol.append(np.std(w)*np.sqrt(252)*100 if len(w)>1 else 0)
            vals = np.array([rvol[0]] + rvol)[:len(vals)]

        mn, mx = np.min(vals), np.max(vals)
        norm = ((vals-mn)/(mx-mn+1e-9)*100).tolist()

        components[name] = {
            "normalized": [round(v,2) for v in norm],
            "raw":        [round(float(v),4) for v in vals],
            "weight":     WEIGHTS.get(name,0.05),
            "label":      LABELS.get(name,name),
        }

    n = min(lookback, min((len(c["normalized"]) for c in components.values()), default=1))
    composite = []
    for i in range(n):
        score, tw = 0, 0
        for comp in components.values():
            nv = comp["normalized"]
            idx = len(nv)-n+i
            if 0 <= idx < len(nv):
                score += nv[idx]*comp["weight"]; tw += comp["weight"]
        composite.append(round(score/tw if tw>0 else 0, 2))

    dates_out = (dates_ref or [])[-n:]

    def classify(s):
        if s>=75: return "EXTREME"
        if s>=60: return "HIGH"
        if s>=40: return "MODERATE"
        if s>=25: return "LOW"
        return "CALM"

    cur = composite[-1] if composite else 50
    pct = round(sum(1 for v in composite if v<=cur)/len(composite)*100,1) if composite else 50

    return jsonify({
        "market":market,"lookback":lookback,"dates":dates_out,
        "composite":composite,"components":components,
        "summary":{"current_score":cur,"regime":classify(cur),
                   "avg_score":round(float(np.mean(composite)),2) if composite else 50,
                   "percentile":pct},
        "equation":"Score = 0.22·VIX + 0.13·HYSpread + 0.10·VVIX + 0.08·TED + 0.07·CorrBreak + 0.07·P/C + 0.07·Dispersion + 0.05·SKEW + 0.05·ATR + 0.04·RealVol + 0.04·BidAsk + 0.04·FundingStress + 0.04·BreadthDecay  [all normalized 0–100]"
    })


# ─── Macro static data ────────────────────────────────────────────────────────
# Real Bloomberg: replace with BDP calls to CPI YOY Index, FDTR Index, etc.

INFLATION_DATA = {
    "US": [
        {"label": "CPI YoY",      "current": 3.1, "prev": 3.4, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
        {"label": "Core CPI YoY", "current": 3.8, "prev": 3.9, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
        {"label": "PCE YoY",      "current": 2.5, "prev": 2.6, "trend": "DOWN", "unit": "%", "period": "Jan 2026"},
    ],
    "CA": [
        {"label": "CPI YoY",      "current": 1.9, "prev": 2.1, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
        {"label": "Core CPI YoY", "current": 2.1, "prev": 2.3, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
    ],
    "MX": [
        {"label": "CPI YoY",      "current": 3.8, "prev": 3.7, "trend": "UP",   "unit": "%", "period": "Feb 2026"},
        {"label": "Core CPI YoY", "current": 3.6, "prev": 3.8, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
    ],
    "BR": [
        {"label": "IPCA YoY",     "current": 5.1, "prev": 4.8, "trend": "UP",   "unit": "%", "period": "Feb 2026"},
        {"label": "Core IPCA",    "current": 4.6, "prev": 4.3, "trend": "UP",   "unit": "%", "period": "Feb 2026"},
    ],
    "CL": [
        {"label": "CPI YoY",      "current": 4.2, "prev": 4.5, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
        {"label": "Core CPI YoY", "current": 3.9, "prev": 4.1, "trend": "DOWN", "unit": "%", "period": "Feb 2026"},
    ],
}

CENTRAL_BANK_DATA = {
    "US": {
        "bank": "Federal Reserve",    "policy_rate": 4.25, "last_change": -0.25,
        "last_change_date": "Dec 11, 2025", "next_meeting": "May 7, 2026",
        "bias": "HOLD",
        "bias_note": "Data-dependent pause; watching PCE and labour market for next move.",
    },
    "CA": {
        "bank": "Bank of Canada",     "policy_rate": 3.00, "last_change": -0.25,
        "last_change_date": "Jan 29, 2026", "next_meeting": "Apr 16, 2026",
        "bias": "EASING",
        "bias_note": "Easing cycle ongoing; inflation back near target, growth risks dominate.",
    },
    "MX": {
        "bank": "Banxico",            "policy_rate": 9.00, "last_change": -0.50,
        "last_change_date": "Feb 6, 2026",  "next_meeting": "Mar 27, 2026",
        "bias": "EASING",
        "bias_note": "Cutting cycle continues cautiously; peso stability constraining pace.",
    },
    "BR": {
        "bank": "Banco Central do Brasil", "policy_rate": 14.75, "last_change": +1.00,
        "last_change_date": "Mar 19, 2026", "next_meeting": "May 7, 2026",
        "bias": "TIGHTENING",
        "bias_note": "Re-tightening cycle underway; IPCA above target, fiscal concerns persist.",
    },
    "CL": {
        "bank": "Banco Central de Chile", "policy_rate": 5.00, "last_change": -0.25,
        "last_change_date": "Jan 29, 2026", "next_meeting": "Apr 1, 2026",
        "bias": "HOLD",
        "bias_note": "On hold; inflation declining but global uncertainty warrants caution.",
    },
}

MACRO_CALENDAR = [
    {"date":"2026-03-06","market":"US","event":"Non-Farm Payrolls","period":"Feb 2026",
     "previous":143,"expected":155,"actual":162,"unit":"K","beat_miss":"BEAT",
     "implication":"Strong labour market reduces Fed urgency to cut. USD positive, rate-sensitive equities under modest pressure."},
    {"date":"2026-03-12","market":"US","event":"CPI YoY","period":"Feb 2026",
     "previous":3.4,"expected":3.1,"actual":3.1,"unit":"%","beat_miss":"INLINE",
     "implication":"Disinflation trend intact. No urgency to change Fed guidance; curve largely unmoved."},
    {"date":"2026-03-14","market":"US","event":"PPI YoY","period":"Feb 2026",
     "previous":3.5,"expected":3.3,"actual":3.4,"unit":"%","beat_miss":"MISS",
     "implication":"Pipeline inflation slightly sticky. Watch for pass-through into core PCE next month."},
    {"date":"2026-03-17","market":"CA","event":"CPI YoY","period":"Feb 2026",
     "previous":2.1,"expected":2.0,"actual":1.9,"unit":"%","beat_miss":"BEAT",
     "implication":"Below-target print strengthens BoC easing case. CAD mildly negative near-term."},
    {"date":"2026-03-18","market":"US","event":"Retail Sales MoM","period":"Feb 2026",
     "previous":-0.9,"expected":0.5,"actual":0.2,"unit":"%","beat_miss":"MISS",
     "implication":"Softer consumer spending. Growth concerns offset hawkish NFP; mixed signal for Fed trajectory."},
    {"date":"2026-03-19","market":"US","event":"FOMC Rate Decision","period":"Mar 2026",
     "previous":4.50,"expected":4.25,"actual":4.25,"unit":"%","beat_miss":"INLINE",
     "implication":"Cut delivered as expected. Dot plot signalled 2 more cuts in 2026 — modestly dovish tone."},
    {"date":"2026-03-20","market":"US","event":"Philadelphia Fed PMI","period":"Mar 2026",
     "previous":18.1,"expected":15.0,"actual":12.5,"unit":"index","beat_miss":"MISS",
     "implication":"Regional manufacturing weakness. Adds to soft-landing debate; modest headwind for industrials."},
    {"date":"2026-03-27","market":"MX","event":"Banxico Rate Decision","period":"Mar 2026",
     "previous":9.50,"expected":9.00,"actual":None,"unit":"%","beat_miss":None,
     "implication":"50bps cut expected. Surprise hold would be MXN positive, equity negative short-term."},
    {"date":"2026-03-28","market":"US","event":"PCE YoY","period":"Feb 2026",
     "previous":2.6,"expected":2.5,"actual":None,"unit":"%","beat_miss":None,
     "implication":"Fed's preferred inflation gauge. At or below 2.5% bolsters rate-cut expectations for H2 2026."},
    {"date":"2026-03-28","market":"BR","event":"IPCA Inflation","period":"Mar 2026",
     "previous":4.8,"expected":5.2,"actual":None,"unit":"%","beat_miss":None,
     "implication":"Expected acceleration confirms BCB tightening bias. Watch BRL and domestic equity reaction."},
    {"date":"2026-04-01","market":"US","event":"ISM Manufacturing PMI","period":"Mar 2026",
     "previous":50.3,"expected":50.0,"actual":None,"unit":"index","beat_miss":None,
     "implication":"Below 50 would signal contraction; rotation into defensives and away from cyclicals likely."},
    {"date":"2026-04-01","market":"CA","event":"BoC Rate Decision","period":"Apr 2026",
     "previous":3.00,"expected":2.75,"actual":None,"unit":"%","beat_miss":None,
     "implication":"25bps cut expected. CAD vulnerability if larger; financials and REITs to benefit."},
    {"date":"2026-04-03","market":"US","event":"Non-Farm Payrolls","period":"Mar 2026",
     "previous":162,"expected":148,"actual":None,"unit":"K","beat_miss":None,
     "implication":"Key risk event. Below 100K would materially shift Fed cut expectations and broad equity sentiment."},
    {"date":"2026-04-01","market":"CL","event":"BCCh Rate Decision","period":"Apr 2026",
     "previous":5.25,"expected":5.00,"actual":None,"unit":"%","beat_miss":None,
     "implication":"Expected hold. CLP stability and copper price trajectory remain key catalysts to watch."},
]


# ─── New routes ───────────────────────────────────────────────────────────────

@app.route("/api/summary")
def summary():
    market = request.args.get("market", "US")
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=12)
    s = start_dt.strftime("%Y%m%d")
    e = end_dt.strftime("%Y%m%d")

    # Difficulty (VIX + HY spread, 2 heaviest components)
    df_d = bdh(["VIX Index", "LF98OAS Index"], ["PX_LAST"], s, e)
    vix_s = df_d[df_d["security"]=="VIX Index"]["PX_LAST"]
    hy_s  = df_d[df_d["security"]=="LF98OAS Index"]["PX_LAST"]
    vix_v = float(vix_s.iloc[-1]) if not vix_s.empty else 18
    hy_v  = float(hy_s.iloc[-1])  if not hy_s.empty  else 350
    def _norm(v, lo, hi): return max(0, min(100, (v-lo)/(hi-lo+1e-9)*100))
    diff_score = round(0.62*_norm(vix_v,12,45) + 0.38*_norm(hy_v,200,900), 1)
    def _classify(sc):
        return "EXTREME" if sc>=75 else "HIGH" if sc>=60 else "MODERATE" if sc>=40 else "LOW" if sc>=25 else "CALM"

    # Yield curve shape
    tenors = YIELD_CURVES.get(market, YIELD_CURVES["US"])
    ks = list(tenors.keys())
    two_tk = tenors.get("2Y",  tenors[ks[len(ks)//2]])
    ten_tk = tenors.get("10Y", tenors[ks[-1]])
    df_y = bdh([two_tk, ten_tk], ["PX_LAST"], s, e)
    y2  = float(df_y[df_y["security"]==two_tk]["PX_LAST"].iloc[-1]) if two_tk in df_y["security"].values else 4.5
    y10 = float(df_y[df_y["security"]==ten_tk]["PX_LAST"].iloc[-1]) if ten_tk in df_y["security"].values else 4.3
    bps = round((y10 - y2) * 100)
    shape = "INVERTED" if bps < -50 else "FLAT" if bps < 25 else "NORMAL" if bps < 75 else "STEEP"

    # Top / bottom sector
    secs = SECTORS.get(market, SECTORS["US"])
    df_s = bdh(list(secs.values()), ["PX_LAST"], s, e)
    df_s["date"] = pd.to_datetime(df_s["date"])
    best_name, worst_name, best_ret, worst_ret = "", "", -999, 999
    for name, sec in secs.items():
        sub = df_s[df_s["security"]==sec].sort_values("date")
        if len(sub) < 2: continue
        p = sub["PX_LAST"].values
        ret = round((p[-1]-p[0])/p[0]*100, 2)
        if ret > best_ret:  best_ret,  best_name  = ret, name
        if ret < worst_ret: worst_ret, worst_name = ret, name

    # Dominant factor spread
    all_f = list({sec for _,a,b,_,_ in FACTOR_PAIRS for sec in [a,b]})
    df_f = bdh(all_f, ["PX_LAST"], s, e)
    df_f["date"] = pd.to_datetime(df_f["date"])
    dom_name, dom_spread, dom_regime = "", 0.0, ""
    for name, sec_a, sec_b, pos_lbl, neg_lbl in FACTOR_PAIRS:
        sa = df_f[df_f["security"]==sec_a].sort_values("date")
        sb = df_f[df_f["security"]==sec_b].sort_values("date")
        if len(sa)<2 or len(sb)<2: continue
        n = min(len(sa), len(sb))
        pa = sa["PX_LAST"].values[-n:]; pb = sb["PX_LAST"].values[-n:]
        spread = float(pa[-1]/pa[0]*100 - pb[-1]/pb[0]*100)
        if abs(spread) > abs(dom_spread):
            dom_spread = spread; dom_name = name
            dom_regime = pos_lbl if spread >= 0 else neg_lbl

    return jsonify({
        "market": market,
        "difficulty_score": diff_score,
        "regime": _classify(diff_score),
        "yield_curve_shape": shape,
        "yield_curve_bps": bps,
        "top_sector": best_name, "top_sector_return": best_ret,
        "bottom_sector": worst_name, "bottom_sector_return": worst_ret,
        "dominant_factor": dom_name,
        "dominant_factor_spread": round(float(dom_spread), 2),
        "dominant_factor_regime": dom_regime,
    })


@app.route("/api/watchlist-prices")
def watchlist_prices():
    raw = request.args.get("tickers", "")
    if not raw:
        return jsonify({"prices": {}})
    tickers = [t.strip() for t in raw.split(",") if t.strip()]
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=7)
    df = bdh(tickers, ["PX_LAST"], start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))
    prices = {}
    for t in tickers:
        sub = df[df["security"]==t]["PX_LAST"]
        if not sub.empty:
            prices[t] = round(float(sub.iloc[-1]), 4)
    return jsonify({"prices": prices})


@app.route("/api/macro/inflation")
def macro_inflation():
    market = request.args.get("market", "US")
    return jsonify({"market": market, "readings": INFLATION_DATA.get(market, INFLATION_DATA["US"])})


@app.route("/api/macro/central-banks")
def macro_central_banks():
    market = request.args.get("market", "US")
    data = CENTRAL_BANK_DATA.get(market, CENTRAL_BANK_DATA["US"])
    return jsonify({"market": market, **data})


@app.route("/api/macro/calendar")
def macro_calendar():
    market = request.args.get("market", None)
    events = MACRO_CALENDAR if not market else [e for e in MACRO_CALENDAR if e["market"] == market]
    today  = datetime.today().strftime("%Y-%m-%d")
    out = []
    for ev in events:
        out.append({**ev, "status": "PAST" if ev["date"] <= today else "UPCOMING"})
    out.sort(key=lambda x: x["date"])
    return jsonify({"events": out})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
