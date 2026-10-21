import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActionToast, Choice, PButton, Toast, TxRow, amountTone, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { ErrorNote } from '../components/ui.jsx';
import { DuplicateQuestion } from './Duplicates.jsx';
import Stacked, { Pill, Progress, TxHead as StackedHead } from './Stacked.jsx';
import { depositChoices } from './joint.js';
import {
  INCOME_KINDS, answerDuplicate, dismissReview, getReview, money, setCategory, setIncomeType,
  setJointFrom, skipReview, undoChange,
} from '../api.js';

/**
 * Needs a look (Pearl R-01 to R-13 and TR-01 on the Current design page,
 * 2026-10-20; THL-123, THL-163, THL-213, THL-165).
 *
 * To review (TR-01) lists every transaction Pearl couldn't sort, oldest
 * first, each with the question it will ask. Tapping a row opens that
 * transaction's card (Stacked.jsx): one short question at a time, where
 * tapping an answer is the commit — there is no Save and next. Once the
 * last answer is saved the card becomes the Sorted card: the dots all
 * filled with a pink check and "Sorted", the answers as rows, what it did
 * to her numbers, and a Next button that opens the next transaction in the
 * list. Nothing moves on by itself.
 *
 * Going back: Undo in the card's top-right takes back the last answer (on
 * a Sorted card it undoes the change and reopens the last step). Previous,
 * floating above the card, returns to the transaction sorted before, whose
 * answers can be reopened too. Tapping an answer row on a Sorted card
 * undoes the change and reopens that step in place, with the other answers
 * still visible.
 *
 * Skip for now puts a question in Skipped (THL-213), kept between visits
 * and out of the badge; Skipped sits at the end of the list. At zero, All
 * sorted (R-04): the alert on Transactions and the count in the navigation
 * go too.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const monthName = (month) => MONTHS[Number(month.slice(5, 7)) - 1] ?? month;
const shortDate = (iso) => `${(MONTHS[Number(iso.slice(5, 7)) - 1] ?? '').slice(0, 3)} ${Number(iso.slice(8, 10))}`;

/** Every item in the review, as one queue, oldest first. */
export function queue(data) {
  if (!data) return [];
  const learnable = new Set((data.unsorted?.groups ?? [])
    .filter((g) => g.learnable).flatMap((g) => g.ids));
  const items = [
    ...(data.unsorted?.transfers ?? []).map((t) => ({
      key: `u:${t.id}`, kind: 'unsorted', date: t.date, txn: t, to: t.to || t.merchant,
      learnable: learnable.has(t.id), skipped: !!t.skipped,
    })),
    ...(data.unsure_category ?? []).map((it) => ({ ...it, kind: 'category', date: it.txn.date })),
    ...(data.money_in ?? []).map((it) => ({ ...it, kind: 'money_in', date: it.txn.date })),
    ...(data.joint_in ?? []).map((it) => ({ ...it, kind: 'joint_in', date: it.txn.date })),
    // R-09: an e-Transfer in with no name from the bank.
    ...(data.who_sent ?? []).map((it) => ({ ...it, kind: 'who_sent', date: it.txn.date })),
    ...(data.income_type ?? []).map((it) => ({ ...it, kind: 'income', date: it.txn.date })),
    ...(data.three_pay_month ?? []).map((it) => ({ ...it, kind: 'pay3', date: `${it.month}-28` })),
    // THL-165 D-02: the same purchase from two places.
    ...(data.duplicate ?? []).map((it) => ({ ...it, kind: 'duplicate', date: it.txn.date })),
  ];
  return items.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

// The chips over the queue, in this order; a type with nothing shows none.
export const KIND_LABELS = {
  unsorted: 'Where it went', category: 'Categories', money_in: 'Money in',
  joint_in: 'Joint deposits', who_sent: 'Who sent it', income: 'Income', pay3: 'Paycheques',
  duplicate: 'Duplicates',
};

/** What a skipped question is about, in a line (R-06). */
export function skippedLine(it) {
  switch (it.kind) {
    case 'unsorted': return 'Where did this go? Counted as spending until you answer';
    case 'category': return `Pearl guessed ${it.guess}`;
    case 'money_in': return 'What was this money? Not counted as income yet';
    case 'joint_in': return 'Who put this in? Pearl isn’t counting it yet';
    case 'who_sent': return 'Who sent this? Your bank didn’t say';
    case 'income': return `Pearl guessed ${it.guess_label || it.guess}`;
    case 'pay3': return 'A month with a third paycheque';
    case 'duplicate': return 'Is this the same purchase? Counted once until you answer';
    default: return '';
  }
}

/** The question a row will ask, for the chip on To review (TR-01). */
export function questionLabel(it) {
  switch (it.kind) {
    case 'unsorted': return 'Where did this go?';
    case 'category': return it.guess && it.guess !== 'Other' ? `Is this ${categoryLabel(it.guess)}?` : 'What was this?';
    case 'money_in': return it.guess?.action === 'split' ? 'Paid back to you?' : 'Is this income?';
    case 'joint_in': return 'Who put this in?';
    case 'who_sent': return 'Who sent this?';
    case 'income': return 'What kind of income?';
    case 'pay3': return 'A third paycheque';
    case 'duplicate': return 'Same purchase?';
    default: return 'Needs a look';
  }
}

/** The chips: All, each type with questions not skipped, then Skipped. */
export function chips(items) {
  const open = items.filter((i) => !i.skipped);
  const out = [{ key: 'all', label: 'All', count: open.length }];
  for (const [kind, label] of Object.entries(KIND_LABELS)) {
    const n = open.filter((i) => i.kind === kind).length;
    if (n) out.push({ key: kind, label, count: n });
  }
  const held = items.length - open.length;
  if (held) out.push({ key: 'skipped', label: 'Skipped', count: held });
  return out;
}

/** What a chip shows. */
export function inView(items, filter) {
  if (filter === 'skipped') return items.filter((i) => i.skipped);
  return items.filter((i) => !i.skipped && (filter === 'all' || i.kind === filter));
}

// The kinds asked as stacked steps (R-07 to R-12); a duplicate and a
// month with three paycheques keep their own one-step cards.
export const STACKED = new Set(['unsorted', 'category', 'money_in', 'income', 'joint_in', 'who_sent']);

export const minutes = (n) => (n <= 4 ? 'about a minute' : `about ${Math.ceil((n * 15) / 60)} minutes`);

export default function NeedsALook({ categories, onChanged, onTab, onQuickSort, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // The transaction open in its card, by key; null is the list (TR-01).
  const [currentKey, setCurrentKey] = useState(null);
  // The Sorted card for the current transaction, once its last answer is saved.
  const [sorted, setSorted] = useState(null);
  // Transactions sorted this visit, oldest first, for Previous.
  const [log, setLog] = useState([]);
  // Looking back at an earlier Sorted card (an index into `log`), if any.
  const [back, setBack] = useState(null);
  // A step being reopened after its change was undone: the answers to
  // restore and which one is open.
  const [resume, setResume] = useState(null);
  const [change, setChange] = useState(null);
  const [toast, setToast] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await getReview());
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { load(); }, [load, version]);

  const items = useMemo(() => queue(data), [data]);
  const open = useMemo(() => items.filter((i) => !i.skipped), [items]);
  const skipped = useMemo(() => items.filter((i) => i.skipped), [items]);
  const current = currentKey ? items.find((i) => i.key === currentKey) ?? null : null;
  const position = current ? Math.max(1, open.indexOf(current) + 1) : 0;
  const count = data?.count ?? 0;

  // A transaction that is no longer in the queue (sorted elsewhere, or gone)
  // sends her back to the list, unless its Sorted card is up.
  useEffect(() => {
    if (currentKey && data && !current && !sorted && !resume) setCurrentKey(null);
  }, [currentKey, data, current, sorted, resume]);

  async function act(fn, makeChange) {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      const what = makeChange?.(res);
      if (what && typeof what === 'object') { setToast(''); setChange(what); }
      else { setChange(null); setToast(what || 'Saved'); }
      await load();
      onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  /** The last answer's call, then the Sorted card (R-13). */
  async function commit(fn, { answers = [], effect = '' } = {}) {
    setBusy(true);
    setError(null);
    try {
      const out = await fn();
      const entry = {
        key: current.key, it: current, answers,
        title: out?.title || 'Sorted.', detail: out?.detail || effect || '', undo: out?.undo,
        // Where Next goes: the transaction after this one in the list.
        nextKey: open[open.indexOf(current) + 1]?.key ?? null,
      };
      setSorted(entry);
      setResume(null);
      setLog((l) => [...l.filter((e) => e.key !== entry.key), entry]);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  /** Next on a Sorted card: the next transaction, or the end. */
  const next = () => {
    const to = sorted?.nextKey && open.find((i) => i.key === sorted.nextKey) ? sorted.nextKey
      : open.find((i) => i.key !== sorted?.key)?.key ?? null;
    setSorted(null);
    setBack(null);
    setCurrentKey(to);
  };

  /** Undo a Sorted card's change and reopen its step `i` (or the last one). */
  const reopen = async (entry, i = entry.answers.length - 1) => {
    setBusy(true);
    setError(null);
    try {
      if (entry.undo) await undoChange(entry.undo);
      setLog((l) => l.filter((e) => e.key !== entry.key));
      setSorted(null);
      setBack(null);
      const last = entry.answers[entry.answers.length - 1];
      setResume({ key: entry.key, path: entry.answers.slice(0, -1), edit: i < entry.answers.length - 1 ? i : null,
                  name: last?.step === 'who_to' || last?.step === 'name' ? last.label : '' });
      setCurrentKey(entry.key);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    const what = change;
    setChange(null);
    try {
      await undoChange(what.undo);
      setToast('Undone');
      await load();
      onChanged?.();
    } catch (e) {
      setError(e);
    }
  };
  // In the queue, Skip for now puts it in Skipped and opens the next one.
  const skip = () => {
    const to = open[open.indexOf(current) + 1]?.key ?? null;
    act(() => skipReview(current.key), () => 'Moved to Skipped').then(() => setCurrentKey(to));
  };
  const unskip = (key) => act(() => skipReview(key, false), () => 'Back in the queue');
  const openItem = (key) => { setSorted(null); setBack(null); setResume(null); setCurrentKey(key); };
  const toList = () => { setSorted(null); setBack(null); setResume(null); setCurrentKey(null); };

  if (!data && !error) return <div className="pk nl-page"><p className="pk-muted">Loading…</p></div>;

  const backLink = (label, onClick) => (
    <button type="button" className="pk-back" onClick={onClick}>
      <PIcon name="arrowLeft" size={16} /> {label}
    </button>
  );

  // ── To review (TR-01) ────────────────────────────────────────────────
  if (!current && !sorted && back === null) {
    return (
      <div className="pk nl-page">
        <header className="nl-head nl-list-head">
          {backLink('Transactions', () => onTab?.('transactions'))}
          <div className="nl-list-title">
            <div>
              <p className="pk-overline accent">
                {count === 0 ? 'Nothing needs a look' : `${count} need${count === 1 ? 's' : ''} a look · ${minutes(count)}`}
              </p>
              <h1 className="pk-h1">To review</h1>
            </div>
            {open.length > 1 && onQuickSort && (
              <PButton className="nl-quick" onClick={onQuickSort}>{`Quick sort all ${open.length}`}</PButton>
            )}
          </div>
        </header>

        {error && <ErrorNote error={error} onRetry={load} />}

        {data && count === 0 && !skipped.length && (
          <section className="nl-card nl-empty" aria-label="All sorted">
            <span className="nl-empty-icon" aria-hidden="true"><PIcon name="check" size={28} /></span>
            <h2 className="pk-h2">All sorted</h2>
            <p className="pk-muted">Your numbers are up to date. We’ll let you know when something
              new needs a look.</p>
            <PButton className="nl-empty-btn" onClick={() => onTab?.('transactions')}>Back to transactions</PButton>
          </section>
        )}

        {open.length > 0 && (
          <section className="pk-list nl-list" aria-label="To review">
            <p className="pk-muted nl-hint">Tap one to sort it. Pearl asks a question or two, then moves to the next.</p>
            {open.map((it) => <ReviewRow key={it.key} it={it} onOpen={() => openItem(it.key)} />)}
          </section>
        )}

        {skipped.length > 0 && (
          <section className="nl-card nl-skipped" aria-label="Skipped for now">
            <h2 className="pk-h2">Skipped for now</h2>
            <p className="pk-muted">These stay here between visits and count the way Pearl guessed
              until you answer.</p>
            {skipped.map((it) => (
              <div key={it.key} className="nl-skip-card">
                {it.txn ? <TxHead txn={it.txn} compact /> : (
                  <p className="pk-h3">{monthName(it.month)} had three paycheques</p>
                )}
                <p>{skippedLine(it)}</p>
                <div className="nl-skip-actions">
                  <PButton variant="secondary" disabled={busy} onClick={() => openItem(it.key)}>
                    Answer
                  </PButton>
                  <PButton variant="text" disabled={busy} onClick={() => unskip(it.key)}>
                    Back to the queue
                  </PButton>
                </div>
              </div>
            ))}
          </section>
        )}
        {toast && !change && <Toast onDone={() => setToast('')}>{toast}</Toast>}
      </div>
    );
  }

  // ── One transaction: its question, or its Sorted card ────────────────
  const entry = back !== null ? log[back] : sorted;
  const showing = entry ?? current;
  const n = entry ? Math.max(1, open.findIndex((i) => i.key === entry.key) + 1) || position : position;
  const total = open.length + (entry && !open.some((i) => i.key === entry.key) ? 1 : 0);
  const prevIndex = back !== null ? back - 1 : log.length - 1 - (sorted ? 1 : 0);
  const hasPrevious = prevIndex >= 0 && !!log[prevIndex];

  return (
    <div className="pk nl-page">
      <header className="nl-head">
        {backLink('To review', toList)}
        <h1 className="pk-h1">
          {total === 0 ? 'Nothing needs a look'
            : `${total} transaction${total === 1 ? '' : 's'} need${total === 1 ? 's' : ''} a look`}
        </h1>
        {showing && <p className="pk-label pk-muted">{Math.min(n, Math.max(total, 1))} of {Math.max(total, 1)} · {minutes(Math.max(total, 1))}</p>}
      </header>

      {error && <ErrorNote error={error} onRetry={load} />}

      {!current && !entry && (
        <section className="nl-card nl-empty" aria-label="All sorted">
          <span className="nl-empty-icon" aria-hidden="true"><PIcon name="check" size={28} /></span>
          <h2 className="pk-h2">All sorted</h2>
          <p className="pk-muted">Your numbers are up to date. We’ll let you know when something
            new needs a look.</p>
          <PButton className="nl-empty-btn" onClick={() => onTab?.('transactions')}>Back to transactions</PButton>
        </section>
      )}

      {showing && (
        <div className="nl-stage">
          {hasPrevious && (
            <div className="nl-above">
              <Pill className="nl-previous" disabled={busy} onClick={() => { setBack(prevIndex); }}
                    aria-label="Previous transaction">
                Previous
              </Pill>
            </div>
          )}
          <section className="nl-card nl-stack" aria-label={entry ? 'Sorted' : 'Question'}
                   key={entry ? `s-${entry.key}-${back}` : `q-${current.key}-${resume?.key === current.key ? 'r' : 'q'}`}>
            {entry ? (
              <SortedCard entry={entry} busy={busy} isPast={back !== null}
                          onNext={back !== null ? () => setBack(null) : next}
                          onUndo={() => reopen(entry)}
                          onReopen={(i) => reopen(entry, i)} />
            ) : STACKED.has(current.kind) ? (
              <Stacked it={current} categories={categories} busy={busy} onSkip={skip}
                       act={act} commit={commit} onBack={toList} onTab={onTab}
                       initialPath={resume?.key === current.key ? resume.path : null}
                       initialEdit={resume?.key === current.key ? resume.edit : null}
                       initialName={resume?.key === current.key ? resume.name : ''} />
            ) : (
              <Question it={current} categories={categories} busy={busy} onSkip={skip}
                        act={act} commit={commit} onBack={toList} />
            )}
            {current && !entry && current.skipped && (
              <PButton variant="text" className="nl-unskip" disabled={busy} onClick={() => unskip(current.key)}>
                Back to the queue
              </PButton>
            )}
          </section>
        </div>
      )}

      {change && (
        <ActionToast title={change.title} detail={change.detail}
                     onUndo={change.undo ? undo : undefined} onDone={() => setChange(null)} />
      )}
      {toast && !change && <Toast onDone={() => setToast('')}>{toast}</Toast>}
    </div>
  );
}

/** A row on To review: the transaction and the question it will ask. */
function ReviewRow({ it, onOpen }) {
  if (!it.txn) {
    return (
      <button type="button" className="pk-row nl-row" onClick={onOpen}>
        <span className="pk-row-text">
          <span className="pk-row-name">{monthName(it.month)} had three paycheques</span>
          <span className="pk-row-meta">{questionLabel(it)}</span>
        </span>
      </button>
    );
  }
  const inflow = it.txn.amount < 0;
  return (
    <TxRow name={it.txn.merchant} logo={it.txn.logo} onOpen={onOpen}
           meta={[it.txn.account_name, shortDate(it.txn.date)].filter(Boolean).join(' · ')}
           chip={{ label: questionLabel(it), suggested: true }}
           amount={Math.abs(it.txn.amount)} inflow={inflow} />
  );
}

/**
 * The Sorted card (R-13): every dot filled with "✓ Sorted", the answers as
 * rows (tap one to reopen that step), what the change did, and Next.
 */
export function SortedCard({ entry, busy = false, isPast = false, onNext, onUndo, onReopen }) {
  const { it, answers } = entry;
  const name = it.to;
  return (
    <>
      {it.txn ? <StackedHead txn={it.txn} name={name} /> : (
        <p className="pk-h3">{monthName(it.month)} had three paycheques</p>
      )}
      <Progress done={answers.length} total={Math.max(answers.length, 1)} sorted
                trailing={<Pill className="nl-undo" disabled={busy} onClick={onUndo} aria-label="Undo this change">Undo</Pill>} />
      {answers.length > 0 && (
        <div className="nl-done-list">
          {answers.map((a, i) => (
            <button key={`${a.step ?? i}-${i}`} type="button" className="nl-done" disabled={busy}
                    aria-label={`Change: ${a.label ?? a.v}`} onClick={() => onReopen?.(i)}>
              <span className="nl-done-ring" aria-hidden="true" />
              <span className="nl-done-label">{a.label ?? a.v}</span>
            </button>
          ))}
        </div>
      )}
      {(entry.detail || entry.title) && (
        <p className="nl-effect" role="status">{entry.detail || entry.title}</p>
      )}
      <div className="nl-actions nl-next">
        <PButton disabled={busy} onClick={onNext}>{isPast ? 'Back to where I was' : 'Next'} <PIcon name="chevronRight" size={16} /></PButton>
      </div>
    </>
  );
}

/** The transaction a question is about, compact, for Skipped. */
function TxHead({ txn, name }) {
  const inflow = txn.amount < 0;
  return (
    <div className="nl-tx compact">
      <div className="nl-tx-text">
        <span>{txn.merchant}</span>
        <span className="pk-label pk-muted">
          {shortDate(txn.date)}{txn.account_name ? ` · ${txn.account_name}` : ''}
        </span>
      </div>
      <span className={`pk-h2 nl-tx-amt ${amountTone(inflow)}`}>
        {txAmount(Math.abs(txn.amount), { inflow, signed: true })}
      </span>
    </div>
  );
}

/** The one-step questions: a duplicate (D-02) and a third paycheque. */
function Question({ it, busy, onSkip, act, commit, onBack }) {
  if (it.kind === 'duplicate') {
    return (
      <>
        <StackedHead txn={it.txn} />
        <Progress done={0} total={1}
                  trailing={<Pill className="nl-undo" disabled={busy} onClick={onBack} aria-label="Back to the list">Undo</Pill>} />
        <DuplicateQuestion it={it} busy={busy} onSkip={onSkip}
                           onAnswer={(answer) => commit(() => answerDuplicate(it.txn.id, answer)
                             .then((res) => ({ title: res?.title, detail: res?.detail, undo: res?.undo })),
                           { answers: [{ step: 'dup', v: answer,
                                         label: answer === 'same' ? 'Same purchase · kept one' : 'Two different purchases' }] })} />
      </>
    );
  }
  return (
    <>
      <div className="nl-corner">
        <Pill className="nl-undo" disabled={busy} onClick={onBack} aria-label="Back to the list">Undo</Pill>
      </div>
      <h2 className="pk-h2">{monthName(it.month)} had three paycheques</h2>
      <p className="pk-muted">{it.reason}
        {it.monthly ? ` That’s ${money(it.monthly)} a month from ${money(it.paycheque)} paycheques.` : ''}</p>
      <div className="nl-actions">
        <PButton disabled={busy} onClick={() => act(() => dismissReview(it.key)).then(onBack)}>Got it</PButton>
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
      </div>
    </>
  );
}

/** What kind of income — or, when it isn't income at all, what it is
 * (2026-10-14): her own money, money she lent coming back, or any category.
 * Kept for the transaction panel; Needs a look asks it as stacked steps. */
export function IncomeKind({ it, categories = [], busy, onSkip, act, sorted }) {
  const [kind, setKind] = useState(it.guess);
  const [cat, setCat] = useState('');
  const others = useMemo(() => groupCategories(categories, {
    only: (c) => c.name !== 'Income',
  }), [categories]);
  const name = `inc-${it.txn.id}`;
  const ready = !!kind && (kind !== 'not:else' || !!cat);
  const save = () => {
    if (kind === 'not:own') {
      return act(() => setCategory(it.txn.id, 'Transfers'), sorted('Sorted as your own money, not income.'));
    }
    if (kind === 'not:lent') {
      return act(() => setCategory(it.txn.id, 'Lent'), sorted('Sorted as money you lent.'));
    }
    if (kind === 'not:savings') {
      return act(() => setCategory(it.txn.id, 'Saved'), sorted('Sorted as taken out of savings.'));
    }
    if (kind === 'not:else') {
      return act(() => setCategory(it.txn.id, cat), sorted(`Sorted as ${categoryLabel(cat)}.`));
    }
    return act(() => setIncomeType(it.txn.id, kind));
  };
  return (
    <>
      <StackedHead txn={it.txn} />
      <h2 className="pk-h2">What kind of income is this?</h2>
      <div className="pk-choices nl-grid" role="radiogroup" aria-label="What kind of income is this?">
        {Object.entries(INCOME_KINDS).map(([k, label]) => (
          <Choice key={k} name={name} checked={kind === k} onChange={() => setKind(k)} label={label} />
        ))}
      </div>
      <p className="pk-overline">Or it isn’t income</p>
      <div className="pk-choices" role="radiogroup" aria-label="It isn’t income">
        <Choice name={name} checked={kind === 'not:own'} onChange={() => setKind('not:own')}
                label="My own money" description="Moves it to Transfers" />
        <Choice name={name} checked={kind === 'not:lent'} onChange={() => setKind('not:lent')}
                label="Paying back money I lent" description="Moves it to Lent" />
        <Choice name={name} checked={kind === 'not:savings'} onChange={() => setKind('not:savings')}
                label="Taken out of my savings" description="Counts against Savings this month" />
        <Choice name={name} checked={kind === 'not:else'} onChange={() => setKind('not:else')}
                label="Something else" description="Pick any category, like a refund" />
      </div>
      {kind === 'not:else' && (
        <div className="nl-spent">
          <p className="pk-label">What was it?</p>
          <CategoryChips groups={others} value={cat} onChange={setCat} label="What was it?" />
        </div>
      )}
      {kind?.startsWith('not:') && (
        <p className="nl-effect" role="status">
          {`It stops counting as income, so Allowance goes down by ${txAmount(Math.abs(it.txn.amount))}.`}
        </p>
      )}
      <div className="nl-actions">
        <PButton disabled={busy || !ready} onClick={save}>Save</PButton>
        {onSkip && <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>}
      </div>
    </>
  );
}

/** Money into a joint account from outside Pearl: hers, or which of theirs?
 * Kept for the transaction panel; Needs a look asks it as a stacked step. */
export function JointIn({ it, busy, onSkip, act, onTab }) {
  const [pick, setPick] = useState('');
  const [remember, setRemember] = useState(true);
  const name = `joint-${it.txn.id}`;
  const choices = depositChoices(it.people, it.label);
  const chosen = choices.find((c) => c.value === pick);
  return (
    <>
      <StackedHead txn={it.txn} />
      <h2 className="pk-h2">Who put this in?</h2>
      <p className="pk-muted">Money into your joint account from outside Pearl. Until you answer, it
        counts as nothing.</p>
      <Choice type="checkbox" checked={remember} onChange={setRemember}
              label={`The same for every deposit from ${it.txn.merchant} on this account`} />
      <div className="pk-choices" role="radiogroup" aria-label="Who put this in?">
        {choices.map((c) => (
          <Choice key={c.value} name={name} checked={pick === c.value}
                  onChange={() => setPick(c.value)} label={c.label} description={c.description} />
        ))}
      </div>
      {onTab && (
        <button type="button" className="txd-link nl-other" onClick={() => onTab('accounts')}>
          Add or change who you share it with <PIcon name="chevronRight" size={14} />
        </button>
      )}
      <div className="nl-actions">
        <PButton disabled={busy || !chosen}
                 onClick={() => act(() => setJointFrom(it.txn.id, chosen.who, remember, chosen.person))}>
          Save
        </PButton>
        {onSkip && <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>}
      </div>
    </>
  );
}
