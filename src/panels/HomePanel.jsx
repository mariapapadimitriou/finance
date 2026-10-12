import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getHome, money } from '../api.js';
import { DetailPanel, PButton, StatusPill } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import './home.css';

/**
 * Home (Pearl THL-125 H-01/H-02, laid out as THL-129 GR-05; THL-44, THL-46).
 *
 * The landing screen. This step draws its header, the safe-to-spend card and
 * "How we worked this out" (X-01 to X-04). The cards below it (week strip,
 * path, Can I afford it?, snapshot, suggestions, needs a look, budgets,
 * debts) arrive in later steps, in that order (THL-9 decision L1).
 *
 * Copy rules from the THL-9 decisions: the hero is in cents, everything else
 * in whole dollars (S7); no display number carries a sign (S3); a month past
 * its plan says by how much and never shows $0 (S1); days left include
 * today (S6); with no income there is no number, only the question (E1).
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function parts(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return { y, m, d, weekday: DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] };
}

/** "October" from "2026-10" or "2026-10-09". */
export const monthName = (iso) => MONTHS[parts(`${iso.slice(0, 7)}-01`).m - 1];
/** "Oct 12". */
export const shortDate = (iso) => { const p = parts(iso); return `${MONTHS[p.m - 1].slice(0, 3)} ${p.d}`; };
/** "Friday, October 16". */
export const longDate = (iso) => { const p = parts(iso); return `${p.weekday}, ${MONTHS[p.m - 1]} ${p.d}`; };

/** An amount as shown: never signed, cents where the decisions ask for them. */
export const shown = (n, cents = false) => money(Math.abs(n), { cents });

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The safe-to-spend card's words, for every state (H-01, H-02, E1). */
export function heroCopy(s) {
  const month = monthName(s.month);
  const label = `Safe to spend in ${month}`;
  if (s.state === 'needs_income') {
    return {
      label, figure: null, pill: null,
      context: `Tell us what you expect to earn and we’ll work out what’s safe to spend in ${month}.`,
    };
  }
  const next = s.next_pay ? `Your next pay arrives on ${longDate(s.next_pay)}.` : null;
  if (s.state === 'over') {
    return {
      label, figure: shown(s.over_by, true), figureWords: 'past this month’s plan', pill: null,
      context: [next, 'That happens, and it’s easy to catch up.'].filter(Boolean).join(' '),
    };
  }
  if (s.amount === 0) {
    return {
      label, figure: null, pill: null,
      context: ['This month’s plan is used up exactly.', next].filter(Boolean).join(' '),
    };
  }
  return {
    label, figure: shown(s.amount, true), pill: 'On track',
    context: s.per_day >= 1
      ? `${plural(s.days_left, 'day')} left · about ${shown(s.per_day)} a day`
      : `${plural(s.days_left, 'day')} left`,
  };
}

const LINE_NOTES = { estimate: 'estimate', late: 'usually here by now' };

// What a row says instead of "$0.00" (S1: never $0 on Home).
const NOTHING = { income: 'None yet', bills: 'None', spent: 'Nothing yet', set_aside: 'Done' };

/** The sheet's rows and total (X-01, X-02), in the order they're subtracted. */
export function sheetRows(s) {
  const rows = s.rows.map((r) => {
    if (r.key === 'income') {
      const other = r.lines.some((l) => l.kind !== 'salary');
      const detail = r.source === 'entered'
        ? 'What you told us you earn'
        : `${plural(r.paycheques, 'paycheque')}${r.payer ? ` from ${r.payer}` : ''}${other ? ', and other income' : ''}`;
      return {
        key: r.key, label: 'Money coming in this month', detail, amount: r.amount,
        lines: r.lines.map((l) => ({
          label: l.date ? `${l.label} · ${shortDate(l.date)}${l.arrived ? '' : ' (on its way)'}` : l.label,
          amount: l.amount,
        })),
      };
    }
    if (r.key === 'bills') {
      let detail = 'Nothing else due this month';
      if (r.count === 1) detail = `1 bill on ${shortDate(r.first)}`;
      else if (r.count > 1) detail = `${r.count} bills between ${shortDate(r.first)} and ${shortDate(r.last)}`;
      return {
        key: r.key, label: 'Bills still to come', detail, amount: r.amount,
        lines: r.lines.map((b) => {
          const notes = ['estimate', 'late'].filter((k) => b[k]).map((k) => LINE_NOTES[k]);
          return { label: `${b.label} · ${shortDate(b.date)}${notes.length ? ` (${notes.join(', ')})` : ''}`,
                   amount: b.amount };
        }),
      };
    }
    if (r.key === 'spent') {
      return {
        key: r.key, label: 'Already spent', amount: r.amount,
        detail: `${r.pending > 0 ? 'Includes pending' : 'Pending included'} · transfers and card payments don’t count`,
        lines: r.lines,
      };
    }
    return {
      key: r.key,
      label: r.goal === 'anchor' ? 'Set aside for your Anchor' : 'Set aside for your saving goal',
      detail: `Your monthly goal is ${shown(r.target)}${r.saved > 0 ? ` · ${shown(r.saved)} saved so far` : ''}`,
      amount: r.amount, lines: [],
    };
  });
  const total = s.state === 'over'
    ? { label: 'Past this month’s plan', amount: s.over_by,
        detail: s.next_pay ? `Your next pay arrives on ${longDate(s.next_pay)}` : null }
    : { label: 'Safe to spend', amount: s.amount,
        detail: s.per_day >= 1 ? `About ${shown(s.per_day)} a day for ${plural(s.days_left, 'day')}` : null };
  const withText = rows.map((r) => ({
    ...r, display: r.amount > 0 ? shown(r.amount, true) : NOTHING[r.key],
  }));
  return {
    rows: withText,
    total: { ...total, display: total.amount > 0 ? shown(total.amount, true) : 'Nothing left' },
  };
}

export default function HomePanel({ onTab, version }) {
  const [home, setHome] = useState(null);
  const [error, setError] = useState(null);
  const [explain, setExplain] = useState(false);

  const load = useCallback(() => {
    setError(null);
    return getHome().then(setHome).catch(setError);
  }, []);
  // `version` moves after every import and sync, so the number follows them.
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!home) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading Home…</p></div>;

  const s = home.safe_to_spend;
  const p = parts(`${home.month}-01`);
  return (
    <div className="pk hm-page">
      <header className="hm-head">
        <p className="pk-overline">{`${MONTHS[p.m - 1]} ${p.y}`}</p>
        <h1 className="pk-h1">Home</h1>
      </header>
      <SafeToSpendCard s={s} onExplain={() => setExplain(true)} onIncome={() => onTab?.('plan')} />
      {explain && s.rows.length > 0 && (
        <HowWeWorkedItOut s={s} onClose={() => setExplain(false)}
                          onEdit={() => { setExplain(false); onTab?.('plan'); }} />
      )}
    </div>
  );
}

/** SafeToSpendCard (H-01, H-02). */
export function SafeToSpendCard({ s, onExplain, onIncome }) {
  const c = heroCopy(s);
  const canExplain = s.rows.length > 0;
  return (
    <section className="hm-sts" aria-labelledby="hm-sts-label">
      <div className="hm-sts-top">
        <p className="hm-sts-label" id="hm-sts-label">{c.label}</p>
        {c.pill && <StatusPill icon="check">{c.pill}</StatusPill>}
      </div>
      {c.figure && (
        <p className="hm-sts-figure">
          <span className="pk-amount">{c.figure}</span>
          {c.figureWords && <span className="hm-sts-words">{` ${c.figureWords}`}</span>}
        </p>
      )}
      <p className="hm-sts-context">
        {c.context}
        {canExplain && (
          <>
            {' · '}
            <button type="button" className="hm-link" onClick={onExplain}>
              How we worked this out
            </button>
          </>
        )}
      </p>
      {s.state === 'needs_income' && (
        <div><PButton variant="secondary" onClick={onIncome}>Add your income</PButton></div>
      )}
    </section>
  );
}

/** "How we worked this out" (X-01 to X-04): every input, adding up to the number. */
export function HowWeWorkedItOut({ s, onClose, onEdit }) {
  const [open, setOpen] = useState(null);
  const { rows, total } = sheetRows(s);
  const title = s.state === 'over'
    ? `Past this month’s plan: ${shown(s.over_by, true)}`
    : s.amount > 0 ? `Safe to spend: ${shown(s.amount, true)}` : 'Safe to spend: nothing left';
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} sheet className="hm-sheet">
      <h1 className="pk-h2">{title}</h1>
      <p className="pk-muted">{`Every number behind it, for ${monthName(s.month)}.`}</p>
      <div className="hm-ledger">
        {rows.map((r) => {
          const expanded = open === r.key;
          const id = `hm-lines-${r.key}`;
          return (
            <div key={r.key} className="hm-row">
              <button type="button" className="hm-row-head" aria-expanded={expanded}
                      aria-controls={r.lines.length ? id : undefined}
                      disabled={!r.lines.length}
                      onClick={() => setOpen(expanded ? null : r.key)}>
                <PIcon name={expanded ? 'chevronDown' : 'chevronRight'} size={16} />
                <span className="hm-row-text">
                  <span className="hm-row-label">{r.label}</span>
                  {r.detail && <span className="hm-row-detail">{r.detail}</span>}
                </span>
                <span className="hm-row-amount">{r.display}</span>
              </button>
              {expanded && (
                <ul className="hm-lines" id={id}>
                  {r.lines.map((l, i) => (
                    <li key={i}><span>{l.label}</span><span>{shown(l.amount, true)}</span></li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
        <div className="hm-total">
          <span className="hm-row-text">
            <span className="pk-h3">{total.label}</span>
            {total.detail && <span className="hm-row-detail">{total.detail}</span>}
          </span>
          <span className="pk-h3">{total.display}</span>
        </div>
      </div>
      <button type="button" className="hm-link" onClick={onEdit}>
        Something look wrong? Edit your income or bills
      </button>
      <div className="hm-sheet-foot">
        <PButton variant="secondary" onClick={onClose}>Got it</PButton>
      </div>
    </DetailPanel>
  );
}
