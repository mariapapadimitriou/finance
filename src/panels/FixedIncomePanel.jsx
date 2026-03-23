import { useEffect, useState } from 'react';
import ChartCanvas from '../components/ChartCanvas.jsx';
import InfoTooltip from '../components/InfoTooltip.jsx';
import {
  loadFIData, loadCreditSpreadsData, loadRealYieldsData,
  sortTenors, tooltipStyle, lineOpts, cssVar,
} from '../api.js';

const SPREAD_OPTIONS = [
  { key: '2s10s', label: '2s10s', a: '2Y',  b: '10Y', color: '#ffd24d' },
  { key: '3m10y', label: '3M10Y', a: '3M',  b: '10Y', color: '#00d4ff' },
  { key: '5s30s', label: '5s30s', a: '5Y',  b: '30Y', color: '#3dffa0' },
  { key: '2s5s',  label: '2s5s',  a: '2Y',  b: '5Y',  color: '#b47fff' },
  { key: '10s30s',label: '10s30s',a: '10Y', b: '30Y', color: '#ff8c42' },
];

const SECTION_TIPS = {
  yieldCurve:    'Government benchmark yield curve at period start (dashed gray) vs current (solid cyan). Steepening = long end rising faster than short end; flattening = the reverse. Inversion = short rates above long rates.',
  keySpreads:    '2s10s = 2yr minus 10yr yield. Negative (inverted) historically signals recession within 12–18 months. 3M10Y = bill-to-bond spread — another inversion signal closely watched by the Fed.',
  tenorSnap:     'Point-in-time yield levels across all tenors at period start and end. Change column shows basis point move over the lookback period.',
  spr2s10s:      'The 2-year vs 10-year government bond spread over time in basis points. Below zero = curve inversion. Trend direction indicates whether steepening or flattening pressure is building.',
  creditSpreads: 'Option-adjusted spread (OAS) over Treasuries. IG OAS measures investment-grade credit risk; HY OAS measures high-yield. Widening spreads signal deteriorating credit conditions or rising recession risk.',
  realYields:    'Real yield = nominal Treasury yield minus inflation (TIPS breakeven). Positive and rising real yields tighten financial conditions — headwind for equities, gold, and long-duration assets.',
  aiAnalysis:    'Procedural narrative using actual spread data for this market and period. Covers curve dynamics, macro drivers, credit implications, and the key signal to watch.',
};

export default function FixedIncomePanel({ market, lookback, theme }) {
  const [data, setData]               = useState(null);
  const [creditSpreads, setCreditSpreads] = useState(null);
  const [realYields, setRealYields]   = useState(null);
  const [aiText, setAiText]           = useState('');
  const [aiLoading, setAiLoading]     = useState(true);
  const [error, setError]             = useState(null);
  const [selectedSpread, setSelectedSpread] = useState('2s10s');

  useEffect(() => {
    setData(null); setCreditSpreads(null); setRealYields(null);
    setAiText(''); setAiLoading(true); setError(null);
    setSelectedSpread('2s10s');

    let cancelled = false;

    Promise.all([
      loadFIData(market, lookback),
      loadCreditSpreadsData(market),
      loadRealYieldsData(market),
    ]).then(([d, csData, ryData]) => {
      if (cancelled) return;
      setData(d);
      setCreditSpreads(csData);
      setRealYields(ryData);
      runAI(d, market, lookback).then(txt => {
        if (cancelled) return;
        setAiText(txt);
        setAiLoading(false);
      });
    }).catch(err => {
      if (!cancelled) setError(err.message);
    });

    return () => { cancelled = true; };
  }, [market, lookback]);

  if (error) return <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>Failed to load data: {error}<br /><span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span></div>;

  // ── Yield curve chart ────────────────────────────────────────────────────
  const buildYC = ctx => {
    if (!data) return null;
    const t = sortTenors(Object.keys(data.curve_start));
    return {
      type: 'line',
      data: {
        labels: t,
        datasets: [
          {
            label: `Start (${data.lookback}D ago)`,
            data: t.map(x => data.curve_start[x]),
            borderColor: '#2d4560',
            backgroundColor: 'rgba(45,69,96,.1)',
            borderWidth: 1.5,
            borderDash: [4, 3],
            pointRadius: 3,
            fill: true,
            tension: 0.4,
          },
          {
            label: 'Current',
            data: t.map(x => data.curve_end[x]),
            borderColor: '#00d4ff',
            backgroundColor: 'rgba(0,212,255,.07)',
            borderWidth: 2,
            pointRadius: 4,
            pointBackgroundColor: '#00d4ff',
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 } } },
          ...tooltipStyle(c => `${c.dataset.label}: ${c.parsed.y.toFixed(2)}%`),
        },
        scales: {
          x: { ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 } }, grid: { color: cssVar("--chart-grid") } },
          y: { ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 }, callback: v => v.toFixed(2) + '%' }, grid: { color: cssVar("--chart-grid") } },
        },
      },
    };
  };

  // ── Spread time series (generic, driven by selectedSpread) ──────────────
  const buildSpreadChart = (opt) => _ctx => {
    if (!data || !opt) return null;
    const tsA = data.time_series[opt.a];
    const tsB = data.time_series[opt.b];
    if (!tsA || !tsB) return null;
    const n = Math.min(tsA.dates.length, tsB.yields.length);
    const spreads = tsA.yields.slice(-n).map((y, i) => Math.round((tsB.yields[i] - y) * 100));
    const dates   = tsA.dates.slice(-n);
    // parse hex color for gradient
    const hr = parseInt(opt.color.slice(1,3),16);
    const hg = parseInt(opt.color.slice(3,5),16);
    const hb = parseInt(opt.color.slice(5,7),16);
    return {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          {
            label: opt.label,
            data: spreads,
            borderColor: opt.color,
            backgroundColor: ctx2 => {
              const g = ctx2.chart.ctx.createLinearGradient(0, 0, 0, 200);
              g.addColorStop(0, `rgba(${hr},${hg},${hb},.25)`);
              g.addColorStop(1, `rgba(${hr},${hg},${hb},0)`);
              return g;
            },
            borderWidth: 2,
            fill: true,
            pointRadius: 0,
            tension: 0.35,
          },
          {
            label: 'Zero',
            data: new Array(n).fill(0),
            borderColor: 'rgba(255,61,94,.35)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: lineOpts({
        yCallback: v => v + ' bps',
        tooltipCallback: c => c.datasetIndex === 0 ? ` ${opt.label}: ${c.parsed.y} bps` : null,
      }),
    };
  };

  // ── Spreads grid ─────────────────────────────────────────────────────────
  const renderSpreads = () => {
    if (!data) return null;
    const sp = data.spreads;
    const bps = v => Math.round(v * 100);
    const items = [
      { lbl: '2s10s (END)',    val: bps(sp['2s10s_end']),                    delta: bps(sp['2s10s_end'] - sp['2s10s_start']) },
      { lbl: '3M10Y (END)',    val: bps(sp['3m10y_end']),                    delta: bps(sp['3m10y_end'] - sp['3m10y_start']) },
      { lbl: '2s10s Δ PERIOD',val: bps(sp['2s10s_end'] - sp['2s10s_start']),delta: null, raw: null },
      { lbl: 'SHAPE',          val: null, raw: sp.inverted ? 'INVERTED' : sp.steepening ? 'STEEPENING' : 'FLATTENING' },
    ];
    return (
      <div className="spr-grid">
        {items.map((it, idx) => {
          const inv = it.raw === 'INVERTED', steep = it.raw === 'STEEPENING';
          const vc = it.raw
            ? (inv ? 'var(--red)' : steep ? 'var(--green)' : 'var(--acc)')
            : (it.val > 0 ? 'var(--green)' : it.val < 0 ? 'var(--red)' : 'var(--text)');
          const vd = it.raw ? it.raw : `${it.val > 0 ? '+' : ''}${it.val} bps`;
          return (
            <div className="spr-cell" key={idx}>
              <div className="spr-lbl">{it.lbl}</div>
              <div className="spr-val" style={{ color: vc }}>{vd}</div>
              {it.delta !== null ? (
                <div className={`spr-delta ${it.delta > 0 ? 'pos' : it.delta < 0 ? 'neg' : ''}`}>
                  {it.delta > 0 ? '▲' : it.delta < 0 ? '▼' : '–'} {Math.abs(it.delta)} bps change
                </div>
              ) : (
                <div className="spr-delta" style={{ color: 'var(--dim)' }}>
                  {it.lbl.includes('Δ') ? 'vs period start' : 'shape'}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // ── Tenor table ──────────────────────────────────────────────────────────
  const renderTenorTable = () => {
    if (!data) return null;
    const sorted = sortTenors(Object.keys(data.curve_start));
    return (
      <table className="tenor-tbl">
        <thead>
          <tr>
            <th>TENOR</th><th>START</th><th>END</th><th>CHG</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(t => {
            const s = data.curve_start[t], e = data.curve_end[t];
            const chg = ((e - s) * 100).toFixed(1);
            return (
              <tr key={t}>
                <td style={{ color: 'var(--dim)' }}>{t}</td>
                <td>{s.toFixed(2)}%</td>
                <td>{e.toFixed(2)}%</td>
                <td className={parseFloat(chg) > 0 ? 'tup' : 'tdn'}>{chg > 0 ? '+' : ''}{chg}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  };

  // ── Credit spreads render ─────────────────────────────────────────────────
  const renderCreditSpreads = () => {
    if (!creditSpreads?.spreads?.length) return <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>No data for this market.</div>;
    const realYield10y = creditSpreads.real_yield_10y;
    return (
      <>
        {realYield10y != null && (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '.6rem', marginBottom: '1rem',
                        paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: '.8rem', color: 'var(--dim)', letterSpacing: '.06em' }}>REAL YIELD (10Y − CPI)</div>
            <div style={{ fontFamily: 'var(--fhead)', fontSize: '2rem',
                          color: realYield10y > 2 ? 'var(--red)' : realYield10y > 0 ? 'var(--gold)' : 'var(--green)' }}>
              {realYield10y > 0 ? '+' : ''}{realYield10y}%
            </div>
            <div style={{ fontSize: '.75rem', color: 'var(--dim)' }}>
              {realYield10y > 1.5 ? 'Restrictive — tightening financial conditions' :
               realYield10y > 0   ? 'Mildly positive — neutral-to-tight conditions' :
                                    'Negative real rate — financially accommodative'}
            </div>
          </div>
        )}
        <div className="oas-grid">
          {creditSpreads.spreads.map((sp, i) => {
            const wide = sp.trend === 'UP';
            const color = sp.current > 400 ? 'var(--red)' : sp.current > 200 ? 'var(--gold)' : 'var(--green)';
            return (
              <div className="oas-cell" key={i}>
                <div className="oas-lbl">{sp.label}</div>
                <div className="oas-val" style={{ color }}>
                  {sp.current}<span className="oas-unit">{sp.unit}</span>
                </div>
                <div className={`oas-delta ${wide ? 'pos' : 'neg'}`}>
                  {wide ? '▲' : '▼'} prev {sp.prev}{sp.unit}
                </div>
              </div>
            );
          })}
        </div>
      </>
    );
  };

  // ── Real yields (TIPS) render ─────────────────────────────────────────────
  const renderRealYields = () => {
    if (!realYields?.real_yields?.length) return null;
    return (
      <div className="ry-grid">
        {realYields.real_yields.map((ry, i) => (
          <div className="ry-row" key={i}>
            <div className="ry-lbl">{ry.label}</div>
            <div className="ry-val" style={{ color: ry.current > 2 ? 'var(--red)' : ry.current > 0 ? 'var(--gold)' : 'var(--green)' }}>
              {ry.current}{ry.unit}
            </div>
            <div className="ry-prev">prev {ry.prev}{ry.unit}</div>
            <div className="ry-dir" style={{ color: ry.trend === 'UP' ? 'var(--red)' : 'var(--green)' }}>
              {ry.trend === 'UP' ? '▲ Rising real rate' : '▼ Falling real rate'}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <>
      {/* ── Yield curve + Spread chart (left) | Key spreads + Tenor table (right) ── */}
      <div className="g-fi">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.8rem' }}>
          <div className="card">
            <div className="ctitle">YIELD CURVE — START VS END <InfoTooltip text={SECTION_TIPS.yieldCurve} /></div>
            {data && (
              <ChartCanvas buildConfig={buildYC} deps={[data, market, lookback, theme]} height={300} />
            )}
          </div>

          {/* ── Spread time series ── */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem', marginBottom: '.7rem', flexWrap: 'wrap' }}>
              <span className="ctitle" style={{ marginBottom: 0 }}>
                SPREAD — TIME SERIES (BPS) <InfoTooltip text={SECTION_TIPS.spr2s10s} />
              </span>
              <div style={{ display: 'flex', gap: '.35rem', flexWrap: 'wrap' }}>
                {SPREAD_OPTIONS.filter(o => data?.time_series?.[o.a] && data?.time_series?.[o.b]).map(o => {
                  const active = selectedSpread === o.key;
                  return (
                    <button key={o.key} onClick={() => setSelectedSpread(o.key)} style={{
                      fontFamily: 'var(--fmono)', fontSize: '.68rem', letterSpacing: '.06em',
                      padding: '.18rem .55rem', borderRadius: 3, cursor: 'pointer',
                      border: `1px solid ${active ? o.color : 'var(--border2)'}`,
                      background: active ? `${o.color}22` : 'transparent',
                      color: active ? o.color : 'var(--dim)',
                      transition: 'all .12s',
                    }}>{o.label}</button>
                  );
                })}
              </div>
            </div>
            {data && (() => {
              const opt = SPREAD_OPTIONS.find(o => o.key === selectedSpread)
                       || SPREAD_OPTIONS.find(o => data.time_series?.[o.a] && data.time_series?.[o.b]);
              return opt
                ? <ChartCanvas buildConfig={buildSpreadChart(opt)} deps={[data, selectedSpread, market, lookback, theme]} height={190} />
                : <div style={{ color: 'var(--dim)', fontSize: '.78rem', padding: '.5rem' }}>No data for this spread.</div>;
            })()}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '.8rem' }}>
          <div className="card">
            <div className="ctitle">KEY SPREADS (BPS) <InfoTooltip text={SECTION_TIPS.keySpreads} /></div>
            {renderSpreads()}
          </div>
          <div className="card">
            <div className="ctitle">TENOR SNAPSHOT <InfoTooltip text={SECTION_TIPS.tenorSnap} /></div>
            {renderTenorTable()}
          </div>
        </div>
      </div>

      {/* ── Credit Spreads ── */}
      <div className="slabel"><em>//</em> CREDIT SPREADS <InfoTooltip text={SECTION_TIPS.creditSpreads} /></div>
      <div className="card" style={{ marginBottom: '1rem' }}>
        {data ? renderCreditSpreads() : <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>Loading…</div>}
      </div>

      {/* ── Real Yields (US only) ── */}
      {realYields?.real_yields?.length > 0 && (
        <>
          <div className="slabel"><em>//</em> REAL YIELDS — TIPS <InfoTooltip text={SECTION_TIPS.realYields} /></div>
          <div className="card" style={{ marginBottom: '1rem' }}>
            {renderRealYields()}
          </div>
        </>
      )}

      {/* ── AI Curve Analysis ── */}
      <div className="slabel"><em>//</em> CURVE ANALYSIS <InfoTooltip text={SECTION_TIPS.aiAnalysis} /></div>
      <div className="ai-box">
        <div className="ai-hdr">
          <div className="aidot" />
          YIELD CURVE ANALYSIS
        </div>
        <div className={`ai-txt${aiLoading ? ' loading' : ''}`} style={{ whiteSpace: 'pre-wrap' }}>
          {aiText}
        </div>
      </div>
    </>
  );
}

// ── Curve analysis (procedural) ───────────────────────────────────────────────
function runAI(d, market, lookback) {
  const sp = d.spreads;
  const bps = v => Math.round(v * 100);
  const dir = sp.steepening ? 'steepened' : 'flattened';
  const chg = Math.abs(bps(sp['2s10s_end'] - sp['2s10s_start']));

  return Promise.resolve(`The ${market} government yield curve has ${dir} by ${chg} basis points over the past ${lookback} trading days, with the 2s10s spread moving from ${bps(sp['2s10s_start'])} to ${bps(sp['2s10s_end'])} bps.${sp.inverted ? ' The curve remains inverted — a condition historically associated with recession risk over a 12–18 month horizon.' : ''}

${sp.steepening
  ? 'The steepening dynamic reflects term premium expansion, as investors demand greater compensation for holding longer-duration paper amid uncertainty around the inflation trajectory and fiscal supply. The front end remains anchored by central bank guidance, while the long end reprices the neutral rate higher.'
  : 'The flattening move suggests either a defensive rotation into long-duration bonds — consistent with fading growth expectations — or continued front-end pressure from policy rates staying elevated longer. Bull flattening typically signals markets pricing in a growth slowdown ahead.'}

For credit markets, ${sp['2s10s_end'] < 0
  ? 'the inverted curve historically foreshadows tighter credit conditions and rising defaults over the medium term, particularly affecting floating-rate borrowers and leveraged credits'
  : 'the curve shape implies cautious risk appetite; monitor IG and HY spread widening as an early stress signal'}. Rate-sensitive sectors — utilities, REITs, long-duration growth equities — face headwinds if the long end continues to rise.

Watch for the next central bank meeting and CPI print as the key catalysts that could force a significant repricing across the entire curve.`);
}
