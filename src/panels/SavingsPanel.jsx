import { useState } from 'react';
import { Empty } from '../components/ui.jsx';
import { dateLabel, dismissFinding, money, restoreFinding } from '../api.js';

/**
 * Cut back: one feed of insights.
 *
 * Three sources, one shape. What the plan says about itself (written in
 * advance, shown when it holds — finance/insights/profile.py), what could be
 * cut (finance/insights/rules.py, ranked by what it saves), and what the
 * recurring charges are doing (a price that went up, a renewal coming, ones
 * that stopped). Each card is a headline and a figure, with the one thing to
 * do about it.
 */
export default function SavingsPanel({ insights, recurring, onRefresh, onTab }) {
  const [busy, setBusy] = useState(null);
  const [showHidden, setShowHidden] = useState(false);

  const findings = [...(insights?.findings ?? [])]
    .sort((a, b) => b.annual_saving - a.annual_saving);
  const observations = insights?.observations ?? [];
  const hidden = insights?.hidden ?? [];
  const yearly = insights?.summary?.weighted_annual ?? 0;

  async function act(fn, id) {
    setBusy(id);
    try {
      await fn(id);
      await onRefresh();
    } finally {
      setBusy(null);
    }
  }
  const hide = (id) => act(dismissFinding, id);

  const bySeverity = (s) => observations.filter((o) => o.severity === s);
  const cards = [
    ...bySeverity('act').map((o) => observationCard(o, onTab)),
    ...findings.map(findingCard),
    ...bySeverity('watch').map((o) => observationCard(o, onTab)),
    ...subscriptionCards(recurring),
    ...bySeverity('good').map((o) => observationCard(o, onTab)),
    ...observations.filter((o) => !['act', 'watch', 'good'].includes(o.severity))
      .map((o) => observationCard(o, onTab)),
  ];

  return (
    <div className="stack">
      {yearly > 0 && (
        <div className="month-hero">
          <div>
            <div className="hero-total">{money(yearly)}</div>
            <div className="hero-sub">a year you could save</div>
          </div>
        </div>
      )}

      {cards.length === 0 ? (
        <Empty title="Nothing to cut that we can see" />
      ) : (
        <div className="insights">
          {cards.map((c) => (
            <Insight key={c.key} card={c} busy={busy === c.id}
                     onHide={c.id ? () => hide(c.id) : null} />
          ))}
        </div>
      )}

      {hidden.length > 0 && (
        <div className="hidden-insights">
          <button className="btn quiet" onClick={() => setShowHidden(!showHidden)}>
            {hidden.length} hidden · {showHidden ? 'Close' : 'Show'}
          </button>
          {showHidden && (
            <ul>
              {hidden.map((h) => (
                <li key={h.id}>
                  <span>{h.title}</span>
                  <button className="btn quiet" disabled={busy === h.id}
                          onClick={() => act(restoreFinding, h.id)}>
                    Restore
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/* ── The card ───────────────────────────────────────────────────────────── */

function Insight({ card: c, busy, onHide }) {
  const [open, setOpen] = useState(false);
  return (
    <article className={`insight tone-${c.tone}`}>
      <span className="chip" aria-hidden="true"><Glyph name={c.icon} /></span>
      <div className="body">
        <div className="t">{c.title}</div>
        {c.sub && <div className="s">{c.sub}</div>}
        {c.pills?.length > 0 && (
          <div className="pills">
            {c.pills.map((p) => <span className="pill" key={p}>{p}</span>)}
          </div>
        )}
        {open && c.evidence && (
          <div className="table-wrap evidence">
            <table>
              <tbody>
                {c.evidence.map((e, i) => (
                  <tr key={`${e.date}-${e.merchant}-${i}`}>
                    <td className="muted">{dateLabel(e.date)}</td>
                    <td className="merchant">{e.merchant}</td>
                    <td className="r num">{money(e.amount, { cents: true })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(c.action || c.evidence || onHide) && (
          <div className="acts">
            {c.action}
            {c.evidence?.length > 0 && (
              <button className="link" onClick={() => setOpen(!open)}>
                {open ? 'Hide charges' : `See ${c.evidence.length} charges`}
              </button>
            )}
            {onHide && (
              <button className="link quiet" onClick={onHide} disabled={busy}>
                {busy ? 'Hiding…' : 'Hide'}
              </button>
            )}
          </div>
        )}
      </div>
      {c.figure && (
        <div className="fig">
          <div className="v num">{c.figure}</div>
          {c.unit && <div className="u">{c.unit}</div>}
        </div>
      )}
    </article>
  );
}

const GLYPHS = {
  alert: 'M12 3l10 18H2L12 3zM12 10v4M12 17.5v.01',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  check: 'M20 6L9 17l-5-5',
  scissors: 'M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12',
  repeat: 'M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3',
  up: 'M12 19V5M5 12l7-7 7 7',
  calendar: 'M4 6h16v14H4zM4 10h16M9 3v4M15 3v4',
  pause: 'M8 5v14M16 5v14',
};

function Glyph({ name }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
         strokeLinecap="round" strokeLinejoin="round">
      <path d={GLYPHS[name] ?? GLYPHS.eye} />
    </svg>
  );
}

/* ── Where the cards come from ──────────────────────────────────────────── */

const OBSERVATION_TONE = {
  act: ['critical', 'alert'], watch: ['warning', 'eye'], good: ['good', 'check'],
};

function observationCard(o, onTab) {
  const [tone, icon] = OBSERVATION_TONE[o.severity] ?? OBSERVATION_TONE.watch;
  return {
    key: `o-${o.id}`, id: o.id, tone, icon,
    title: o.title,
    figure: o.metric || null,
    action: o.tab && o.action && onTab
      ? <button className="link" onClick={() => onTab(o.tab)}>{o.action}</button>
      : null,
  };
}

function findingCard(f) {
  const merchants = f.merchants ?? [];
  return {
    key: `f-${f.id}`, id: f.id, tone: 'brand', icon: 'scissors',
    title: f.title,
    sub: `${money(f.monthly_saving)} a month`,
    figure: money(f.annual_saving), unit: 'a year',
    pills: [
      f.category,
      ...merchants.slice(0, 2),
      merchants.length > 2 ? `+${merchants.length - 2} more` : null,
    ].filter(Boolean),
    evidence: f.evidence?.length ? f.evidence : null,
  };
}

const RARE = new Set(['quarterly', 'semiannual', 'annual']);
const RENEWAL_DAYS = 14;

function subscriptionCards(recurring) {
  const items = recurring?.recurring ?? [];
  const summary = recurring?.summary ?? {};
  const active = items.filter((r) => r.active);
  const cards = [];

  if (active.length > 0) {
    cards.push({
      key: 's-total', tone: 'neutral', icon: 'repeat',
      title: `${active.length} subscription${active.length === 1 ? '' : 's'}`,
      sub: `${money(summary.annual_total ?? 0)} a year`,
      figure: money(summary.monthly_total ?? 0), unit: 'a month',
      pills: [...active].sort((a, b) => b.annual_cost - a.annual_cost)
        .slice(0, 4).map((r) => r.merchant),
    });
  }

  active.filter((r) => r.price_change?.direction === 'increase').forEach((r) => {
    cards.push({
      key: `s-up-${r.merchant}-${r.amount}`, tone: 'warning', icon: 'up',
      title: `${r.merchant} went up`,
      sub: `${money(r.price_change.from, { cents: true })} → ${
        money(r.price_change.to, { cents: true })}`,
      figure: `+${Math.round(r.price_change.pct * 100)}%`,
    });
  });

  const today = new Date(new Date().toDateString());
  active.filter((r) => RARE.has(r.cadence) && r.next_expected).forEach((r) => {
    const days = Math.round((new Date(`${r.next_expected}T00:00:00`) - today) / 86400000);
    if (days < 0 || days > RENEWAL_DAYS) return;
    cards.push({
      key: `s-renew-${r.merchant}-${r.amount}`, tone: 'neutral', icon: 'calendar',
      title: `${r.merchant} renews ${days === 0 ? 'today' : dateLabel(r.next_expected)}`,
      figure: money(r.amount, { cents: true }),
    });
  });

  const lapsed = items.filter((r) => !r.active && r.confidence >= 0.6);
  if (lapsed.length > 0) {
    cards.push({
      key: 's-lapsed', tone: 'neutral', icon: 'pause',
      title: `${lapsed.length} stopped charging`,
      sub: lapsed.slice(0, 3).map((r) => r.merchant).join(', ')
        + (lapsed.length > 3 ? ` and ${lapsed.length - 3} more` : ''),
    });
  }
  return cards;
}
