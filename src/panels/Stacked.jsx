import { useEffect, useMemo, useState } from 'react';
import { Avatar, Choice, PButton, amountTone, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { RepaymentMatch } from './Splits.jsx';
import { depositChoices } from './joint.js';
import WhatWasThis from './WhatWasThis.jsx';
import {
  INCOME_KINDS, confirmTx, dismissReview, getTxCases, linkPayback, markTx, setCategory,
  setIncomeType, setJointFrom, setParty, sortTransfers,
} from '../api.js';
import './stacked.css';

/**
 * Needs a look, stacked (R-07 to R-12, 2026-10-17): one transaction, one
 * short question at a time. Each answer folds into a grey line with Change
 * above the next question, and dots count the steps. A choice that leads
 * somewhere moves on at once; the last one shows what it will do and Save
 * and next.
 *
 * Money out starts at "Was this spending?" (Yes, I bought something → what
 * for; No, I saved it → which account; No, something else → moved, lent,
 * paying someone back… → who to). Money in starts at "Is this income?"
 * (Yes → what kind; No, I moved my own money; No, something else → who put
 * it in, for a joint account, or what it was → which purchase, which
 * account, who sent it). Every answer goes through the same calls as the
 * What was this? sheet, so the list and the month never disagree.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const longDate = (iso) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${WEEKDAYS[new Date(y, m - 1, d).getDay()]}, ${MONTHS[m - 1]} ${d}`;
};
const shortDate = (iso) => `${SHORT[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

/** "e-Transfer to M. Papas" → "M. Papas". */
export function nameIn(text = '') {
  const m = text.match(/(?:e-?\s?transfer|interac)\s*(?:to|from)\s+(.+)$/i);
  return (m ? m[1] : '').replace(/\*+/g, '').trim();
}

const isOut = (it) => (it.txn?.amount ?? 0) > 0;

/**
 * The questions for one item, as steps. Each step has a title, what it
 * asks (choices, chips, a name…), and for each choice where it leads (`to`)
 * or nothing, when it's the last answer. `left` is how many steps remain
 * at most, counting this one, for the dots.
 */
export function steps(it, cases) {
  const guess = it.guess && typeof it.guess === 'string' ? it.guess : '';
  const kindsOf = (k) => (cases?.cases ?? []).find((c) => c.key === k)?.candidates ?? [];
  const S = {};
  if (isOut(it)) {
    const unsure = it.kind === 'category' && guess && guess !== 'Other';
    S.q1 = unsure ? {
      title: `Is this ${categoryLabel(guess)}?`, left: 3,
      options: [
        { v: 'yes', label: `Yes, ${categoryLabel(guess)}`, done: categoryLabel(guess) },
        { v: 'other', label: 'No, a different category', done: 'A different category', to: 'cat' },
        { v: 'else', label: 'It wasn’t a purchase', done: 'Not a purchase', to: 'what_out' },
      ],
    } : {
      title: 'Was this spending?', left: 3,
      options: [
        { v: 'spent', label: 'Yes, I bought something', done: 'Spending', to: 'cat' },
        { v: 'saved', label: 'No, I saved it', done: 'Saved', to: 'account' },
        { v: 'else', label: 'No, something else', done: 'Something else', to: 'what_out' },
      ],
    };
    S.cat = { title: 'What was it for?', left: 1, ask: 'category' };
    S.account = { title: 'Which account did it go to?', left: 1, ask: 'account' };
    S.what_out = {
      title: 'What was it?', left: 2,
      options: [
        { v: 'moved', label: 'Moved between my own accounts', done: 'Moved between my accounts' },
        { v: 'lent', label: 'Lent to someone', done: 'Lent', to: 'who_to' },
        { v: 'paying_back', label: 'Paying someone back', done: 'Paying someone back', to: 'who_to' },
        { v: 'work', label: 'A work expense, to be reimbursed', done: 'A work expense' },
        { v: 'not_mine', label: 'Not mine', done: 'Not mine' },
        { v: 'more', label: 'Something else…', done: 'Something else', to: 'sheet' },
      ],
    };
    S.who_to = { title: 'Who to?', left: 1, ask: 'name' };
    S.sheet = { title: 'What was this?', left: 1, ask: 'sheet' };
    return { start: 'q1', S };
  }
  const joint = it.kind === 'joint_in';
  const nameless = it.kind === 'who_sent';
  const match = it.kind === 'money_in' && it.guess?.action === 'split' ? it.guess.split : null;
  if (match) {
    S.match = {
      title: `Is ${match.name} paying you back?`, left: 3, match,
      options: [
        { v: 'yes', label: 'Yes, link them', done: `${match.name} paying me back` },
        { v: 'no', label: 'No, it’s something else', done: 'Something else', to: 'q1' },
      ],
    };
  }
  S.q1 = {
    title: 'Is this income?', left: nameless ? 3 : 2,
    options: [
      { v: 'income', label: 'Yes, it’s income', done: 'Income', to: 'kind' },
      { v: 'own', label: 'No, I moved my own money', done: 'My own money' },
      { v: 'else', label: 'No, something else', done: 'Something else', to: joint ? 'who_in' : 'what_in' },
    ],
  };
  S.kind = { title: 'What kind of income?', left: 1, ask: 'kind' };
  S.who_in = {
    title: 'Who put this in?', left: 1, ask: 'joint',
    sub: 'A deposit to your joint account. Until you answer, it counts as nothing.',
  };
  const payback = kindsOf('payback');
  const refund = (cases?.cases ?? []).some((c) => c.key === 'refund');
  const reimb = kindsOf('reimbursement');
  S.what_in = {
    title: 'What was it?', left: 2,
    options: [
      { v: 'payback', label: 'Paying me back', done: 'Paying me back',
        to: nameless ? 'name' : payback.length ? 'pick_payback' : undefined, as: 'lent_back' },
      ...(refund ? [{ v: 'refund', label: 'A refund', done: 'A refund', to: 'pick_refund' }] : []),
      ...(reimb.length ? [{ v: 'reimbursement', label: 'A reimbursement', done: 'A reimbursement', to: 'pick_reimb' }] : []),
      { v: 'out_of_savings', label: 'Taken out of my savings', done: 'Out of savings', to: 'account_in' },
      { v: 'borrowed', label: 'Money I borrowed', done: 'Borrowed' },
      { v: 'not_mine', label: 'Not mine', done: 'Not mine' },
    ],
  };
  S.name = { title: 'Who sent this?', left: payback.length ? 2 : 1, ask: 'sender',
             sub: 'Your bank left the name off. Pearl uses it to match paybacks.',
             to: payback.length ? 'pick_payback' : undefined };
  S.pick_payback = { title: 'Which purchase is it for?', left: 1, ask: 'pick', key: 'payback',
                     candidates: payback, none: 'None of these: money I lent' };
  S.pick_refund = { title: 'Which purchase is it a refund of?', left: 1, ask: 'pick', key: 'refund',
                    candidates: kindsOf('refund') };
  S.pick_reimb = { title: 'Which expense does it pay back?', left: 1, ask: 'pick', key: 'reimbursement',
                   candidates: reimb };
  S.account_in = { title: 'Which account did it come from?', left: 1, ask: 'account' };
  return { start: match ? 'match' : 'q1', S };
}

/** The dots: answered steps filled, the rest dashed, and "2 of 3". */
export function Progress({ done, total }) {
  return (
    <p className="nl-steps" aria-label={`Step ${Math.min(done + 1, total)} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`nl-dot${i < done ? ' on' : ''}`} aria-hidden="true" />
      ))}
      <span className="nl-steps-n" aria-hidden="true">{`${done} of ${total}`}</span>
    </p>
  );
}

/** The transaction: a row with an avatar for money out, a soft panel for money in. */
export function TxHead({ txn, name }) {
  const inflow = txn.amount < 0;
  const amount = txAmount(Math.abs(txn.amount), { inflow, signed: true });
  const where = txn.account_name ? ` · ${inflow ? '' : 'from '}${txn.account_name}` : '';
  return (
    <div className={`nl-tx${inflow ? ' in' : ''}`}>
      {!inflow && <Avatar name={name || txn.merchant} logo={txn.logo} />}
      <div className="nl-tx-text">
        <span>{txn.merchant}</span>
        <span className="pk-label pk-muted">{`${longDate(txn.date)}${where}`}</span>
      </div>
      <span className={`nl-tx-amt ${amountTone(inflow)}`}>{amount}</span>
    </div>
  );
}

export default function Stacked({ it, categories = [], busy, act, sorted, onSkip, onTab }) {
  const [cases, setCases] = useState(null);
  const [path, setPath] = useState([]);            // [{ step, v }]
  const [pick, setPick] = useState(null);          // the last answer, before Save
  const [name, setName] = useState(() => nameIn(it.txn?.merchant) || it.to || '');
  const [cat, setCat] = useState('');
  const [remember, setRemember] = useState(it.kind === 'joint_in' || !!it.learnable);
  useEffect(() => {
    let live = true;
    getTxCases(it.txn.id).then((d) => { if (live) setCases(d); }).catch(() => { if (live) setCases({ cases: [] }); });
    return () => { live = false; };
  }, [it.txn.id]);

  const flow = useMemo(() => steps(it, cases), [it, cases]);
  const stepId = path.length ? nextOf(flow, path[path.length - 1]) : flow.start;
  // Pearl's guess at the kind of income is already chosen.
  useEffect(() => {
    if (stepId === 'kind' && it.kind === 'income' && it.guess) setPick(it.guess);
  }, [stepId]);                                             // eslint-disable-line react-hooks/exhaustive-deps
  const step = flow.S[stepId];
  // A last answer chosen means one step left, whatever the longest path was.
  const lastChosen = step?.options && pick !== null && !step.options.find((o) => o.v === pick)?.to;
  const total = path.length + (lastChosen ? 1 : (step?.left ?? 1));
  const amt = txAmount(Math.abs(it.txn.amount));
  const answered = (k) => path.find((p) => p.step === k)?.v;
  const go = (v) => {
    const opt = step.options?.find((o) => o.v === v);
    if (opt?.to) { setPath([...path, { step: stepId, v }]); setPick(null); } else setPick(v);
  };
  const rewind = (i) => { setPath(path.slice(0, i)); setPick(null); };

  // ── What the last answer does, and saving it ─────────────────────────
  const out = isOut(it);
  const via = (body, title) => act(() => markTx(it.txn.id, body), (res) => ({
    title: res?.title || title, detail: res?.detail || '', undo: res?.undo,
  }));
  const spendingCats = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group),
  }), [categories]);
  const accounts = cases?.accounts ?? [];
  const people = (cases?.people ?? []).filter((p) => p.toLowerCase() !== name.trim().toLowerCase());
  const choices = depositChoices(it.people, it.label);

  let ready = false; let effect = ''; let save = () => {};
  const lastQ = stepId;
  if (step?.ask === 'category') {
    ready = !!cat;
    effect = cat ? `Counts as ${categoryLabel(cat)} spending.` : '';
    save = () => (it.kind === 'unsorted'
      ? act(() => sortTransfers([it.txn.id], cat, it.learnable && remember), sorted(`Sorted as ${categoryLabel(cat)}.`))
      : act(() => setCategory(it.txn.id, cat, remember), sorted(`Moved to ${categoryLabel(cat)}.`)));
  } else if (step?.ask === 'account') {
    ready = pick !== null;
    const a = accounts.find((x) => x.id === pick);
    if (lastQ === 'account_in') {
      effect = ready ? `Not income. It comes off Savings this month${a ? `, from ${a.label}` : ''}.` : '';
      save = () => via({ case: 'out_of_savings', account: pick || '' }, 'Sorted as taken out of savings.');
    } else {
      effect = ready ? `Not spending. It adds ${amt} to Savings this month${a?.anchor ? ' and to your Anchor' : ''}.` : '';
      save = () => via({ case: 'saved', account: pick || '', remember: !!(it.learnable && remember) },
        a ? `Put away to ${a.label}.` : 'Sorted as savings.');
    }
  } else if (step?.ask === 'name') {
    const how = answered('what_out');
    ready = !!name.trim();
    effect = how === 'lent'
      ? `Not spending. Safe to spend goes up by ${amt} and ${name.trim() || 'they'} owe${name.trim() ? 's' : ''} you ${amt}.`
      : `Not spending. Safe to spend goes up by ${amt}.`;
    save = () => act(async () => {
      const res = await markTx(it.txn.id, how === 'lent' ? { case: 'lent' } : { case: 'paying_back', counted: true });
      if (name.trim() && name.trim() !== nameIn(it.txn.merchant)) await setParty(it.txn.id, name.trim());
      return res;
    }, (res) => ({ title: res?.title || (how === 'lent' ? `Lent to ${name.trim()}.` : `Paying back ${name.trim()}.`),
                   detail: res?.detail || '', undo: res?.undo }));
  } else if (step?.ask === 'sender') {
    ready = !!name.trim();
    save = () => act(async () => {
      await setParty(it.txn.id, name.trim());
      return markTx(it.txn.id, { case: 'lent_back' });
    }, (res) => ({ title: `${name.trim()} paid you back.`, detail: res?.detail || '', undo: res?.undo }));
  } else if (step?.ask === 'kind') {
    ready = !!pick;
    effect = ready ? `Counts as ${INCOME_KINDS[pick] ?? 'income'}.` : '';
    save = () => (it.kind === 'income'
      ? act(() => setIncomeType(it.txn.id, pick))
      : via({ case: 'pay', income_kind: pick }, 'Sorted as income.'));
  } else if (step?.ask === 'joint') {
    const chosen = choices.find((c) => c.value === pick);
    ready = !!chosen;
    effect = !chosen ? '' : chosen.who === 'me' ? 'A transfer, not income.'
      : `Covers ${chosen.label}’s share of joint spending. Your spending goes down by ${amt}.`;
    save = () => act(() => setJointFrom(it.txn.id, chosen.who, remember, chosen.person));
  } else if (step?.ask === 'pick') {
    ready = pick !== null && (pick !== '' || !!step.none || (step.key === 'refund' && !!cat));
    const c = step.candidates.find((x) => x.id === pick);
    effect = !ready ? '' : step.key === 'payback' ? (c ? `Comes off what you spent at ${c.merchant}. Not income.` : 'Moves it to Lent. Not income.')
      : step.key === 'refund' ? `Comes off ${c?.category || categoryLabel(cat)}. Not income.`
        : 'Pays back a work expense you left out. Not income.';
    save = () => {
      if (step.key === 'payback' && !pick) return via({ case: 'lent_back' }, 'Sorted as money you lent, paid back.');
      if (step.key === 'refund' && !pick) return via({ case: 'refund', category: cat }, 'Sorted as a refund.');
      return via({ case: step.key, charge: pick }, 'Sorted.');
    };
  } else if (step?.options && pick) {
    ready = true;
    const v = pick;
    if (lastQ === 'match') {
      effect = 'Not income. The split shows as paid back.';
      save = () => act(() => linkPayback(step.match.charge_id, it.txn.id, step.match.name));
    } else if (lastQ === 'q1' && out) {               // "Yes, Groceries"
      effect = `Stays in ${categoryLabel(it.guess)}.`;
      save = () => act(() => confirmTx(it.txn.id), () => 'Confirmed');
    } else if (lastQ === 'q1') {                       // my own money
      effect = 'A transfer. Not income.';
      save = () => (it.kind === 'joint_in' ? act(() => setJointFrom(it.txn.id, 'me', false))
        : it.kind === 'income' ? act(() => setCategory(it.txn.id, 'Transfers'), sorted('Sorted as your own money, not income.'))
          : via({ case: 'own' }, 'Sorted as your own money.'));
    } else if (lastQ === 'what_out') {
      const words = { moved: 'A transfer. Not spending, not income.', work: 'Left out of your spending until the money comes back.',
                      not_mine: 'Left out of everything.' };
      effect = words[v] ?? '';
      save = () => (v === 'moved' && it.kind === 'unsorted'
        ? act(() => sortTransfers([it.txn.id], 'Transfers', it.learnable && remember), sorted('Sorted as moved between your accounts.'))
        : via(v === 'not_mine' ? { case: v, reason: '' } : { case: v }, 'Sorted.'));
    } else if (lastQ === 'what_in') {
      const opt = step.options.find((o) => o.v === v);
      const words = { borrowed: 'Borrowed. Not income.', not_mine: 'Left out of everything.', payback: 'Moves it to Lent. Not income.' };
      effect = words[v] ?? '';
      save = () => via(v === 'not_mine' ? { case: v, reason: '' } : { case: opt?.as || v }, 'Sorted.');
    }
  }

  if (step?.ask === 'sheet') {
    return (
      <>
        <TxHead txn={it.txn} name={it.to} />
        <Progress done={path.length} total={total} />
        <Done path={path} flow={flow} onChange={rewind} />
        <WhatWasThis tx={{ id: it.txn.id, merchant: it.txn.merchant, amount: Math.abs(it.txn.amount),
                           inflow: !out, logo: it.txn.logo }}
                     categories={categories} busy={busy} saveLabel="Save and next" showHead={false}
                     onDone={(res) => act(() => Promise.resolve(res), sorted(res.title))} />
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
      </>
    );
  }

  const group = `q-${it.txn.id}-${stepId}`;
  return (
    <>
      <TxHead txn={it.txn} name={it.to} />
      <Progress done={path.length} total={total} />
      <Done path={path} flow={flow} onChange={rewind} />
      <h2 className="pk-h2 nl-q">{step.title}</h2>
      {step.sub && <p className="pk-muted nl-sub">{step.sub}</p>}
      {step.match && <RepaymentMatch match={step.match} />}

      {step.options && (
        <div className="pk-choices" role="radiogroup" aria-label={step.title}>
          {step.options.map((o) => (
            <Choice key={o.v} name={group} checked={pick === o.v} onChange={() => go(o.v)} label={o.label} />
          ))}
        </div>
      )}
      {step.ask === 'category' && (
        <>
          <CategoryChips groups={spendingCats} value={cat} onChange={setCat} label={step.title} />
          <Choice type="checkbox" checked={remember} onChange={setRemember}
                  label={it.kind === 'unsorted' ? `Remember for ${it.to || it.txn.merchant}` : `Always for ${it.txn.merchant}`} />
        </>
      )}
      {step.ask === 'account' && (
        <div className="pk-choices" role="radiogroup" aria-label={step.title}>
          {accounts.map((a) => (
            <Choice key={a.id} name={group} checked={pick === a.id} onChange={() => setPick(a.id)} label={a.label} />
          ))}
          <Choice name={group} checked={pick === ''} onChange={() => setPick('')} label="Not sure" />
        </div>
      )}
      {step.ask === 'kind' && (
        <div className="pk-choices" role="radiogroup" aria-label={step.title}>
          {Object.entries(INCOME_KINDS).map(([k, label]) => (
            <Choice key={k} name={group} checked={pick === k} onChange={() => setPick(k)} label={label} />
          ))}
        </div>
      )}
      {(step.ask === 'name' || step.ask === 'sender') && (
        <div className="txd-field nl-name">
          {step.ask === 'sender' && <label className="pk-label" htmlFor={group}>Their name</label>}
          <input id={group} type="text" value={name} maxLength={60} autoComplete="off"
                 aria-label={step.title} placeholder="First and last name"
                 onChange={(e) => setName(e.target.value)} />
          {step.ask === 'sender' && <p className="pk-label pk-muted">Shown in your list from now on</p>}
          {step.ask === 'name' && people.length > 0 && (
            <div className="nl-people">
              {people.map((p) => (
                <button key={p} type="button" className="nl-person" onClick={() => setName(p)}>{p}</button>
              ))}
            </div>
          )}
          {step.ask === 'sender' && (
            <button type="button" className="txd-link nl-other" disabled={busy}
                    onClick={() => act(() => dismissReview(it.key), () => 'Kept your bank’s name')}>
              Use your bank’s name instead
            </button>
          )}
        </div>
      )}
      {step.ask === 'joint' && (
        <>
          <div className="pk-choices" role="radiogroup" aria-label={step.title}>
            {choices.map((c) => (
              <Choice key={c.value} name={group} checked={pick === c.value} onChange={() => setPick(c.value)}
                      label={c.label} description={c.description} />
            ))}
          </div>
          <Choice type="checkbox" checked={remember} onChange={setRemember}
                  label={`Remember for deposits from ${(choices.find((c) => c.value === pick)?.who === 'them'
                    && choices.find((c) => c.value === pick)?.label) || it.txn.merchant}`} />
        </>
      )}
      {step.ask === 'pick' && (
        <>
          <div className="pk-choices" role="radiogroup" aria-label={step.title}>
            {step.candidates.map((c) => (
              <Choice key={c.id} name={group} checked={pick === c.id} onChange={() => setPick(c.id)}
                      label={`${c.merchant} · ${shortDate(c.date)}`}
                      description={[txAmount(c.amount, { signed: true }), c.category].filter(Boolean).join(' · ')} />
            ))}
            {(step.none || step.key === 'refund') && (
              <Choice name={group} checked={pick === ''} onChange={() => setPick('')}
                      label={step.none || 'None of these'} />
            )}
          </div>
          {step.key === 'refund' && pick === '' && (
            <CategoryChips groups={spendingCats} value={cat} onChange={setCat} label="What was it a refund of?" />
          )}
        </>
      )}

      {ready && effect && <p className="nl-effect" role="status">{effect}</p>}
      {step.ask === 'joint' && onTab && (
        <button type="button" className="txd-link nl-other" onClick={() => onTab('accounts')}>
          Who shares this account <PIcon name="chevronRight" size={14} />
        </button>
      )}
      <div className="nl-actions">
        {ready && (
          <PButton disabled={busy} onClick={() => (step.to && step.ask === 'sender'
            ? (setPath([...path, { step: stepId, v: name.trim() }]), setPick(null))
            : save())}>
            {step.to && step.ask === 'sender' ? 'Next' : 'Save and next'}
          </PButton>
        )}
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
      </div>
    </>
  );
}

/** Where the last answer leads. */
function nextOf(flow, last) {
  const s = flow.S[last.step];
  if (s?.options) return s.options.find((o) => o.v === last.v)?.to;
  return s?.to;
}

/** The answers so far, each a grey line with Change (R-11, R-12). */
function Done({ path, flow, onChange }) {
  if (!path.length) return null;
  return (
    <div className="nl-done-list">
      {path.map((p, i) => {
        const s = flow.S[p.step];
        const label = s?.options?.find((o) => o.v === p.v)?.done ?? p.v;
        return (
          <div key={`${p.step}-${i}`} className="nl-done">
            <span className="nl-done-ring" aria-hidden="true" />
            <span className="nl-done-label">{label}</span>
            <button type="button" className="nl-change" onClick={() => onChange(i)}
                    aria-label={`Change: ${label}`}>Change</button>
          </div>
        );
      })}
    </div>
  );
}
