import { useMemo, useState } from 'react';
import { money, quickSortDone, quickSortSeen, quickSortStep } from '../api.js';
import { CategoryChip, ChipOption, Dialog, PButton, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import WhatWasThis from './WhatWasThis.jsx';
import './quicksort.css';

/**
 * Quick sort when you come back (Pearl THL-244 QS-01 to QS-06; THL-254).
 *
 * On sign-in, when there are new transactions Pearl isn't sure of (the
 * same rows Needs a look asks about, THL-227), a modal on the web and a
 * sheet on a phone: QS-01 the prompt, with Start and Later; QS-02 one card
 * per transaction — ✓ Right, Something else…, or Skip this one — with
 * "Later" at the top throughout; QS-03 the picker, suggested and recent
 * categories first, then a search, and "It wasn't a purchase…" into What
 * was this?; QS-04 the done screen: Allowance before → after, one line
 * on why, and how many rules were saved. Shown at most once a day. Later
 * and anything skipped stay in Needs a look.
 */
export default function QuickSort({ data, categories = [], onClose, onChanged }) {
  const [step, setStep] = useState('prompt');
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  // A rule saved for a merchant sorts its other cards too, so they're dropped.
  const [dropped, setDropped] = useState(() => new Set());
  const items = useMemo(() => (data.items ?? []).filter((x) => !dropped.has(x.id)), [data.items, dropped]);
  const ids = (data.items ?? []).map((x) => x.id);
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

  const later = () => run(() => quickSortSeen(ids, false), () => onClose?.());
  const start = () => run(() => quickSortSeen(ids, true), () => setStep('card'));
  const next = () => {
    if (i + 1 < items.length) { setI(i + 1); setStep('card'); return; }
    run(() => quickSortDone(), (r) => { setDone(r); setStep('done'); onChanged?.(); });
  };
  const answer = (body) => run(() => quickSortStep(item.id, body), (r) => {
    if (r?.rule_saved) {
      const same = items.filter((x, k) => k > i && x.merchant === item.merchant).map((x) => x.id);
      if (same.length) {
        setDropped((d) => new Set([...d, ...same]));
      }
    }
    next();
  });
  const finish = () => { onClose?.(); };

  if (step === 'prompt') return <Prompt count={items.length} busy={busy} error={error} onStart={start} onLater={later} />;
  if (step === 'done') return <Done r={done} onDone={finish} />;
  if (!item) return null;
  const head = (
    <Head label={`Quick sort · ${i + 1} of ${items.length}`}
          action={step === 'card' ? { label: 'Later', onClick: finish } : { label: 'Back', onClick: () => setStep('card') }} />
  );
  if (step === 'pick') {
    return (
      <Dialog labelledBy="qs-title" onClose={finish} className="qs-dialog">
        {head}
        <h2 className="pk-h2" id="qs-title">What was it?</h2>
        <Picker item={item} categories={categories} busy={busy}
                onSave={(cat) => answer({ action: 'category', category: cat })}
                onNotPurchase={() => setStep('what')} />
        {error && <p className="pk-error" role="alert">{error.message || 'That didn’t save. Try again.'}</p>}
      </Dialog>
    );
  }
  if (step === 'what') {
    return (
      <Dialog labelledBy="qs-title" onClose={finish} className="qs-dialog">
        {head}
        <h2 className="pk-h2" id="qs-title">What was this?</h2>
        <WhatWasThis tx={{ id: item.id, merchant: item.merchant, amount: item.amount, inflow: item.inflow, logo: item.logo }}
                     categories={categories} busy={busy} saveLabel="Save and next" showHead={false}
                     onDone={(res) => answer({ action: 'marked', title: res?.title || '' })} />
      </Dialog>
    );
  }
  return (
    <Dialog labelledBy="qs-title" onClose={finish} className="qs-dialog">
      {head}
      <Progress n={items.length} at={i} />
      <Card item={item} />
      <div className="qs-guess">
        <p className="pk-label">Pearl’s guess</p>
        {item.guess === 'Other'
          ? <p className="pk-muted">Pearl couldn’t tell what this was.</p>
          : <CategoryChip label={categoryLabel(item.guess)} suggested />}
      </div>
      {error && <p className="pk-error" role="alert">{error.message || 'That didn’t save. Try again.'}</p>}
      <div className="qs-actions">
        {item.guess === 'Other' ? (
          <PButton disabled={busy} onClick={() => setStep('pick')}>Pick a category</PButton>
        ) : (
          <>
            <PButton className="qs-right" disabled={busy} onClick={() => answer({ action: 'right' })}>✓ Right</PButton>
            <PButton variant="secondary" disabled={busy} onClick={() => setStep('pick')}>Something else…</PButton>
          </>
        )}
        <PButton variant="text" disabled={busy} onClick={() => answer({ action: 'skip' })}>Skip this one</PButton>
      </div>
    </Dialog>
  );
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

/** The transaction on the card: its name, when and where, and the amount. */
export function Card({ item }) {
  return (
    <div className="qs-tx">
      <div className="qs-tx-text">
        <span>{item.merchant}</span>
        <span className="pk-muted">{longDate(item.date)}{item.account ? ` · ${item.account}` : ''}</span>
      </div>
      <span className={`pk-h2 qs-amt ${item.inflow ? 'in' : 'out'}`}>
        {txAmount(item.amount, { inflow: item.inflow, signed: true })}
      </span>
    </div>
  );
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

/** QS-03: suggested and recent first, then a search over every category. */
export function Picker({ item, categories, busy, onSave, onNotPurchase }) {
  const [pick, setPick] = useState('');
  const [q, setQ] = useState('');
  const groups = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const all = useMemo(() => groups.flatMap((g) => g.names), [groups]);
  const needle = q.trim().toLowerCase();
  const found = needle ? all.filter((n) => categoryLabel(n).toLowerCase().includes(needle)) : [];
  const suggested = item.suggested ?? [];
  const recent = (item.recent ?? []).filter((n) => !suggested.includes(n));
  return (
    <>
      <div className="gl-field qs-search">
        <label htmlFor="qs-q" className="pk-sr">Search categories</label>
        <input id="qs-q" type="search" placeholder="Search categories" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {needle ? (
        <div className="qs-group">
          <p className="pk-overline">{found.length ? 'Matches' : 'No match'}</p>
          <div className="pk-opts" role="radiogroup" aria-label="Matches">
            {found.map((n) => <ChipOption key={n} label={categoryLabel(n)} selected={pick === n} onSelect={() => setPick(n)} />)}
          </div>
        </div>
      ) : (
        <>
          {suggested.length > 0 && (
            <div className="qs-group">
              <p className="pk-overline">Suggested</p>
              <div className="pk-opts" role="radiogroup" aria-label="Suggested">
                {suggested.map((n) => (
                  <ChipOption key={n} label={categoryLabel(n)} selected={pick === n} suggested={n === item.guess}
                              onSelect={() => setPick(n)} />
                ))}
              </div>
            </div>
          )}
          {recent.length > 0 && (
            <div className="qs-group">
              <p className="pk-overline">Recent</p>
              <div className="pk-opts" role="radiogroup" aria-label="Recent">
                {recent.map((n) => <ChipOption key={n} label={categoryLabel(n)} selected={pick === n} onSelect={() => setPick(n)} />)}
              </div>
            </div>
          )}
          <CategoryChips groups={groups} value={pick} onChange={setPick} label="Every category" />
        </>
      )}
      <div className="qs-not">
        <button type="button" className="txd-link" onClick={onNotPurchase}>
          It wasn’t a purchase… <PIcon name="chevronRight" size={14} />
        </button>
        <p className="pk-muted">Opens “What was this?” for transfers, paybacks and refunds.</p>
      </div>
      <div className="qs-actions">
        <PButton disabled={busy || !pick} onClick={() => onSave(pick)}>Save and next</PButton>
      </div>
    </>
  );
}

/** "$642.18 → $598.40", or what can be said when a figure is missing. */
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
