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

SECTORS = {
    "US": {
        "Technology":    "XLK US Equity",
        "Financials":    "XLF US Equity",
        "Health Care":   "XLV US Equity",
        "Energy":        "XLE US Equity",
        "Industrials":   "XLI US Equity",
        "Cons. Discr.":  "XLY US Equity",
        "Cons. Staples": "XLP US Equity",
        "Utilities":     "XLU US Equity",
        "Real Estate":   "XLRE US Equity",
        "Materials":     "XLB US Equity",
        "Comm. Svcs":    "XLC US Equity",
    },
    "CA": {
        "Technology":    "XIT CN Equity",
        "Financials":    "XFN CN Equity",
        "Energy":        "XEG CN Equity",
        "Materials":     "XMA CN Equity",
        "Real Estate":   "XRE CN Equity",
        "Broad Market":  "XIU CN Equity",
        "Utilities":     "XUT CN Equity",
        "Health Care":   "XHC CN Equity",
    },
    "MX": {
        "Broad Market":  "NAFTRAC MM Equity",
        "Financials":    "GFNORTEO MM Equity",
        "Telecoms":      "AMXL MM Equity",
        "Consumer":      "BIMBOA MM Equity",
        "Materials":     "CEMEXCPO MM Equity",
        "Airports":      "ASURB MM Equity",
        "Retail":        "WALMEX MM Equity",
    },
    "BR": {
        "Broad Market":  "BOVA11 BZ Equity",
        "Financials":    "ITUB4 BZ Equity",
        "Energy":        "PETR4 BZ Equity",
        "Mining":        "VALE3 BZ Equity",
        "Consumer":      "MGLU3 BZ Equity",
        "Utilities":     "ELET3 BZ Equity",
        "Retail":        "LREN3 BZ Equity",
    },
    "CL": {
        "Broad Market":  "IPSA CI Index",
        "Copper/Mining": "SQM/B CI Equity",
        "Retail":        "FALABELLA CI Equity",
        "Utilities":     "ENELCHIL CI Equity",
        "Banks":         "BCI CI Equity",
        "Lithium":       "SQM CI Equity",
    },
}

YIELD_CURVES = {
    "US": {"3M":"USGG3M Index","6M":"USGG6M Index","1Y":"USGG1Y Index",
           "2Y":"USGG2Y Index","3Y":"USGG3Y Index","5Y":"USGG5Y Index",
           "7Y":"USGG7Y Index","10Y":"USGG10Y Index","20Y":"USGG20Y Index","30Y":"USGG30Y Index"},
    "CA": {"3M":"GCAN3M Index","6M":"GCAN6M Index","1Y":"GCAN1Y Index",
           "2Y":"GCAN2Y Index","3Y":"GCAN3Y Index","5Y":"GCAN5Y Index",
           "7Y":"GCAN7Y Index","10Y":"GCAN10Y Index","20Y":"GCAN20Y Index","30Y":"GCAN30Y Index"},
    "MX": {"3M":"MXBM3M Index","6M":"MXBM6M Index","1Y":"MXBM1Y Index",
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
    "US":  [180,38,130,85,110,175,72,65,38,90,82],
    "CA":  [38,42,18,22,19,35,24,28],
    "MX":  [52,180,22,35,18,155,75],
    "BR":  [115,28,38,85,12,42,18],
    "CL":  [5200,45,1850,280,12500,48],
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
        is_yield   = "Index" in sec and not is_vol_idx and "SPX" not in sec
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


if __name__ == "__main__":
    app.run(debug=True, port=5050)
