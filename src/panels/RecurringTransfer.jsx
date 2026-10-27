import { useMemo, useState } from 'react';
import { Choice, PButton, txAmount } from '../pearl/kit.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { Progress, TxHead } from './SortCard.jsx';
import { confirmRecurring, dismissReview } from '../api.js';

/**
 * "Is this a recurring transfer?" (2026-10-27): the same amount out of one
 * account on a schedule, asked once for the whole series
 * (finance/recurring_transfers.py). Yes, and what it is, sorts every one of
 * them, and every one that matches its amount and schedule from now on.
 * No asks about each one on its own, as before.
 */
export const RECURRING_KINDS = [
  { v: 'rent', label: 'Rent' },
  { v: 'saved', label: 'Into savings' },
  { v: 'moved', label: 'Moved to another of my accounts' },
  { v: 'else', label: 'Something else' },
];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const short = (iso) => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

export default function RecurringQuestion({ it, categories = [], busy, act, commit, onSkip }) {
  const [step, setStep] = useState('q1');
  const [cat, setCat] = useState('');
  const s = it.series;
  const spending = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const answers = (what) => [
    { step: 'q1', v: 'yes', label: 'Recurring', title: 'Is this a recurring transfer?' },
    { step: 'what', v: what.v, label: what.label, title: 'What is it?' },
  ];
  const save = (what, body) => commit(() => confirmRecurring(it.key, body).then((res) => ({
    title: res?.title, detail: res?.detail, undo: res?.undo,
  })), { answers: answers(what), effect: '' });
  const pick = (v) => {
    if (v === 'else') { setStep('cat'); return; }
    save(RECURRING_KINDS.find((k) => k.v === v), { kind: v });
  };
  return (
    <>
      <TxHead txn={it.txn} />
      <Progress done={step === 'q1' ? 0 : 1} total={2} />
      {step === 'q1' && (
        <div className="nl-step">
          <h2 className="pk-h2 nl-q">Is this a recurring transfer?</h2>
          <p className="pk-muted nl-sub">{it.reason}</p>
          <ul className="nl-series" aria-label="The transfers">
            {(it.rows ?? []).slice(0, 4).map((r) => (
              <li key={r.id}><span>{short(r.date)}</span><span>{txAmount(r.amount)}</span></li>
            ))}
            {(it.rows ?? []).length > 4 && <li className="pk-muted">{`and ${it.rows.length - 4} more`}</li>}
          </ul>
          <div className="pk-choices" role="radiogroup" aria-label="Is this a recurring transfer?">
            <Choice name={`rt-${it.key}`} checked={false} disabled={busy} onChange={() => setStep('what')}
                    label="Yes, it repeats" description="These and the ones to come are sorted the same way" />
            <Choice name={`rt-${it.key}`} checked={false} disabled={busy}
                    onChange={() => act(() => dismissReview(it.key), () => 'Asked about one at a time')}
                    label="No, they’re separate" description="Pearl asks about each one on its own" />
          </div>
        </div>
      )}
      {step === 'what' && (
        <div className="nl-step">
          <h2 className="pk-h2 nl-q">What is it?</h2>
          <p className="pk-muted nl-sub">{`The ${s.count} so far, and each new ${txAmount(s.amount)} transfer ${s.when}.`}</p>
          <div className="pk-choices" role="radiogroup" aria-label="What is it?">
            {RECURRING_KINDS.map((k) => (
              <Choice key={k.v} name={`rt-what-${it.key}`} checked={false} disabled={busy}
                      onChange={() => pick(k.v)} label={k.label} />
            ))}
          </div>
        </div>
      )}
      {step === 'cat' && (
        <div className="nl-step">
          <h2 className="pk-h2 nl-q">What is it for?</h2>
          <CategoryChips groups={spending} value={cat} label="What is it for?"
                         onChange={(v) => { setCat(v); save({ v, label: categoryLabel(v) }, { category: v }); }} />
        </div>
      )}
      <div className="nl-actions">
        {step !== 'q1' && (
          <PButton variant="text" disabled={busy} onClick={() => setStep(step === 'cat' ? 'what' : 'q1')}>Back</PButton>
        )}
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
      </div>
    </>
  );
}
