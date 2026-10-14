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
import {
  INCOME_KINDS, answerDuplicate, confirmTx, dismissReview, getReview, linkPayback, money,
  setCategory, setIncomeType, setJointFrom, skipReview, sortTransfers, undoChange,
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
  joint_in: ['Until you say, it counts as nothing.',
    'Your own money isn’t income. What the other person puts in pays for part of your joint spending.'],
  income: ['Your plan is built on your usual pay.',
    'Knowing what kind of income this was keeps a one-off from looking like a raise.'],
  pay3: ['Two months a year hold a third paycheque.',
    'Your plan uses a typical month, so the extra one is yours to put somewhere.'],
  duplicate: ['Until you decide, we count it once.',
    'The same amount came in from two places on the same day. We’d rather check than count it twice.'],
};

// The chips over the queue, in this order; a type with nothing shows none.
export const KIND_LABELS = {
  unsorted: 'Where it went', category: 'Categories', money_in: 'Money in',
  joint_in: 'Joint deposits', income: 'Income', pay3: 'Paycheques', duplicate: 'Duplicates',
};

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
  const current = shown.find((i) => !passed.has(i.key));
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
    if (current.skipped) { setPassed((s) => new Set([...s, current.key])); return; }
    act(() => skipReview(current.key), () => 'Moved to Skipped');
  };
  const unskip = () => act(() => skipReview(current.key, false), () => 'Back in the queue');
  const pick = (key) => { setFilter(key); setPassed(new Set()); };
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
      {filter === 'skipped' && (
        <p className="pk-muted nl-skipped-note">Skipped ones count the way Pearl guessed.</p>
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

      {data && (count > 0 || data.skipped > 0) && !current && (
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
                      act={act} sorted={sorted} />
            {current.skipped && (
              <PButton variant="text" className="nl-unskip" disabled={busy} onClick={unskip}>
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
function TxHead({ txn, name }) {
  const inflow = txn.amount < 0;
  return (
    <div className="nl-tx">
      <Avatar name={name || txn.merchant} logo={txn.logo} />
      <div className="nl-tx-text">
        <span>{txn.merchant}</span>
        <span className="pk-label pk-muted">
          {longDate(txn.date)}{txn.account_name ? ` · ${inflow ? 'to' : 'from'} ${txn.account_name}` : ''}
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

function Question({ it, categories, busy, onSkip, act, sorted }) {
  switch (it.kind) {
    case 'unsorted':
      return <WhereDidThisGo it={it} categories={categories} busy={busy} onSkip={onSkip}
                             act={act} sorted={sorted} />;
    case 'category':
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
          <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>
            Skip for now
          </PButton>
        </>
      );
    case 'money_in':
      return <MoneyIn it={it} busy={busy} onSkip={onSkip} act={act} sorted={sorted} />;
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
      return <IncomeKind it={it} busy={busy} onSkip={onSkip} act={act} />;
    case 'joint_in':
      return <JointIn it={it} busy={busy} onSkip={onSkip} act={act} />;
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
 * Where did this go? (R-01, THL-163): Saved, Spent (and on what), or moved
 * between her own accounts, and "Remember where these go" — a rule for that
 * destination, on by default when Pearl can recognise it next time.
 */
function WhereDidThisGo({ it, categories, busy, onSkip, act, sorted }) {
  const [where, setWhere] = useState('');
  const [cat, setCat] = useState('');
  const [remember, setRemember] = useState(it.learnable);
  const spending = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group),
  }), [categories]);
  const kind = /e-?\s?t(ransfe)?r|interac/i.test(`${it.txn.description} ${it.txn.merchant}`)
    ? 'e-Transfers' : 'transfers';
  const category = where === 'saved' ? 'Saved' : where === 'moved' ? 'Transfers' : cat;
  const title = where === 'saved' ? 'Sorted as savings.'
    : where === 'moved' ? 'Sorted as moved between your accounts.'
      : `Sorted as ${category}.`;
  const name = `where-${it.txn.id}`;
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
      {where === 'spent' && (
        <div className="nl-spent">
          <p className="pk-label">What was it for?</p>
          <CategoryChips groups={spending} value={cat} onChange={setCat} label="What was it for?" />
        </div>
      )}
      {it.learnable && (
        <Choice type="checkbox" checked={remember} onChange={setRemember}
                label={`Remember where ${kind} to ${it.to} go`}
                description="We’ll sort the next ones the same way." />
      )}
      <Actions busy={busy} ready={!!category} onSkip={onSkip}
               onSave={() => act(() => sortTransfers([it.txn.id], category, it.learnable && remember),
                                 sorted(title))} />
    </>
  );
}

/**
 * Money that came in from somewhere Pearl can't see. When it matches a
 * split someone still owes on, the question is that one (S-02).
 */
function MoneyIn({ it, busy, onSkip, act, sorted }) {
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
  return <MoneyInChoices it={it} busy={busy} onSkip={onSkip} act={act} sorted={sorted} />;
}

function MoneyInChoices({ it, busy, onSkip, act, sorted }) {
  const likely = it.guess?.action === 'payback' && it.candidates?.[0]?.likely
    ? `pb:${it.guess.charge.id}` : '';
  const [pick, setPick] = useState(likely);
  const name = `in-${it.txn.id}`;
  const run = () => {
    if (pick.startsWith('pb:')) {
      const charge = it.candidates.find((c) => `pb:${c.id}` === pick);
      return act(() => linkPayback(charge.id, it.txn.id));
    }
    if (pick === 'own') return act(() => dismissReview(it.key));
    if (pick === 'gift') return act(() => setIncomeType(it.txn.id, 'gifts'));
    return act(() => setCategory(it.txn.id, 'Lent'), sorted('Sorted as money you lent.'));
  };
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">What was this money?</h2>
      <div className="pk-choices" role="radiogroup" aria-label="What was this money?">
        {(it.candidates ?? []).slice(0, 3).map((c) => (
          <Choice key={c.id} name={name} checked={pick === `pb:${c.id}`}
                  onChange={() => setPick(`pb:${c.id}`)}
                  label={`Paying me back for ${c.merchant}`}
                  description={`${longDate(c.date)} · ${money(c.amount, { cents: true })}, about a 1/${c.split} share. Not income.`} />
        ))}
        <Choice name={name} checked={pick === 'own'} onChange={() => setPick('own')}
                label="My own money" description="From an account Pearl can’t see. It won’t count as income." />
        <Choice name={name} checked={pick === 'gift'} onChange={() => setPick('gift')}
                label="A gift" description="It counts as income." />
        <Choice name={name} checked={pick === 'lent'} onChange={() => setPick('lent')}
                label="Paying back money I lent" description="Not income: it was yours before." />
      </div>
      <Actions busy={busy} ready={!!pick} onSkip={onSkip} onSave={run} />
    </>
  );
}

function IncomeKind({ it, busy, onSkip, act }) {
  const [kind, setKind] = useState(it.guess);
  const name = `inc-${it.txn.id}`;
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">What kind of income is this?</h2>
      <div className="pk-choices" role="radiogroup" aria-label="What kind of income is this?">
        {Object.entries(INCOME_KINDS).map(([k, label]) => (
          <Choice key={k} name={name} checked={kind === k} onChange={() => setKind(k)} label={label} />
        ))}
      </div>
      <Actions busy={busy} ready={!!kind} onSkip={onSkip}
               onSave={() => act(() => setIncomeType(it.txn.id, kind))} />
    </>
  );
}

/** Money into a joint account from outside Pearl: hers, or which of theirs? */
export function JointIn({ it, busy, onSkip, act }) {
  const [pick, setPick] = useState('');
  const [remember, setRemember] = useState(true);
  const name = `joint-${it.txn.id}`;
  const choices = depositChoices(it.people, it.label);
  const chosen = choices.find((c) => c.value === pick);
  return (
    <>
      <TxHead txn={it.txn} />
      <h2 className="pk-h2">Who put this in?</h2>
      <div className="pk-choices" role="radiogroup" aria-label="Who put this in?">
        {choices.map((c) => (
          <Choice key={c.value} name={name} checked={pick === c.value}
                  onChange={() => setPick(c.value)} label={c.label} description={c.description} />
        ))}
      </div>
      <Choice type="checkbox" checked={remember} onChange={setRemember}
              label={`The same for every deposit from ${it.txn.merchant}`}
              description="We’ll sort the next ones the same way." />
      <Actions busy={busy} ready={!!chosen} onSkip={onSkip}
               onSave={() => act(() => setJointFrom(it.txn.id, chosen.who, remember, chosen.person))} />
    </>
  );
}

