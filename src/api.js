// ─── Config ──────────────────────────────────────────────────────────────────
export const API = 'http://localhost:5050';

export const PALETTE = [
  '#00d4ff','#ff4d6d','#3dffa0','#ffd24d','#b47fff',
  '#ff8c42','#7ec8e3','#ff6b9d','#6aff8c','#ffb347','#c084fc'
];

export const FACTOR_COLORS = [
  '#00d4ff','#ff4d6d','#ffd24d','#3dffa0','#b47fff','#ff8c42',
  '#7ec8e3','#ff6b9d','#6aff8c','#f97316','#38bdf8','#a3e635',
  '#c084fc','#facc15'
];

export const COMP_COLORS = {
  VIX:          '#ff3d5e',
  VVIX:         '#ff8c42',
  PutCall:      '#ffd24d',
  HYSpread:     '#b47fff',
  TED:          '#00d4ff',
  SkewIndex:    '#7ec8e3',
  CorrelBreak:  '#3dffa0',
  ATR_SPX:      '#ff6b9d',
  RealizedVol:  '#c084fc',
  BidAskProxy:  '#6aff8c',
  Dispersion:   '#f97316',
  FundingStress:'#38bdf8',
  BreadthDecay: '#a3e635',
};

// ─── Utilities ───────────────────────────────────────────────────────────────
export function fmt(n, d = 2) {
  return (n >= 0 ? '+' : '') + n.toFixed(d);
}

export function hexToRgba(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

export function sortTenors(tenors) {
  const toYrs = t => t.endsWith('M') ? parseFloat(t) / 12 : parseFloat(t);
  return [...tenors].sort((a, b) => toYrs(a) - toYrs(b));
}

// ─── Chart option helpers ─────────────────────────────────────────────────────
export function tooltipStyle(labelFn) {
  return {
    tooltip: {
      backgroundColor: '#090e14',
      borderColor: '#1e2f42',
      borderWidth: 1,
      titleColor: '#4a6880',
      bodyColor: '#c8dff0',
      titleFont: { family: 'IBM Plex Mono', size: 11 },
      bodyFont: { family: 'IBM Plex Mono', size: 13 },
      callbacks: {
        label: typeof labelFn === 'function'
          ? ctx => { const r = labelFn(ctx); return r !== null && r !== undefined ? r : undefined; }
          : ctx => ` ${ctx.parsed.y}`,
      },
    },
  };
}

export function lineOpts({ yCallback, tooltipCallback, legend = false }) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: legend
        ? { labels: { color: '#4a6880', font: { family: 'IBM Plex Mono', size: 12 } } }
        : { display: false },
      ...tooltipStyle(tooltipCallback || null),
    },
    scales: {
      x: {
        ticks: { color: '#4a6880', font: { family: 'IBM Plex Mono', size: 11 }, maxTicksLimit: 6 },
        grid: { color: '#172230' },
      },
      y: {
        ticks: { color: '#4a6880', font: { family: 'IBM Plex Mono', size: 11 }, callback: yCallback || undefined },
        grid: { color: '#172230' },
      },
    },
  };
}

// ─── API loaders ──────────────────────────────────────────────────────────────
async function apiFetch(path) {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export async function loadEquitiesData(market, lookback) {
  const qs = `?market=${market}&lookback=${lookback}`;
  const [retD, volD] = await Promise.all([
    apiFetch(`/api/equities/returns${qs}`),
    apiFetch(`/api/equities/volume${qs}`),
  ]);
  return { sectors: retD.sectors, volSectors: volD.sectors };
}

export async function loadFactorsData(market, lookback) {
  const d = await apiFetch(`/api/equities/factors?market=${market}&lookback=${lookback}`);
  return d.factors;
}

export async function loadFIData(market, lookback) {
  return apiFetch(`/api/fixedincome/yields?market=${market}&lookback=${lookback}`);
}

export async function loadDifficultyData(market, lookback) {
  return apiFetch(`/api/difficulty?market=${market}&lookback=${lookback}`);
}

export async function loadSummaryData(market) {
  return apiFetch(`/api/summary?market=${market}`);
}

export async function loadWatchlistPrices(tickers) {
  if (!tickers.length) return { prices: {} };
  return apiFetch(`/api/watchlist-prices?tickers=${encodeURIComponent(tickers.join(','))}`);
}

export async function loadInflationData(market) {
  return apiFetch(`/api/macro/inflation?market=${market}`);
}

export async function loadCentralBanksData(market) {
  return apiFetch(`/api/macro/central-banks?market=${market}`);
}

export async function loadCalendarData() {
  return apiFetch('/api/macro/calendar');
}
