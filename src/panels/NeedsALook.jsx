import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActionToast, Avatar, Choice, PButton, Toast, amountTone, txAmount,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import CategoryPicker, { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { ErrorNote } from '../components/ui.jsx';
import { RepaymentMatch } from './Splits.jsx';
import { DuplicateQuestion } from './Duplicates.jsx';
import { depositChoices } from './joint.js';
import WhatWasThis from './WhatWasThis.jsx';
import {
  INCOME_KINDS, answerDuplicate, confirmTx, dismissReview, getReview, getTxCases, linkPayback,
  markTx, money, setCategory, setIncomeType, setJointFrom, setParty, skipReview, sortTransfers,
  undoChange,
} from '../api.js';

/**
 * Needs a look (Pearl R-01 and R-04, THL-123; THL-163 for transfers).
 *
 * Everything Pearl isn't sure about, one question at a time, oldest first,
 * so the queue takes about a minute: where a transfer went, a category Pearl
 * guessed, money that came in, a kind of income, a month with a third
 * paycheque, the same purchase from two places (THL-165 D-02). Beside each
 * question, why Pearl asks. Answering moves to the next. Skip for now puts
 * it in Skipped (THL-213), kept between visits and out of the badge; chips
 * filter the queue by type, and Skipped has Back to the queue. A change
 * that moves safe to spend says by how much, with Undo (R-03).
 *
 * At zero, All sorted (R-04): the alert on Transactions and the count in the
 * navigation go too.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function longDate(iso) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[m - 1]} ${d}`
    + (y !== new Date().getFullYear() ? `, ${y}` : '');
}

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

// Why Pearl asks, beside each kind of question.
const WHY = {
  unsorted: ['Until it’s sorted, we count it as spending.',
    'So your safe to spend may be a little low right now. Sorting it keeps your numbers right.'],
  category: ['A wrong category moves your numbers.',
    'Your budgets and your usual month are worked out by category.'],
  money_in: ['Money in isn’t income until you say so.',
    'If a friend paid you back, it comes off what you spent instead. Nothing counts twice.'],
  joint_in: ['Until you answer, it counts as nothing.',
    'So your spending on the joint account isn’t over- or under-counted.'],
  who_sent: ['A name makes paybacks easy to match.',
    'Pearl uses it to link this to a purchase you paid for someone.'],
  income: ['We ask so your income is right.',
    'Money that isn’t income would make safe to spend look bigger than it is.'],
  pay3: ['Two months a year hold a third paycheque.',
    'Your plan uses a typical month, so the extra one is yours to put somewhere.'],
  duplicate: ['Until you decide, we count it once.',
    'The same amount came in from two places on the same day. We’d rather check than count it twice.'],
};

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

const minutes = (n) => (n <= 4 ? 'about a minute' : `about ${Math.ceil((n * 15) / 60)} minutes`);

export default function NeedsALook({ categories, onChanged, onTab, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('all');
  // Passed over in this visit, within Skipped (Skip for now there moves on).
  const [passed, setPassed] = useState(() => new Set());
  // R-06: the skipped question she chose to answer, from the list.
  const [answering, setAnswering] = useState(null);
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
  const shown = useMemo(() => inView(items, filter), [items, filter]);
  const current = filter === 'skipped'
    ? shown.find((i) => i.key === answering) ?? null
    : shown.find((i) => !passed.has(i.key));
  const position = current ? shown.indexOf(current) + 1 : 0;
  // A chip whose questions are all answered falls back to All.
  useEffect(() => {
    if (filter !== 'all' && data && !chips(items).some((c) => c.key === filter)) setFilter('all');
  }, [items, filter, data]);

  async function act(fn, makeChange) {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      const what = makeChange?.(res);
      if (what && typeof what === 'object') { setToast(''); setChange(what); }
      else { setChange(null); setToast(what || 'Saved'); }
      setAnswering(null);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const sorted = (title) => (res) => ({
    title: [title, res?.impact?.title].filter(Boolean).join(' '),
    detail: res?.impact?.detail ?? '',
    undo: res?.undo,
  });
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
  // In the queue, Skip for now puts it in Skipped; in Skipped, it moves on.
  const skip = () => {
    if (current.skipped) { setAnswering(null); return; }
    act(() => skipReview(current.key), () => 'Moved to Skipped');
  };
  const unskip = (key = current?.key) => act(() => skipReview(key, false), () => 'Back in the queue');
  const pick = (key) => { setFilter(key); setPassed(new Set()); setAnswering(null); };
  const tabs = chips(items);

  if (!data && !error) return <div className="pk nl-page"><p className="pk-muted">Loading…</p></div>;

  const back = (
    <button type="button" className="pk-back" onClick={() => onTab?.('transactions')}>
      <PIcon name="arrowLeft" size={16} /> Transactions
    </button>
  );
  const count = data?.count ?? 0;

  return (
    <div className="pk nl-page">
      <header className="nl-head">
        {back}
        <h1 className="pk-h1">
          {count === 0 ? 'Nothing needs a look'
            : `${count} transaction${count === 1 ? '' : 's'} need${count === 1 ? 's' : ''} a look`}
        </h1>
        {current && (
          <p className="pk-label pk-muted">{position} of {shown.length} · {minutes(shown.length)}</p>
        )}
      </header>

      {error && <ErrorNote error={error} onRetry={load} />}

      {tabs.length > 1 && (
        <nav className="nl-chips" aria-label="Filter by type">
          {tabs.map((c) => (
            <button key={c.key} type="button" aria-pressed={filter === c.key}
                    className={`pk-filter nl-chip${filter === c.key ? ' active' : ''}`} onClick={() => pick(c.key)}>
              {c.label} ({c.count})
            </button>
          ))}
        </nav>
      )}
      {filter === 'skipped' && !current && shown.length > 0 && (
        <section className="nl-card nl-skipped" aria-label="Skipped for now">
          <h2 className="pk-h2">Skipped for now</h2>
          <p className="pk-muted">These stay here between visits and count the way Pearl guessed
            until you answer.</p>
          {shown.map((it) => (
            <div key={it.key} className="nl-skip-card">
              {it.txn ? <TxHead txn={it.txn} compact /> : (
                <p className="pk-h3">{monthName(it.month)} had three paycheques</p>
              )}
              <p>{skippedLine(it)}</p>
              <div className="nl-skip-actions">
                <PButton variant="secondary" disabled={busy} onClick={() => setAnswering(it.key)}>
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

      {data && count === 0 && !data.skipped && (
        <section className="nl-card nl-empty" aria-label="All sorted">
          <span className="nl-empty-icon" aria-hidden="true"><PIcon name="check" size={28} /></span>
          <h2 className="pk-h2">All sorted</h2>
          <p className="pk-muted">Your numbers are up to date. We’ll let you know when something
            new needs a look.</p>
          <PButton className="nl-empty-btn" onClick={() => onTab?.('today')}>Back to Home</PButton>
        </section>
      )}

      {data && (count > 0 || data.skipped > 0) && !current && filter !== 'skipped' && (
        <section className="nl-card nl-empty" aria-label="Skipped">
          <h2 className="pk-h2">That’s everything for now</h2>
          {data.skipped > 0 && (
            <p className="pk-muted">{data.skipped} skipped. {data.skipped === 1 ? 'It counts' : 'They count'} the
              way Pearl guessed until you answer.</p>
          )}
          {data.skipped > 0 && (
            <PButton className="nl-empty-btn" onClick={() => pick('skipped')}>
              Go through skipped
            </PButton>
          )}
          <PButton variant="text" onClick={() => onTab?.('transactions')}>Back to transactions</PButton>
        </section>
      )}

      {current && (
        <div className="nl-cols">
          <section className="nl-card" aria-label="Question" key={current.key}>
            <Question it={current} categories={categories} busy={busy} onSkip={skip}
                      act={act} sorted={sorted} onTab={onTab} />
            {current.skipped && (
              <PButton variant="text" className="nl-unskip" disabled={busy} onClick={() => unskip()}>
                Back to the queue
              </PButton>
            )}
          </section>
          <aside className="nl-why" aria-label="Why we ask">
            <p className="pk-overline accent">Why we ask</p>
            <p className="pk-h3">{WHY[current.kind][0]}</p>
            <p className="pk-muted">{current.reason && current.kind !== 'pay3'
              ? current.reason : WHY[current.kind][1]}</p>
          </aside>
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

/** The transaction a question is about: who, when, from where, how much. */
function TxHead({ txn, name, compact = false }) {
  const inflow = txn.amount < 0;
  return (
    <div className={`nl-tx${compact ? ' compact' : ''}`}>
      {!compact && <Avatar name={name || txn.merchant} logo={txn.logo} />}
      <div className="nl-tx-text">
        <span>{txn.merchant}</span>
        <span className="pk-label pk-muted">
          {compact ? shortDate(txn.date) : longDate(txn.date)}
          {txn.account_name ? ` · ${compact ? '' : inflow ? 'to ' : 'from '}${txn.account_name}` : ''}
        </span>
      </div>
      <span className={`pk-h2 nl-tx-amt ${amountTone(inflow)}`}>
        {txAmount(Math.abs(txn.amount), { inflow, signed: true })}
      </span>
    </div>
  );
}

function Actions({ busy, ready, onSave, onSkip, label = 'Save and next' }) {
  return (
    <div className="nl-actions">
      <PButton disabled={busy || !ready} onClick={onSave}>{label}</PButton>
      <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
    </div>
  );
}

function Question({ it, categories, busy, onSkip, act, sorted, onTab }) {
  switch (it.kind) {
    case 'unsorted':
      return <WhereDidThisGo it={it} categories={categories} busy={busy} onSkip={onSkip}
                             act={act} sorted={sorted} />;
    case 'category':
      return <CategoryQuestion it={it} categories={categories} busy={busy} onSkip={onSkip}
                               act={act} sorted={sorted} />;
    case 'money_in':
      return <MoneyIn it={it} categories={categories} busy={busy} onSkip={onSkip} act={act}
                      sorted={sorted} />;
    case 'duplicate':
      // D-02 → D-03: the toast says what it did to her numbers, with Undo.
      return (
        <DuplicateQuestion it={it} busy={busy} onSkip={onSkip}
                           onAnswer={(answer) => act(() => answerDuplicate(it.txn.id, answer),
                                                     (res) => ({ title: res.title,
                                                                 detail: res.detail,
                                                                 undo: res.undo }))} />
      );
    case 'income':
      return <IncomeKind it={it} categories={categories} busy={busy} onSkip={onSkip} act={act}
                         sorted={sorted} />;
    case 'joint_in':
      return <JointIn it={it} busy={busy} onSkip={onSkip} act={act} onTab={onTab} />;
    case 'who_sent':
      return <WhoSent it={it} busy={busy} onSkip={onSkip} act={act} />;
    default:
      return (
        <>
          <h2 className="pk-h2">{monthName(it.month)} had three paycheques</h2>
          <p className="pk-muted">{it.reason}
            {it.monthly ? ` That’s ${money(it.monthly)} a month from ${money(it.paycheque)} paycheques.` : ''}</p>
          <Actions busy={busy} ready label="Got it" onSkip={onSkip}
                   onSave={() => act(() => dismissReview(it.key))} />
        </>
      );
  }
}

/**
 * Is this Groceries? (R-02) — or, when it wasn't a purchase at all, the one
 * "What was this?" sheet (2026-10-14), with every case.
 */
function CategoryQuestion({ it, categories, busy, onSkip, act, sorted }) {
  const [sheet, setSheet] = useState(false);
  if (sheet) {
    return (
      <>
        <TxHead txn={it.txn} />
        <h2 className="pk-h2">What was this?</h2>
        <WhatWasThis tx={{ id: it.txn.id, merchant: it.txn.merchant, amount: Math.abs(it.txn.amount),
                           inflow: it.txn.amount < 0, logo: it.txn.logo }}
                     categories={categories} busy={busy} saveLabel="Save and next" showHead={false}
                     onDone={(res) => act(() => Promise.resolve(res), sorted(res.title))} />
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={() => setSheet(false)}>
          Back to the category
        </PButton>
      </>
    );
  }
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">{it.guess === 'Other' ? 'What was this?' : `Is this ${it.guess}?`}</h2>
      <CategoryPicker tx={{ id: it.txn.id, category: it.guess, merchant: it.txn.merchant,
                            suggested: true }}
                      categories={categories} busy={busy} confirmable saveLabel="Save and next"
                      onSave={(cat, always) => act(
                        () => (cat === it.guess && !always ? confirmTx(it.txn.id)
                          : setCategory(it.txn.id, cat, always)),
                        cat === it.guess && !always ? undefined
                          : sorted(`Moved to ${categoryLabel(cat)}.`),
                      )} />
      <button type="button" className="txd-link nl-other" onClick={() => setSheet(true)}>
        It wasn’t a purchase…
      </button>
      <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>
        Skip for now
      </PButton>
    </>
  );
}

/**
 * Where did this go? (R-01, THL-163): Saved, Spent (and on what), or moved
 * between her own accounts, and "Remember where these go" — a rule for that
 * destination, on by default when Pearl can recognise it next time.
 */
function WhereDidThisGo({ it, categories, busy, onSkip, act, sorted }) {
  const [where, setWhere] = useState('');
  const [cat, setCat] = useState('');
  const [account, setAccount] = useState('');
  const [accounts, setAccounts] = useState(null);
  const [remember, setRemember] = useState(it.learnable);
  const spending = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group),
  }), [categories]);
  // Saved: which savings or investment account it went to (2026-10-14),
  // from the same list the What was this? sheet offers.
  useEffect(() => {
    if (where !== 'saved' || accounts !== null) return undefined;
    let live = true;
    getTxCases(it.txn.id).then((d) => { if (live) setAccounts(d.accounts ?? []); })
      .catch(() => { if (live) setAccounts([]); });
    return () => { live = false; };
  }, [where, accounts, it.txn.id]);
  const kind = /e-?\s?t(ransfe)?r|interac/i.test(`${it.txn.description} ${it.txn.merchant}`)
    ? 'e-Transfers' : 'transfers';
  const category = where === 'saved' ? 'Saved' : where === 'moved' ? 'Transfers' : cat;
  const label = (accounts ?? []).find((a) => a.id === account)?.label;
  const title = where === 'saved' ? (label ? `Put away to ${label}.` : 'Sorted as savings.')
    : where === 'moved' ? 'Sorted as moved between your accounts.'
      : `Sorted as ${category}.`;
  const name = `where-${it.txn.id}`;
  const save = () => {
    const keep = it.learnable && remember;
    if (where === 'saved') {
      return act(() => markTx(it.txn.id, { case: 'saved', account, remember: keep }), sorted(title));
    }
    return act(() => sortTransfers([it.txn.id], category, keep), sorted(title));
  };
  return (
    <>
      <TxHead txn={it.txn} name={it.to} />
      <h2 className="pk-h2">Where did this go?</h2>
      <div className="pk-choices" role="radiogroup" aria-label="Where did this go?">
        <Choice name={name} checked={where === 'saved'} onChange={() => setWhere('saved')}
                label="Saved"
                description="I moved it to savings or an investment account. It won’t count as spending." />
        <Choice name={name} checked={where === 'spent'} onChange={() => setWhere('spent')}
                label="Spent" description="I paid someone for something. It counts as spending." />
        <Choice name={name} checked={where === 'moved'} onChange={() => setWhere('moved')}
                label="Moved between my own accounts"
                description="It won’t count as spending or saving." />
      </div>
      {where === 'saved' && accounts?.length > 0 && (
        <div className="nl-spent">
          <p className="pk-label">Which account did it go to?</p>
          <div className="pk-choices" role="radiogroup" aria-label="Which account?">
            <Choice name={`${name}-acct`} checked={!account} onChange={() => setAccount('')}
                    label="Not sure" />
            {accounts.map((a) => (
              <Choice key={a.id} name={`${name}-acct`} checked={account === a.id}
                      onChange={() => setAccount(a.id)} label={a.label} />
            ))}
          </div>
        </div>
      )}
      {where === 'spent' && (
        <div className="nl-spent">
          <p className="pk-label">What was it for?</p>
          <CategoryChips groups={spending} value={cat} onChange={setCat} label="What was it for?" />
        </div>
      )}
      {it.learnable && (
        <Choice type="checkbox" checked={remember} onChange={setRemember}
                label={`Remember where ${kind} to ${it.to} go`}
                description="We’ll sort the next ones the same way. Change it any time in Profile › Categories and rules." />
      )}
      <Actions busy={busy} ready={!!category} onSkip={onSkip} onSave={save} />
    </>
  );
}

/**
 * Money that came in from somewhere Pearl can't see. When it matches a
 * split someone still owes on, the question is that one (S-02).
 */
function MoneyIn({ it, categories = [], busy, onSkip, act, sorted }) {
  const [other, setOther] = useState(false);
  const match = it.guess?.action === 'split' ? it.guess.split : null;
  if (match && !other) {
    return (
      <>
        <TxHead txn={it.txn} />
        <h2 className="pk-h2">Is {match.name} paying you back for this?</h2>
        <RepaymentMatch match={match} />
        <p className="pk-muted">If you link them, this e-Transfer won’t count as income, and the
          split shows as paid back.</p>
        <div className="nl-actions">
          <PButton disabled={busy}
                   onClick={() => act(() => linkPayback(match.charge_id, it.txn.id, match.name))}>
            Yes, link them
          </PButton>
          <PButton variant="secondary" disabled={busy} onClick={() => setOther(true)}>
            No, it’s something else
          </PButton>
          <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>
            Skip for now
          </PButton>
        </div>
      </>
    );
  }
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">What was this money?</h2>
      <WhatWasThis tx={{ id: it.txn.id, merchant: it.txn.merchant, amount: Math.abs(it.txn.amount),
                         inflow: true, logo: it.txn.logo }}
                   categories={categories} busy={busy} saveLabel="Save and next" showHead={false}
                   onDone={(res) => act(() => Promise.resolve(res), sorted(res.title))} />
      <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>
        Skip for now
      </PButton>
    </>
  );
}

/** What kind of income — or, when it isn't income at all, what it is
 * (2026-10-14): her own money, money she lent coming back, or any category. */
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
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">What kind of income is this?</h2>
      <div className="pk-choices" role="radiogroup" aria-label="What kind of income is this?">
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
          {`It stops counting as income, so safe to spend goes down by ${txAmount(Math.abs(it.txn.amount))}.`}
        </p>
      )}
      <Actions busy={busy} ready={ready} onSkip={onSkip} onSave={save} />
    </>
  );
}

/** Money into a joint account from outside Pearl: hers, or which of theirs? */
export function JointIn({ it, busy, onSkip, act, onTab }) {
  const [pick, setPick] = useState('');
  const [remember, setRemember] = useState(true);
  const name = `joint-${it.txn.id}`;
  const choices = depositChoices(it.people, it.label);
  const chosen = choices.find((c) => c.value === pick);
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">Who put this in?</h2>
      <p className="pk-muted">Money into your joint account from outside Pearl. Until you answer, it
        counts as nothing.</p>
      <div className="pk-choices" role="radiogroup" aria-label="Who put this in?">
        {choices.map((c) => (
          <Choice key={c.value} name={name} checked={pick === c.value}
                  onChange={() => setPick(c.value)} label={c.label} description={c.description} />
        ))}
      </div>
      <Choice type="checkbox" checked={remember} onChange={setRemember}
              label={`The same for every deposit from ${it.txn.merchant} on this account`} />
      {onTab && (
        <button type="button" className="txd-link nl-other" onClick={() => onTab('accounts')}>
          Add or change who you share it with <PIcon name="chevronRight" size={14} />
        </button>
      )}
      <Actions busy={busy} ready={!!chosen} onSkip={onSkip}
               onSave={() => act(() => setJointFrom(it.txn.id, chosen.who, remember, chosen.person))} />
    </>
  );
}

/** Who sent this? (R-09): an e-Transfer the bank didn't name. */
export function WhoSent({ it, busy, onSkip, act }) {
  const [name, setName] = useState('');
  const id = `who-${it.txn.id}`;
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">Who sent this?</h2>
      <p className="pk-muted">Your bank didn’t say. Adding a name helps Pearl match paybacks and
        makes it easy to find.</p>
      <div className="txd-field">
        <label className="pk-label" htmlFor={id}>Their name</label>
        <input id={id} type="text" value={name} maxLength={60} autoComplete="off"
               placeholder="First and last name" onChange={(e) => setName(e.target.value)} />
        <p className="pk-label pk-muted">Shown in your list and search from now on</p>
      </div>
      <button type="button" className="txd-link nl-other" disabled={busy}
              onClick={() => act(() => dismissReview(it.key), () => 'Kept your bank’s name')}>
        Use your bank’s name instead
      </button>
      <Actions busy={busy} ready={!!name.trim()} onSkip={onSkip} label="Save"
               onSave={() => act(() => setParty(it.txn.id, name.trim()), () => 'Saved')} />
    </>
  );
}
