import { useState } from 'react';
import { money, quickSortDone, quickSortSeen, quickSortStep, undoChange } from '../api.js';
import { Dialog, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import SortCard, { SortedCard } from './SortCard.jsx';
import './quicksort.css';

/**
 * Quick sort when you come back (Pearl THL-244 QS-01 to QS-06; THL-254).
 *
 * On sign-in, when there are new transactions Pearl isn't sure of (the
 * same rows Needs a look asks about, THL-227), a modal on the web and a
 * sheet on a phone: QS-01 the prompt, with Start and Later; then one sort
 * card per transaction (SortCard.jsx, THL-263: the same questions, options,
 * Remember and Undo as Needs a look), each ending on the Sorted card with
 * Next, and "Later" at the top throughout; QS-04 the done screen: safe to
 * spend before → after, one line on why, and how many rules were saved.
 * Shown at most once a day. Later and anything skipped stay in Needs a look.
 */
export default function QuickSort({ data, categories = [], onClose, onChanged }) {
  const [step, setStep] = useState('prompt');
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  // The card just sorted (the Sorted card), and where to pick up after Undo.
  const [sorted, setSorted] = useState(null);
  const [resume, setResume] = useState(null);
  const items = data.items ?? [];
  const ids = items.map((x) => x.id);
  const item = items[i];

  const run = async (fn, then) => {
    setBusy(true); setError(null);
    try {
      const r = await fn();
      then?.(r);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  // Later closes whatever the server says: a failed "seen" must never leave
  // the sheet up with no way off it (2026-10-21).
  const later = () => { quickSortSeen(ids, false).catch(() => {}); onClose?.(); };
  const start = () => run(() => quickSortSeen(ids, true), () => setStep('card'));
  const next = () => {
    setSorted(null);
    setResume(null);
    if (i + 1 < items.length) { setI(i + 1); setStep('card'); return; }
    run(() => quickSortDone(), (r) => { setDone(r); setStep('done'); onChanged?.(); });
  };
  const skip = () => run(() => quickSortStep(item.id, { action: 'skip' }), next);
  // The sort card did the work; the batch notes what it said (QS-04).
  const commit = (fn, { answers, effect }) => run(async () => {
    const r = await fn();
    await quickSortStep(item.id, { action: 'marked', title: r.title || '' });
    return r;
  }, (r) => setSorted({ key: item.id, it: asItem(item), answers, effect, title: r.title,
                        detail: r.detail || effect || '', undo: r.undo, rule: r.rule || '' }));
  const reopen = (k = sorted.answers.length - 1) => run(async () => {
    if (sorted.undo) await undoChange(sorted.undo);
  }, () => {
    const last = sorted.answers[sorted.answers.length - 1];
    setResume({ path: sorted.answers.slice(0, -1), edit: k < sorted.answers.length - 1 ? k : null,
                name: last?.step === 'who_to' || last?.step === 'name' ? last.label : '' });
    setSorted(null);
  });
  const finish = () => { onClose?.(); };

  if (step === 'prompt') return <Prompt count={items.length} busy={busy} error={error} onStart={start} onLater={later} />;
  if (step === 'done') return <Done r={done} onDone={finish} />;
  if (!item) return null;
  return (
    <Dialog labelledBy="qs-title" onClose={finish} className="qs-dialog">
      <Head label={`Quick sort · ${i + 1} of ${items.length}`} action={{ label: 'Later', onClick: finish }} />
      <Progress n={items.length} at={i} />
      <h2 className="pk-sr" id="qs-title">Quick sort</h2>
      {error && <p className="pk-error" role="alert">{error.message || 'That didn’t save. Try again.'}</p>}
      <section className="nl-card nl-stack qs-sort" aria-label={sorted ? 'Sorted' : 'Question'}>
        {sorted ? (
          <SortedCard entry={sorted} busy={busy} onNext={next} onUndo={() => reopen()} onReopen={reopen} />
        ) : (
          <SortCard key={`${item.id}-${resume ? 'r' : 'q'}`} it={asItem(item)} categories={categories} busy={busy}
                    commit={commit} onSkip={skip}
                    initialPath={resume?.path ?? null} initialEdit={resume?.edit ?? null} initialName={resume?.name ?? ''} />
        )}
      </section>
    </Dialog>
  );
}

/** A quick-sort row as the sort card's item: Pearl's guess is the first question. */
export function asItem(item) {
  return {
    key: `cat:${item.id}`, kind: 'category', guess: item.guess, learnable: true,
    txn: { id: item.id, merchant: item.merchant, date: item.date, logo: item.logo, account_name: item.account,
           amount: item.inflow ? -Math.abs(item.amount) : Math.abs(item.amount) },
  };
}

function Head({ label, action }) {
  return (
    <div className="qs-head">
      <p className="pk-overline">{label}</p>
      {action && <button type="button" className="txd-link" onClick={action.onClick}>{action.label}</button>}
    </div>
  );
}

/** QS-02's progress: one segment per card, the ones done filled. */
export function Progress({ n, at }) {
  return (
    <div className="qs-progress" role="progressbar" aria-valuemin={0} aria-valuemax={n} aria-valuenow={at + 1}
         aria-label={`Card ${at + 1} of ${n}`}>
      {Array.from({ length: n }, (_, k) => <span key={k} className={k <= at ? 'on' : ''} />)}
    </div>
  );
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export function longDate(iso) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${WEEKDAYS[new Date(y, m - 1, d).getDay()]}, ${MONTHS[m - 1]} ${d}`;
}

/** QS-01. */
export function Prompt({ count, busy, error, onStart, onLater }) {
  return (
    <Dialog labelledBy="qs-title" describedBy="qs-sub" onClose={onLater} className="qs-dialog">
      <p className="pk-overline accent">Welcome back</p>
      <h2 className="pk-h2" id="qs-title">
        {count === 1 ? 'You’ve got 1 new transaction to sort' : `You’ve got ${count} new transactions to sort`}
      </h2>
      <p className="pk-muted" id="qs-sub">
        Pearl isn’t sure what {count === 1 ? 'it was' : 'these were'}. Sorting {count === 1 ? 'it' : 'them'} keeps Allowance right, and takes about a minute.
      </p>
      {error && <p className="pk-error" role="alert">{error.message || 'Something went wrong. Try again.'}</p>}
      <div className="qs-actions">
        <PButton disabled={busy} onClick={onStart}>Start</PButton>
        <PButton variant="text" disabled={busy} onClick={onLater}>Later</PButton>
      </div>
    </Dialog>
  );
}

export function effectWords(r) {
  if (!r) return '';
  const a = r.before == null ? '—' : money(r.before, { cents: true });
  const b = r.after == null ? '—' : money(r.after, { cents: true });
  if (r.before != null && r.after != null && Math.abs(r.before - r.after) < 0.005) {
    return `Allowance: ${b}, unchanged`;
  }
  return `Allowance: ${a} → ${b}`;
}

export function rulesWords(n) {
  if (!n) return '';
  return `${n === 1 ? '1 rule' : `${n} rules`} saved, so ${n === 1 ? 'it sorts itself' : 'these sort themselves'} next time.`;
}

/** QS-04. */
export function Done({ r, onDone }) {
  const n = r?.sorted ?? 0;
  return (
    <Dialog labelledBy="qs-title" onClose={onDone} className="qs-dialog">
      <p className="pk-overline accent">All sorted</p>
      <h2 className="pk-h2" id="qs-title">{n === 0 ? 'Nothing sorted this time' : `${n} sorted. Thanks!`}</h2>
      {n > 0 && (
        <div className="qs-effect">
          <p className="qs-effect-figure">{effectWords(r)}</p>
          {r?.reason && <p className="pk-muted">{r.reason}</p>}
        </div>
      )}
      {n === 0 && <p className="pk-muted">Whatever you skipped is still in Needs a look.</p>}
      {rulesWords(r?.rules) && <p>{rulesWords(r.rules)}</p>}
      <div className="qs-actions">
        <PButton onClick={onDone}>Done</PButton>
      </div>
    </Dialog>
  );
}
