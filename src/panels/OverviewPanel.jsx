import { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart.jsx';
import Treemap from '../components/Treemap.jsx';
import { MerchantMark, MonthFreshness, Notice } from '../components/ui.jsx';
import { Donut, RingLegend, RingRow } from '../components/Ring.jsx';
import { dailySpendConfig, paceConfig } from '../charts.js';
import { categoryColors, categoryGradient } from '../categoryColors.js';
import {
  dateLabel, getBreakdown, getTransactions, money, monthLabel, pct,
} from '../api.js';

const VIEW_KEY = 'spendie.month.view';

/**
 * This month: what was spent, how it is running against a usual month, where
 * it went, and the latest charges. The figures speak for themselves.
 */
export default function OverviewPanel({ summary, theme, month, onTab, version = 0 }) {
  const [breakdown, setBreakdown] = useState(null);
  const [recent, setRecent] = useState([]);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'trends'; } catch { return 'trends'; }
  });

  useEffect(() => {
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* per visit then */ }
  }, [view]);

  useEffect(() => {
    if (!month) return undefined;
    let cancelled = false;
    getBreakdown(month)
      .then((d) => { if (!cancelled) setBreakdown(d); })
      .catch(() => { if (!cancelled) setBreakdown(null); });
    getTransactions({ month, limit: 12 })
      .then((d) => { if (!cancelled) setRecent(d.transactions ?? []); })
      .catch(() => { if (!cancelled) setRecent([]); });
    return () => { cancelled = true; };
  }, [month, version]);

  const pace = breakdown?.pace;
  const config = useMemo(() => (pace ? paceConfig(pace) : null), [pace, theme]);
  const daily = breakdown?.daily ?? [];
  const dailyConfig = useMemo(
    () => (daily.length ? dailySpendConfig(daily) : null), [daily, theme]);
  const categories = (breakdown?.categories ?? []).filter((c) => c.amount > 0);
  const spent = pace?.total ?? currentMonthSpend(summary, month);
  const gaps = summary.coverage_gaps ?? [];
  const charges = recent.filter((t) => t.amount > 0).slice(0, 8);

  return (
    <div className="stack">
      {gaps.length > 0 && (
        <Notice>{gaps.length} month{gaps.length === 1 ? '' : 's'} missing</Notice>
      )}
      <MonthFreshness month={month} summary={summary} onTab={onTab} from="overview" />

      <div className="segmented" role="group" aria-label="View">
        <button aria-pressed={view === 'trends'} onClick={() => setView('trends')}>
          Trends
        </button>
        <button aria-pressed={view === 'categories'} onClick={() => setView('categories')}>
          Categories
        </button>
      </div>

      {view === 'trends' ? (
        <div>
        <div className="month-hero">
          <div>
            <div className="hero-total">{money(spent, { cents: true })}</div>
            <div className="hero-sub">
              {breakdown?.bills ? 'Everyday spending in ' : 'Spent in '}
              {monthLabel(month, { full: true })}
            </div>
          </div>
          {pace?.average_total != null && (
            <div className="hero-side">
              <div className="k"><span className="dot" aria-hidden="true" />
                {pace.compared.length} month avg.</div>
              <div className="v num">{money(pace.average_total, { cents: true })}</div>
            </div>
          )}
        </div>
        {breakdown?.bills && <Bills bills={breakdown.bills} />}
        </div>
      ) : categories.length > 0 && (
        // Every category, bills included: the ring is where the whole month
        // is, while the headline above is the part worth watching.
        <CategoryRing categories={categories}
                      total={categories.reduce((t, c) => t + c.amount, 0)} month={month} />
      )}

      {view === 'trends' ? (
        <>
          {config && (
            <div className="pace">
              <Chart config={config} theme={theme}
                     ariaLabel={`${money(spent)} spent so far in ${monthLabel(month, { long: true })}${
                       pace.average_total != null
                         ? `, against ${money(pace.average_total)} in a usual month` : ''}`} />
            </div>
          )}
          {dailyConfig && (
            <section>
              <h2 className="chart-title">Last 90 days</h2>
              <div className="chart short">
                <Chart config={dailyConfig} theme={theme}
                       ariaLabel={`Spending each day for the last 90 days, ${
                         money(daily.reduce((t, d) => t + d.amount, 0))} in all`} />
              </div>
            </section>
          )}
        </>
      ) : (
        <>
          {categories.length > 0 && (
            <Treemap items={categories.map((c) => ({ label: c.category, value: c.amount }))} />
          )}
          <section>
            <h2 className="section-title" style={{ cursor: 'default', margin: '8px 0 4px' }}>
              Categories
            </h2>
            <div className="cat-list">
              {categories.map((c) => (
                <div className="cat-row" key={c.category}>
                  <span className="sw" style={{ background: categoryGradient(c.category) }}
                        aria-hidden="true" />
                  <div>
                    <div className="n">{c.category}</div>
                    <div className="c">
                      {c.transactions} transaction{c.transactions === 1 ? '' : 's'}
                    </div>
                  </div>
                  <div>
                    <div className="a num">{money(c.amount, { cents: true })}</div>
                    <div className="p">{pct(c.share)}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {charges.length > 0 && (
        <section>
          <button className="section-title" onClick={() => onTab?.('transactions')}>
            Transactions
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
          <RecentList rows={charges} />
        </section>
      )}
    </div>
  );
}

/**
 * The month as a donut: the biggest categories, and the rest as one slice.
 * Colours are each category's own, so a slice matches its row below.
 */
/**
 * The bills the plan already set aside — the mortgage, the hydro — paid this
 * month, apart from the headline: they aren't spending to watch.
 */
function Bills({ bills }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" className="bills-row" aria-expanded={open}
              onClick={() => setOpen((o) => !o)}>
        <span>Bills from your plan</span>
        <span className="num">
          <strong>{money(bills.paid)}</strong>
          <span className="muted"> of {money(bills.planned)} paid</span>
          {' '}{open ? '▴' : '▾'}
        </span>
      </button>
      {open && (
        <ul className="bills-list">
          {bills.items.map((b) => (
            <li key={b.category}>
              <span>{b.name}</span>
              <span className="num">
                {money(b.paid)} <span className="muted">/ {money(b.planned)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CategoryRing({ categories, total, month }) {
  const top = categories.slice(0, 5);
  const rest = categories.slice(5).reduce((t, c) => t + c.amount, 0);
  const parts = [
    ...top.map((c) => ({ label: c.category, value: c.amount,
                         color: categoryColors(c.category)[0] })),
    rest > 0 && { label: `${categories.length - 5} more`, value: rest,
                  color: 'var(--surface-3)' },
  ].filter(Boolean);

  return (
    <RingRow>
      <Donut size={172} thickness={18}
             segments={parts.map((p) => ({ ...p, title: money(p.value) }))}>
        <div className="small-big num">{money(total)}</div>
        <div className="under">{monthLabel(month, { long: true })}</div>
      </Donut>
      <RingLegend items={parts.slice(0, 4).map((p) => ({
        label: p.label, color: p.color, value: money(p.value),
      }))} />
    </RingRow>
  );
}

function RecentList({ rows }) {
  const groups = [];
  rows.forEach((t) => {
    const label = dayLabel(t.date);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.rows.push(t);
    else groups.push({ label, rows: [t] });
  });
  return (
    <div className="txn-list">
      {groups.map((g) => (
        <div key={g.label}>
          <div className="txn-day">{g.label}</div>
          {g.rows.map((t) => (
            <div className="txn-row" key={t.id}>
              <MerchantMark logo={t.logo} name={t.merchant} className="ic"
                            style={{ background: categoryGradient(t.category) }} />
              <div style={{ minWidth: 0 }}>
                <div className="m">{t.merchant}</div>
                <div className="c">{t.category}</div>
              </div>
              <div>
                <div className="a">
                  −{money(t.my_share ?? t.amount, { cents: true })}
                </div>
                {t.my_share != null && (
                  <div className="c">of {money(t.amount, { cents: true })}</div>
                )}
                {t.invested != null && (
                  <div className="c">invested {money(t.invested, { cents: true })}</div>
                )}
                {t.raw && typeof t.raw === 'string' && t.raw.includes('"pending": true') && (
                  <span className="pill">Pending</span>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function dayLabel(iso) {
  const today = new Date();
  const d = new Date(`${iso}T00:00:00`);
  const diff = Math.round((new Date(today.toDateString()) - d) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  return dateLabel(iso);
}

function currentMonthSpend(summary, month) {
  return summary.monthly?.find((m) => m.month === month)?.spend ?? 0;
}
