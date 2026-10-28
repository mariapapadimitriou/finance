import { useCallback, useEffect, useMemo, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { deleteRule, editRule, getRecurringTransfers } from '../api.js';
import { Alert, Choice, DetailPanel, EmptyState, PButton, StatTile, Toast, txAmount } from '../pearl/kit.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { ListRow, PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Recurring transfers (2026-10-28): every transfer she said repeats
 * — the same amount on a schedule (finance/recurring_transfers.py) — in one
 * place: what it is, how often, the next one, and what a month of them comes
 * to. Tap one to change what it is, see the ones so far, or stop treating it
 * as recurring. Needs a look still asks about new ones; the page says how
 * many are waiting.
 */

const TRAIL = [{ label: 'Profile', to: 'profile' }, { label: 'Recurring transfers' }];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function parts(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return { y, m, d, dow: new Date(Date.UTC(y, m - 1, d)).getUTCDay() };
}
export const shortDay = (iso) => { const p = parts(iso); return `${MONTHS[p.m - 1].slice(0, 3)} ${p.d}`; };
export const longDay = (iso) => { const p = parts(iso); return `${DAYS[p.dow]}, ${MONTHS[p.m - 1]} ${p.d}`; };

// What a recurring transfer can be, as Needs a look asks it.
const KINDS = [
  { category: 'Rent & Housing', label: 'Rent' },
  { category: 'Saved', label: 'Into savings' },
  { category: 'Transfers', label: 'Moved to another of my accounts' },
];

/** "$1,500.00 every month, around the 1st · from Chequing". */
export function scheduleWords(r) {
  return [`${txAmount(r.amount)} ${r.when}`, r.account && `from ${r.account}`].filter(Boolean).join(' · ');
}

/** The page's own parts, data in, for tests. */
export function RecurringPage({ data, onTab, onOpen }) {
  const list = data.transfers ?? [];
  const asking = data.asking ?? 0;
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={TRAIL} title="Recurring transfers" onTab={onTab}>
        <p className="pk-muted">
          The same amount leaving on a schedule. Pearl sorts each new one the way you said.
        </p>
      </PageHead>
      {asking > 0 && (
        <Alert action="Review" onAction={() => onTab?.('review')}>
          {asking === 1 ? '1 more looks recurring.' : `${asking} more look recurring.`}
        </Alert>
      )}
      {list.length === 0 ? (
        <EmptyState icon="arrows" title="No recurring transfers yet">
          When the same amount leaves on a schedule, Needs a look asks whether it repeats. The
          ones you confirm show up here.
        </EmptyState>
      ) : (
        <>
          <div className="pk-tiles rt-tiles">
            <StatTile label="A month, on average" value={txAmount(data.monthly)} />
            <StatTile label="Recurring" value={String(list.length)} />
          </div>
          <section className="pf-section" aria-label="Your recurring transfers">
            <ul className="pf-list">
              {list.map((r) => (
                <ListRow key={r.id} name={r.name !== 'Transfer' ? `${r.what} · ${r.name}` : r.what}
                         sub={scheduleWords(r)}
                         end={<span className="pf-row-sub">{`Next ${shortDay(r.next)}`}</span>}
                         onOpen={() => onOpen(r)} />
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

/** One recurring transfer: what it is, the ones so far, or stop. */
export function RecurringDetail({ item, categories = [], onClose, onSave, onStop }) {
  const known = KINDS.some((k) => k.category === item.category);
  const [pick, setPick] = useState(known ? item.category : 'other');
  const [other, setOther] = useState(known ? null : item.category);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const groups = useMemo(() => groupCategories(categories, {
    only: (c) => !['Income', 'Transfers', 'Saved', 'Rent & Housing'].includes(c.name), keep: other,
  }), [categories, other]);
  const chosen = pick === 'other' ? other : pick;
  const run = (fn) => {
    setBusy(true);
    setError(null);
    fn().catch((e) => { setError(e.message); setBusy(false); });
  };
  return (
    <DetailPanel label={`Recurring transfer: ${item.what}`} overline="Recurring transfer" onClose={onClose}>
      <h1 className="pk-h2">{item.name !== 'Transfer' ? item.name : item.what}</h1>
      <p className="pk-muted">{`${scheduleWords(item)}. Next on ${longDay(item.next)}.`}</p>
      <section className="pf-section" aria-labelledby="rt-what">
        <h2 className="pk-h3" id="rt-what">What is it?</h2>
        <div className="pk-choices" role="radiogroup" aria-labelledby="rt-what">
          {KINDS.map((k) => (
            <Choice key={k.category} name="rt-what" label={k.label} checked={pick === k.category}
                    disabled={busy} onChange={() => setPick(k.category)} />
          ))}
          <Choice name="rt-what" label="Something else" checked={pick === 'other'} disabled={busy}
                  onChange={() => setPick('other')} />
        </div>
        {pick === 'other' && <CategoryChips groups={groups} value={other} onChange={setOther} />}
        <PButton disabled={busy || !chosen || chosen === item.category}
                 onClick={() => run(() => onSave(chosen))}>Save</PButton>
      </section>
      <section className="pf-section" aria-labelledby="rt-so-far">
        <h2 className="pk-h3" id="rt-so-far">
          {item.count === 1 ? 'The one so far' : `The ${item.count} so far`}
        </h2>
        <ul className="pf-list">
          {(item.transactions ?? []).map((t) => (
            <ListRow key={t.id} name={longDay(t.date)} chevron={false}
                     end={<span className="pf-row-sub">{txAmount(t.amount, { signed: true })}</span>} />
          ))}
        </ul>
      </section>
      {error && <Alert tone="caution">{error}</Alert>}
      <p className="pk-muted">Stopping it keeps how the ones so far are sorted. New ones are asked about again.</p>
      <PButton variant="text" disabled={busy} onClick={() => run(onStop)}>Stop treating it as recurring</PButton>
    </DetailPanel>
  );
}

export default function RecurringPanel({ categories = [], onTab, onChanged, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);
  const [note, setNote] = useState(null);
  const load = useCallback(() => getRecurringTransfers().then(setData).catch(setError), []);
  useEffect(() => { load(); }, [load, version]);

  if (error && !data) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) {
    return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading your recurring transfers…</p></div>;
  }
  const done = async (text) => {
    setOpen(null);
    setNote(text);
    await load();
    await onChanged?.();
  };
  return (
    <>
      <RecurringPage data={data} onTab={onTab} onOpen={setOpen} />
      {open && (
        <div className="pk">
          <RecurringDetail item={open} categories={categories} onClose={() => setOpen(null)}
                           onSave={async (category) => {
                             await editRule(open.rule_id, category);
                             const label = KINDS.find((k) => k.category === category)?.label ?? categoryLabel(category);
                             await done(`${label}, for the ones so far and every new one.`);
                           }}
                           onStop={async () => {
                             await deleteRule(open.rule_id);
                             await done('No longer recurring. The ones so far stay as they are.');
                           }} />
        </div>
      )}
      {note && <div className="pk"><Toast onDone={() => setNote(null)}>{note}</Toast></div>}
    </>
  );
}
