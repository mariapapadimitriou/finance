import { useEffect, useState, useMemo } from 'react';
import ChartCanvas from '../components/ChartCanvas.jsx';
import InfoTooltip from '../components/InfoTooltip.jsx';
import {
  loadEquitiesData,
  loadFactorsData,
  fmt,
  hexToRgba,
  PALETTE,
  FACTOR_COLORS,
  lineOpts,
  tooltipStyle,
  cssVar,
} from '../api.js';

const SECTION_TIPS = {
  sectorReturns:   'Total return of each sector index over the selected lookback. Bars are scaled to the strongest performer. Sorted best to worst.',
  indexedPerf:     'All sector indices rebased to 100 at period start. Diverging lines reveal relative momentum and regime leadership between sectors.',
  volFlow:         'Dollar volume traded on advancing days (green) vs declining days (red). Flow ratio > 1 signals net buying pressure for that sector.',
  volBar:          'Mean daily notional turnover (price × volume) in billions. Colored green if flow ratio > 1 (net buy) or red (net sell). Proxy for liquidity depth.',
  factorOverview:  'Spread = rebased return of asset A minus asset B over the period. Positive = A outperforming. Regime label reflects which factor is in control.',
  factorTimeSeries:'Rolling spread over the lookback window. Trend direction and zero-line crossings indicate regime changes between the two assets.',
};

const FACTOR_TIPS = {
  'Large vs Small Cap':    'SPY vs IWM. Positive = large-caps leading — typical in late-cycle or risk-off environments. Negative = small-cap risk appetite returning.',
  'Value vs Growth':       'IVE vs IVW. Positive = value regime, often driven by rising rates or inflation. Negative = growth/momentum leadership, typical in easing cycles.',
  'Gold vs Gold Miners':   'GLD vs GDX. Persistent positive = gold pricing in stress but miners not confirming. Convergence often signals a tradeable mean-reversion setup.',
  'Oil/Gas vs Energy Stks':'USO vs XLE. Negative = energy equities pricing in better margins or supply discipline beyond what the spot commodity price implies.',
  'Momentum vs Broad':     'MTUM vs SPY. Elevated positive = trend-following strategies being rewarded. Breaks down quickly in choppy or reversing markets.',
  'Quality vs High Beta':  'QUAL vs SPHB. Positive = balance sheet quality rewarded over levered, high-beta names — a classic defensive rotation signal.',
  'Low Vol vs High Beta':  'USMV vs SPHB. Risk-off signal when positive. Diverges from Quality when stress is idiosyncratic rather than broad/systemic.',
  'EM vs DM':              'EEM vs EFA. Positive = risk appetite for emerging markets. Highly sensitive to USD strength, commodity cycles, and global growth expectations.',
  'Defensive vs Cyclical': 'XLU vs XLY. Positive = utilities outperforming consumer discretionary — a classic risk-off rotation ahead of slowdowns.',
  'Bonds vs Equities':     'TLT vs SPY. Positive = flight to safety into long-duration Treasuries. Persistent positive signals markets pricing in a growth slowdown.',
  'Dollar vs EM FX':       'UUP vs EEM. Positive = dollar strength compressing EM returns. Watch for EM carry unwind when this spread extends rapidly.',
  'Semis vs Broad Tech':   'SOXX vs XLK. Semis lead the tech cycle. Sustained outperformance = cyclical tech recovery underway; underperformance = caution ahead.',
  'Small Value vs Growth': 'IWN vs IWO. Value factor within the small-cap universe. Positive = deep value rotation — often an early-cycle or rate-peak indicator.',
  'Dividend vs Growth':    'DVY vs IWO. Positive = defensive income-seeking posture dominating. Negative = growth momentum and risk appetite in control.',
};

export default function EquitiesPanel({ market, lookback, theme }) {
  const [sectors, setSectors]           = useState(null);
  const [volSectors, setVolSectors]     = useState(null);
  const [factors, setFactors]           = useState(null);
  const [selectedFactor, setSelectedFactor] = useState(0);
  const [error, setError]                   = useState(null);

  useEffect(() => {
    setSectors(null);
    setVolSectors(null);
    setFactors(null);
    setSelectedFactor(0);
    setError(null);

    let cancelled = false;

    Promise.all([
      loadEquitiesData(market, lookback),
      loadFactorsData(market, lookback),
    ]).then(([eq, fac]) => {
      if (cancelled) return;
      setSectors(eq.sectors);
      setVolSectors(eq.volSectors);
      setFactors(fac);
    }).catch(err => {
      if (!cancelled) setError(err.message);
    });

    return () => { cancelled = true; };
  }, [market, lookback]);

  const spreadAnalysis = useMemo(() => {
    if (!factors) return '';
    const f = factors[selectedFactor];
    if (!f) return '';
    return computeSpreadAnalysis(f, market, lookback);
  }, [selectedFactor, factors, market, lookback]);

  const loading = !error && (!sectors || !volSectors || !factors);

  if (error) return <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>Failed to load data: {error}<br /><span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span></div>;

  // ── Sector returns bar list ──────────────────────────────────────────────
  const retLbl = `${lookback}D · ${market}`;
  const mx = sectors ? Math.max(...sectors.map(s => Math.abs(s.return_pct))) : 1;

  // ── Rebased line chart ───────────────────────────────────────────────────
  const buildRetLine = ctx => {
    if (!sectors) return null;
    return {
      type: 'line',
      data: {
        labels: sectors[0]?.dates || [],
        datasets: sectors.map((s, i) => ({
          label: s.sector,
          data: s.prices.map(p => (p / s.prices[0] - 1) * 100),
          borderColor: PALETTE[i % PALETTE.length],
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
        })),
      },
      options: lineOpts({
        yCallback: v => fmt(v) + '%',
        tooltipCallback: c => ` ${c.dataset.label}: ${fmt(c.parsed.y)}%`,
      }),
    };
  };

  // ── Volume bar chart ─────────────────────────────────────────────────────
  const buildVolBar = ctx => {
    if (!volSectors) return null;
    const sorted = [...volSectors].sort((a, b) => b.avg_vol_bn - a.avg_vol_bn);
    return {
      type: 'bar',
      data: {
        labels: sorted.map(s => s.sector),
        datasets: [{
          label: 'Avg Daily Vol (Bn)',
          data: sorted.map(s => s.avg_vol_bn),
          backgroundColor: sorted.map(s => s.flow_ratio > 1 ? 'rgba(61,255,160,.5)' : 'rgba(255,61,94,.45)'),
          borderColor: sorted.map(s => s.flow_ratio > 1 ? '#3dffa0' : '#ff3d5e'),
          borderWidth: 1,
          borderRadius: 2,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          ...tooltipStyle(c => `$${c.parsed.x.toFixed(2)}Bn`),
        },
        scales: {
          x: { ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 } }, grid: { color: cssVar("--chart-grid") } },
          y: { ticks: { color: cssVar("--chart-text"), font: { family: 'IBM Plex Mono', size: 16 } }, grid: { display: false } },
        },
      },
    };
  };

  // ── Vol flow list ────────────────────────────────────────────────────────
  const renderVolFlow = () => {
    if (!volSectors) return null;
    const mx_up = Math.max(...volSectors.map(s => s.up_volume));
    const mx_dn = Math.max(...volSectors.map(s => s.down_volume));
    return (
      <div>
        <div className="vrow" style={{ fontSize: '.58rem', color: 'var(--dim)', letterSpacing: '.07em' }}>
          <div>SECTOR</div><div>UP / DOWN FLOW</div><div>RATIO</div>
        </div>
        {volSectors.map((s, i) => {
          const upW = s.up_volume / mx_up * 100;
          const dnW = s.down_volume / mx_dn * 100;
          const rc = s.flow_ratio > 1.1 ? 'pos' : s.flow_ratio < 0.9 ? 'neg' : '';
          return (
            <div className="vrow" key={i}>
              <div className="vname">{s.sector}</div>
              <div className="vbars">
                <div style={{ display: 'flex', alignItems: 'center', gap: '.3rem' }}>
                  <div className="vbar u" style={{ width: `${upW * 0.8}px`, minWidth: 2 }} />
                  <span style={{ fontSize: '.58rem', color: 'var(--green)' }}>{s.up_volume.toFixed(1)}Bn</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '.3rem' }}>
                  <div className="vbar d" style={{ width: `${dnW * 0.8}px`, minWidth: 2 }} />
                  <span style={{ fontSize: '.58rem', color: 'var(--red)' }}>{s.down_volume.toFixed(1)}Bn</span>
                </div>
              </div>
              <div className={`vratio ${rc}`}>{s.flow_ratio > 99 ? '∞' : s.flow_ratio.toFixed(2)}</div>
            </div>
          );
        })}
      </div>
    );
  };

  // ── Factor chart configs (one per factor) ────────────────────────────────
  const buildFactorChart = (f, i) => ctx => {
    const color = FACTOR_COLORS[i % FACTOR_COLORS.length];
    return {
      type: 'line',
      data: {
        labels: f.dates || [],
        datasets: [
          {
            label: f.name,
            data: f.spread || [],
            borderColor: color,
            backgroundColor: hexToRgba(color, 0.08),
            borderWidth: 1.5,
            pointRadius: 0,
            fill: true,
            tension: 0.35,
          },
          {
            label: 'Zero',
            data: new Array((f.spread || []).length).fill(0),
            borderColor: 'rgba(255,255,255,.12)',
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: lineOpts({
        legend: false,
        yCallback: v => fmt(v) + '%',
        tooltipCallback: c => ` ${f.name}: ${fmt(c.parsed.y)}%`,
      }),
    };
  };

  return (
    <>
      {/* ── Sector Returns + Rebased Performance ── */}
      <div className="g2">
        <div className="card">
          <div className="ctitle">
            <span style={{ display: 'flex', alignItems: 'center' }}>
              SECTOR RETURNS <InfoTooltip text={SECTION_TIPS.sectorReturns} />
            </span>
            <span>{retLbl}</span>
          </div>
          {loading ? (
            <div style={{ color: 'var(--dim)', fontSize: '.7rem' }}>Loading…</div>
          ) : (
            <div className="sect-list">
              {sectors.map((s, i) => {
                const w = Math.abs(s.return_pct) / mx * 100;
                const c = s.return_pct >= 0 ? 'p' : 'n';
                const cv = s.return_pct >= 0 ? 'pos' : 'neg';
                return (
                  <div className="srow" key={i}>
                    <div className="sname">{s.sector}</div>
                    <div className="btrack">
                      <div className={`bfill ${c}`} style={{ width: `${w}%` }} />
                    </div>
                    <div className={`sval ${cv}`}>{fmt(s.return_pct)}%</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="ctitle">INDEXED PERFORMANCE (REBASED TO 100) <InfoTooltip text={SECTION_TIPS.indexedPerf} /></div>
          {!loading && (
            <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
              <ChartCanvas
                buildConfig={buildRetLine}
                deps={[sectors, market, lookback, theme]}
                height="100%"
              />
            </div>
          )}
        </div>
      </div>

      {/* ── Volume & Flow ── */}
      <div className="slabel"><em>//</em> VOLUME &amp; FLOW</div>
      <div className="g2">
        <div className="card">
          <div className="ctitle">UP / DOWN VOLUME FLOW <InfoTooltip text={SECTION_TIPS.volFlow} /></div>
          {loading ? (
            <div style={{ color: 'var(--dim)', fontSize: '.7rem' }}>Loading…</div>
          ) : renderVolFlow()}
        </div>
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="ctitle">AVG DAILY DOLLAR VOLUME <InfoTooltip text={SECTION_TIPS.volBar} /></div>
          {!loading && (
            <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
              <ChartCanvas
                buildConfig={buildVolBar}
                deps={[volSectors, market, lookback, theme]}
                height="100%"
              />
            </div>
          )}
        </div>
      </div>

      {/* ── Factor Spreads: cards left, chart right ── */}
      <div className="slabel">
        <em>//</em> FACTOR SPREAD OVERVIEW <InfoTooltip text={SECTION_TIPS.factorOverview} />
      </div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.7rem' }}>Loading…</div>
      ) : (
        <div className="g-factors">
          {/* Left: all factor cards in 2-column grid */}
          <div className="factors-cards">
            {factors.map((f, i) => {
              const pos = f.current >= 0;
              const color = FACTOR_COLORS[i % FACTOR_COLORS.length];
              const rc = pos ? 'pos-r' : 'neg-r';
              const isSelected = selectedFactor === i;
              return (
                <div
                  className="factor-card"
                  key={i}
                  onClick={() => setSelectedFactor(i)}
                  style={{
                    cursor: 'pointer',
                    outline: isSelected ? `1px solid ${color}` : '1px solid transparent',
                    boxShadow: isSelected ? `0 0 8px ${color}33` : 'none',
                    transition: 'outline .12s, box-shadow .12s',
                  }}
                >
                  <div className="fc-name" style={{ display: 'flex', alignItems: 'center' }}>
                    {f.name} <InfoTooltip text={FACTOR_TIPS[f.name] || ''} direction="above" />
                  </div>
                  <div className="fc-val" style={{ color }}>{fmt(f.current)}%</div>
                  <div className={`fc-regime ${rc}`}>{f.regime}</div>
                  <div style={{ fontSize: '.6rem', color: 'var(--dim)', marginTop: '.1rem' }}>
                    Δ period:{' '}
                    <span style={{ color: f.period_change >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      {fmt(f.period_change)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right: single chart for selected factor */}
          {(() => {
            const f = factors[selectedFactor];
            const color = FACTOR_COLORS[selectedFactor % FACTOR_COLORS.length];
            return (
              <div className="card" style={{ padding: '.8rem .9rem', alignSelf: 'stretch', display: 'flex', flexDirection: 'column' }}>
                <div className="ctitle">
                  <span style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
                    FACTOR SPREAD TIME SERIES <InfoTooltip text={SECTION_TIPS.factorTimeSeries} />
                  </span>
                  <span style={{ color, fontFamily: 'var(--fmono)', fontSize: '.6rem' }}>{f.name}</span>
                </div>
                <div style={{ fontSize: '.6rem', color: 'var(--dim)', marginBottom: '.6rem' }}>
                  Click a card to switch factor
                </div>
                <ChartCanvas
                  buildConfig={buildFactorChart(f, selectedFactor)}
                  deps={[selectedFactor, f.spread, f.dates, market, lookback, theme]}
                  height={300}
                />
                <div className="ai-box" style={{ marginTop: '.9rem' }}>
                  <div className="ai-hdr">
                    SPREAD ANALYSIS — {f.name.toUpperCase()}
                  </div>
                  <div className="ai-txt" style={{ whiteSpace: 'pre-wrap' }}>
                    {spreadAnalysis}
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </>
  );
}

// ── Spread analysis ───────────────────────────────────────────────────────────
function computeSpreadAnalysis(f, market, lookback) {
  const spread = f.spread || [];
  const n = spread.length;
  const recent = spread.slice(-Math.min(10, n));
  const avg = spread.length ? (spread.reduce((a, b) => a + b, 0) / spread.length).toFixed(2) : 0;
  const min = spread.length ? Math.min(...spread).toFixed(2) : 0;
  const max = spread.length ? Math.max(...spread).toFixed(2) : 0;
  const trend = recent.length >= 2
    ? (recent[recent.length - 1] - recent[0] > 0 ? 'rising' : 'falling')
    : 'flat';
  const zeroCrossings = spread.slice(1).filter((v, i) => (spread[i] >= 0) !== (v >= 0)).length;

  const dir = f.period_change >= 0 ? 'widened' : 'narrowed';
  const absChg = Math.abs(f.period_change?.toFixed(2));
  const regimeTxt = f.current >= 0
    ? `The positive spread of ${f.current?.toFixed(2)}% confirms the first-named asset is outperforming over this period.`
    : `The negative spread of ${f.current?.toFixed(2)}% indicates the second asset has taken the lead, consistent with a regime shift.`;

  return `The ${f.name} spread has ${dir} by ${absChg}% over the past ${lookback} trading days, currently reading ${f.current?.toFixed(2)}%. ${regimeTxt}

The spread has traded between ${min}% and ${max}% over the period, with a mean of ${avg}%. ${zeroCrossings > 2 ? `The ${zeroCrossings} zero-line crossings suggest an unstable, choppy regime with no clear directional conviction.` : zeroCrossings === 0 ? 'No zero-line crossings indicate a persistent, one-directional regime throughout the lookback window.' : 'A single zero-line crossing marks a potential regime transition worth monitoring.'}

The recent ${trend} trend is the key signal to track. A sustained move back through zero would confirm a full regime reversal; watch for confirmation from complementary factors before adjusting positioning.`;
}
