import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getHome, money, putHomeAnswers } from '../api.js';
import { Alert, DetailPanel, PButton, StatusPill } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Field, Mark } from './GoalsParts.jsx';
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
 *
 * When data is missing or thin (THL-137, E10) Home is one of:
 *   E-01 no_data   — connect your bank, the path ahead, or two questions
 *   E-02 learning  — a rough estimate, "learning" with dates, starter questions
 *   E-03 irregular — a cautious estimate, labelled, with "Use a different amount"
 *   E-04 card_only — card spending only, and one prompt to link chequing
 * Rough and cautious numbers are shown rounded down to $10 (S7, E5). Exactly
 * one primary action on the page (E3); one alert at a time (C3).
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
  if (s.state === 'ok' && s.estimate === 'rough') {
    return {
      label, pill: 'Estimate',
      figure: s.shown >= 10 ? `About ${shown(s.shown)}` : 'Less than $10',
      context: s.income_source === 'told'
        ? 'Rough estimate from the income and rent you told us'
        : 'Rough estimate from your first few weeks',
    };
  }
  if (s.state === 'ok' && s.estimate === 'cautious') {
    return {
      label, pill: 'Cautious',
      figure: s.shown >= 10 ? shown(s.shown) : 'Less than $10',
      context: `Based on your lowest month of the last 3 (${shown(s.cautious.lowest)})`,
    };
  }
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
      let detail = `${plural(r.paycheques, 'paycheque')}${r.payer ? ` from ${r.payer}` : ''}${other ? ', and other income' : ''}`;
      if (r.source === 'entered' || r.source === 'told') detail = 'What you told us you earn';
      if (r.source === 'cautious') {
        detail = `Your lowest month of the last 3 was ${monthName(r.cautious.month)}, ${shown(r.cautious.lowest)}`;
      }
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
      if (r.count === 1) detail = r.first ? `1 bill on ${shortDate(r.first)}` : '1 bill';
      else if (r.count > 1) {
        detail = r.first && r.last && r.first !== r.last
          ? `${r.count} bills between ${shortDate(r.first)} and ${shortDate(r.last)}`
          : `${r.count} bills this month`;
      }
      return {
        key: r.key, label: 'Bills still to come', detail, amount: r.amount,
        lines: r.lines.map((b) => {
          const notes = ['estimate', 'late'].filter((k) => b[k]).map((k) => LINE_NOTES[k]);
          if (b.told) notes.push('what you told us');
          const when = b.date ? ` · ${shortDate(b.date)}` : '';
          return { label: `${b.label}${when}${notes.length ? ` (${notes.join(', ')})` : ''}`,
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
  // E5: the sheet keeps the exact rows and says what the card rounded.
  const note = s.state === 'ok' && s.estimate && s.amount > 0
    ? (s.shown >= 10 ? `Shown rounded down to ${shown(s.shown)}.` : 'Shown as less than $10.')
    : null;
  return {
    rows: withText,
    total: { ...total, display: total.amount > 0 ? shown(total.amount, true) : 'Nothing left', note },
  };
}

export default function HomePanel({ onTab, version }) {
  const [home, setHome] = useState(null);
  const [error, setError] = useState(null);
  const [explain, setExplain] = useState(false);
  const [income, setIncome] = useState(false);

  const load = useCallback(() => {
    setError(null);
    return getHome().then(setHome).catch(setError);
  }, []);
  // `version` moves after every import and sync, so the number follows them.
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!home) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading Home…</p></div>;

  const s = home.safe_to_spend;
  const ds = home.data_state;
  const p = parts(`${home.month}-01`);
  const save = (answers) => putHomeAnswers(answers).then(setHome);
  const link = () => onTab?.('banks');
  return (
    <div className="pk hm-page">
      <header className="hm-head">
        <p className="pk-overline">{`${MONTHS[p.m - 1]} ${p.y}`}</p>
        <h1 className="pk-h1">Home</h1>
      </header>
      <HomeBody s={s} ds={ds} onSave={save} onLink={link}
                onExplain={() => setExplain(true)} onIncome={() => setIncome(true)} />
      {explain && s.rows.length > 0 && (
        <HowWeWorkedItOut s={s} onClose={() => setExplain(false)}
                          onEdit={() => {
                            setExplain(false);
                            // Income she gave us, or the cautious figure, is
                            // changed here; detected pay is confirmed on the
                            // income page until THL-45's flow replaces it.
                            if (['told', 'cautious'].includes(s.income_source)) setIncome(true);
                            else onTab?.('plan');
                          }} />
      )}
      {income && (
        <IncomePanel s={s} told={ds.answers.income} onClose={() => setIncome(false)}
                     onSave={(amount) => save({ income: amount, override: !!s.cautious })
                       .then(() => setIncome(false))}
                     onReset={() => save({ income: 0 }).then(() => setIncome(false))} />
      )}
    </div>
  );
}

/** Which Home to draw, by data state (THL-137). Exactly one primary action. */
export function HomeBody({ s, ds, onSave, onLink, onExplain, onIncome }) {
  if (ds.kind === 'no_data') {
    return (
      <>
        <ConnectCard failed={ds.linking_failed} onLink={onLink} primary />
        <PathPreview />
        <WithoutLinking onSave={onSave} />
      </>
    );
  }
  if (ds.kind === 'card_only') {
    return (
      <>
        <CardOnlyHero ds={ds} month={s.month} onLink={onLink} />
        <MonthSoFar month={s.month} lines={ds.card_spending.lines}
                    note="Usual-month comparisons start once we’ve seen a full month." />
      </>
    );
  }
  const noAccounts = ds.history_days === 0;
  const alert = homeAlert(s, ds);
  return (
    <>
      {alert && (
        <Alert tone="info" action={alert.action} onAction={alert.action ? onIncome : undefined}>
          {alert.text}
        </Alert>
      )}
      <SafeToSpendCard s={s} onExplain={onExplain} />
      {ds.asks_questions && <StarterQuestions onSave={onSave} primary />}
      {ds.kind === 'learning' && !noAccounts && (
        <MonthSoFar month={s.month}
                    lines={[{ label: 'Spent so far', amount: ds.spent_so_far },
                            { label: 'Regular bills found', count: ds.bills_found }]}
                    note={ds.comparisons_from
                      ? `We’ll compare with your usual month from ${longDate(ds.comparisons_from)}.`
                      : 'We’ll compare with your usual month once we’ve seen one.'} />
      )}
      {noAccounts && <ConnectCard failed={ds.linking_failed} onLink={onLink}
                                  primary={!ds.asks_questions} />}
    </>
  );
}

/** One alert at a time, in the C3 order: connection, over plan, learning,
 * cautious. Connection and over plan arrive with steps 4 and 3. */
export function homeAlert(s, ds) {
  if (ds.kind === 'learning' && ds.history_days > 0 && ds.learning_until) {
    return {
      text: `Pearl is learning your patterns. Your number gets more exact after ${longDate(ds.learning_until)}, and comparisons with a usual month start on ${longDate(ds.comparisons_from)}.`,
    };
  }
  if (ds.kind === 'irregular') {
    return { text: 'Your income changes month to month, so this is a cautious estimate.',
             action: 'Use a different amount' };
  }
  return null;
}

/** SafeToSpendCard (H-01, H-02). */
export function SafeToSpendCard({ s, onExplain }) {
  const c = heroCopy(s);
  const canExplain = s.rows.length > 0;
  return (
    <section className="hm-sts" aria-labelledby="hm-sts-label">
      <div className="hm-sts-top">
        <p className="hm-sts-label" id="hm-sts-label">{c.label}</p>
        {c.pill && <StatusPill icon={s.estimate ? 'info' : 'check'}>{c.pill}</StatusPill>}
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
    </section>
  );
}

/** "How we worked this out" (X-01 to X-04): every input, adding up to the number. */
export function HowWeWorkedItOut({ s, onClose, onEdit }) {
  const [open, setOpen] = useState(null);
  const { rows, total } = sheetRows(s);
  const title = s.state === 'over'
    ? `Past this month’s plan: ${shown(s.over_by, true)}`
    : s.amount <= 0 ? 'Safe to spend: nothing left'
      : s.estimate ? `Safe to spend: about ${shown(s.shown)}`
        : `Safe to spend: ${shown(s.amount, true)}`;
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
      {total.note && <p className="pk-muted hm-note">{total.note}</p>}
      <button type="button" className="hm-link" onClick={onEdit}>
        Something look wrong? Edit your income or bills
      </button>
      <div className="hm-sheet-foot">
        <PButton variant="secondary" onClick={onClose}>Got it</PButton>
      </div>
    </DetailPanel>
  );
}

/** "$3,200", "3200", "3,200.50" → 3200.5; anything else → NaN. */
export function parseAmount(text) {
  const clean = String(text ?? '').replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return NaN;
  return Number(clean);
}

/** Starter questions (E-02): take-home pay and rent, for an estimate now. */
export function StarterQuestions({ onSave, primary = false, title = 'Help Pearl get it right sooner' }) {
  const [income, setIncome] = useState('');
  const [rent, setRent] = useState('');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const pay = parseAmount(income);
    const home = rent.trim() ? parseAmount(rent) : 0;
    if (!(pay > 0)) { setError({ field: 'income', text: 'Enter your monthly take-home pay, like 3200.' }); return; }
    if (Number.isNaN(home)) { setError({ field: 'rent', text: 'Enter your rent or mortgage, like 1650, or leave it empty.' }); return; }
    setError(null);
    setSaving(true);
    onSave({ income: pay, rent: home })
      .catch((err) => setError({ field: 'income', text: err.message }))
      .finally(() => setSaving(false));
  };
  return (
    <form className="hm-card" onSubmit={submit} aria-labelledby="hm-starter-title">
      <h2 className="pk-h3" id="hm-starter-title">{title}</h2>
      <p className="pk-muted">Two quick answers and we can estimate your month now.</p>
      <Field label="Monthly take-home pay" id="hm-income"
             error={error?.field === 'income' ? error.text : null}>
        <input id="hm-income" inputMode="decimal" autoComplete="off" placeholder="$4,300"
               value={income} onChange={(e) => setIncome(e.target.value)} />
      </Field>
      <Field label="Rent or mortgage" id="hm-rent"
             error={error?.field === 'rent' ? error.text : null}>
        <input id="hm-rent" inputMode="decimal" autoComplete="off" placeholder="$1,650"
               value={rent} onChange={(e) => setRent(e.target.value)} />
      </Field>
      <PButton type="submit" variant={primary ? 'primary' : 'secondary'} disabled={saving}>
        {saving ? 'Saving…' : 'Save answers'}
      </PButton>
    </form>
  );
}

/** E-01: nothing linked, or linking didn't finish. */
export function ConnectCard({ failed, onLink, primary = true }) {
  const [why, setWhy] = useState(false);
  return (
    <section className="hm-card hm-connect" aria-labelledby="hm-connect-title">
      <span className="pk-empty-icon"><PIcon name="search" size={24} /></span>
      <h2 className="pk-h3" id="hm-connect-title">Let’s connect your bank</h2>
      <p className="pk-muted">
        {failed
          ? 'Pearl works out what’s safe to spend from your accounts. Linking didn’t finish last time, and nothing was saved.'
          : 'Pearl works out what’s safe to spend from your accounts.'}
      </p>
      <PButton variant={primary ? 'primary' : 'secondary'} onClick={onLink}>
        {failed ? 'Try linking again' : 'Link your bank'}
      </PButton>
      <button type="button" className="hm-link" aria-expanded={why} onClick={() => setWhy(!why)}>
        Why Pearl needs this
      </button>
      {why && (
        <p className="pk-muted hm-why">
          Pearl reads what comes in, what’s due and what you’ve spent, so the number fits your
          month. It only reads; it can’t move money. You sign in through Plaid.
        </p>
      )}
    </section>
  );
}

const PATH = [
  { phase: 'protect', name: 'Protect', text: 'Know what’s coming in and going out' },
  { phase: 'build', name: 'Build', text: 'Build your Anchor' },
  { phase: 'unveil', name: 'Unveil', text: 'Start growing your money' },
];

/** E-01: the milestone path, as a preview. */
export function PathPreview() {
  return (
    <section className="hm-card" aria-labelledby="hm-path-title">
      <h2 className="pk-h3" id="hm-path-title">Your path</h2>
      <ol className="hm-path">
        {PATH.map((step) => (
          <li key={step.phase}>
            <Mark phase={step.phase} width={40} />
            <span className="pk-h3">{step.name}</span>
            <span className="pk-muted pk-label">{step.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** E-01: start without linking, with the two starter questions. */
export function WithoutLinking({ onSave }) {
  const [open, setOpen] = useState(false);
  if (open) return <StarterQuestions onSave={onSave} title="Two questions to start" />;
  return (
    <section className="hm-card" aria-labelledby="hm-nolink-title">
      <h2 className="pk-h3" id="hm-nolink-title">Prefer to start without linking?</h2>
      <p className="pk-muted">Tell us your take-home pay and rent and we’ll give you a rough estimate.</p>
      <button type="button" className="hm-link" onClick={() => setOpen(true)}>
        Answer two questions <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

/** E-02 and E-04: what's known this month, before the snapshot can compare. */
export function MonthSoFar({ month, lines, note }) {
  return (
    <section className="hm-card" aria-labelledby="hm-sofar-title">
      <h2 className="pk-h3" id="hm-sofar-title">{`${monthName(month)} so far`}</h2>
      <dl className="hm-facts">
        {lines.map((l) => (
          <div key={l.label}>
            <dt>{l.label}</dt>
            <dd>{'count' in l
              ? (l.count > 0 ? l.count : 'None yet')
              : (l.amount > 0 ? shown(l.amount) : 'Nothing yet')}</dd>
          </div>
        ))}
      </dl>
      {note && <p className="pk-muted pk-label">{note}</p>}
    </section>
  );
}

/** E-04: only a card linked, so spending only, and one prompt to link chequing. */
export function CardOnlyHero({ ds, month, onLink }) {
  const amount = ds.card_spending.amount;
  return (
    <section className="hm-card" aria-labelledby="hm-cardonly-title">
      <p className="pk-overline" id="hm-cardonly-title">{`Card spending in ${monthName(month)}`}</p>
      <p className="pk-amount">{amount > 0 ? shown(amount) : 'Nothing yet'}</p>
      <p className="pk-muted">
        With only a credit card linked we can see spending, but not what comes in, so there’s
        no safe-to-spend yet.
      </p>
      <PButton onClick={onLink}>Link your chequing account</PButton>
    </section>
  );
}

/** E-03: "Use a different amount" instead of the cautious figure. */
export function IncomePanel({ s, told, onClose, onSave, onReset }) {
  const [value, setValue] = useState(told ? String(told) : '');
  const [error, setError] = useState(null);
  const submit = (e) => {
    e.preventDefault();
    const amount = parseAmount(value);
    if (!(amount > 0)) { setError('Enter what you usually take home in a month, like 3800.'); return; }
    onSave(amount).catch((err) => setError(err.message));
  };
  return (
    <DetailPanel label="Use a different amount" overline="Your income" onClose={onClose}>
      <form className="hm-form" onSubmit={submit}>
        <h1 className="pk-h2">Use a different amount</h1>
        {s.cautious && (
          <p className="pk-muted">
            {`We used ${shown(s.cautious.lowest)}, your lowest month of the last 3. If you expect more, tell us what you usually take home in a month. You can change it any time.`}
          </p>
        )}
        <Field label="Monthly take-home pay" id="hm-override" error={error}>
          <input id="hm-override" inputMode="decimal" autoComplete="off" value={value}
                 onChange={(e) => setValue(e.target.value)} />
        </Field>
        <PButton type="submit">Save</PButton>
        {told && s.cautious && (
          <PButton variant="secondary" onClick={() => onReset().catch((err) => setError(err.message))}>
            {`Go back to the cautious figure (${shown(s.cautious.lowest)})`}
          </PButton>
        )}
      </form>
    </DetailPanel>
  );
}
