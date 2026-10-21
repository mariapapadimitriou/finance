import { useEffect, useMemo, useState } from 'react';
import { Avatar, Choice, PButton, amountTone, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { RepaymentMatch } from './Splits.jsx';
import { depositChoices } from './joint.js';
import {
  INCOME_KINDS, confirmTx, dismissReview, getTxCases, linkPayback, markTx, setCategory,
  setIncomeType, setJointFrom, setParty, sortTransfers,
} from '../api.js';
import './stacked.css';

/**
 * Needs a look, stacked (R-07 to R-13 on the Current design page,
 * 2026-10-20): one transaction, one short question at a time, and as few
 * taps as possible.
 *
 *   - Tapping an answer is the commit. There is no Save and next: an answer
 *     that leads to another question slides that question in under it; the
 *     last answer saves at once and the card becomes the Sorted card
 *     (NeedsALook.jsx). A name is committed with Enter or by picking a
 *     person she has named before.
 *   - Each answer folds into a row above the next question. Tapping a row
 *     reopens that step in place — its options expand where the row was,
 *     with the other answers still visible — and tapping the same row again
 *     collapses it. A different answer that leads the same way keeps the
 *     later answers; one that leads elsewhere drops them.
 *   - Undo sits in the card's top-right and takes back the last answer (or
 *     leaves the question when nothing is answered yet). Previous, above
 *     the card, is NeedsALook's: it returns to the transaction sorted before.
 *   - Dots count the steps; "What kind of income?" lays its options out in
 *     two columns; a Remember checkbox sits above the choices it applies to.
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
      ],
    };
    S.who_to = { title: 'Who to?', left: 1, ask: 'name' };
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

/** The dots: answered steps filled, the rest dashed, and "2 of 3" — or,
 * once everything is answered, a pink check and "Sorted". */
export function Progress({ done, total, sorted = false, trailing = null }) {
  const n = sorted ? total : Math.min(done + 1, total);
  return (
    <p className="nl-steps" aria-label={sorted ? 'Sorted' : `Step ${n} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`nl-dot${i < done || sorted ? ' on' : ''}`} aria-hidden="true" />
      ))}
      {sorted ? (
        <span className="nl-steps-sorted" aria-hidden="true"><PIcon name="check" size={14} /> Sorted</span>
      ) : (
        <span className="nl-steps-n" aria-hidden="true">{`${done} of ${total}`}</span>
      )}
      {trailing && <span className="nl-steps-trailing">{trailing}</span>}
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

/** The small pill in a card's corner: "↶ Undo", "↶ Previous". */
export function Pill({ children, className = '', ...rest }) {
  return (
    <button type="button" className={`nl-pill ${className}`} {...rest}>
      <PIcon name="undo" size={14} /> {children}
    </button>
  );
}

/** Where an answer leads. */
export function nextOf(flow, last) {
  const s = flow.S[last.step];
  if (s?.options) return s.options.find((o) => o.v === last.v)?.to;
  return s?.to;
}

/** The words for an answer, for the stacked rows and the Sorted card. */
export function answerLabel(flow, p) {
  const s = flow.S[p.step];
  if (s?.options) return s.options.find((o) => o.v === p.v)?.done ?? p.v;
  return p.label ?? p.v;
}

export default function Stacked({ it, categories = [], busy, act, commit, onSkip, onBack, onTab,
                                  initialPath = null, initialEdit = null, initialName = '' }) {
  const [cases, setCases] = useState(null);
  // [{ step, v, label? }]: the answers so far, the last one still open.
  const [path, setPath] = useState(() => initialPath ?? []);
  // The row being changed in place (an index into `path`), if any.
  const [editing, setEditing] = useState(initialEdit);
  const [name, setName] = useState(() => initialName || nameIn(it.txn?.merchant) || it.to || '');
  const [cat, setCat] = useState('');
  const [remember, setRemember] = useState(it.kind === 'joint_in' || !!it.learnable);
  useEffect(() => {
    let live = true;
    getTxCases(it.txn.id).then((d) => { if (live) setCases(d); }).catch(() => { if (live) setCases({ cases: [] }); });
    return () => { live = false; };
  }, [it.txn.id]);

  const flow = useMemo(() => steps(it, cases), [it, cases]);
  const stepId = path.length ? nextOf(flow, path[path.length - 1]) : flow.start;
  const step = flow.S[stepId];
  const total = path.length + (step?.left ?? 1);
  const amt = txAmount(Math.abs(it.txn.amount));
  const answered = (k) => path.find((p) => p.step === k)?.v;
  const out = isOut(it);

  // ── What an answer does, and saving it ───────────────────────────────
  const via = (body, title) => markTx(it.txn.id, body).then((res) => ({
    res, title: res?.title || title, detail: res?.detail || '', undo: res?.undo,
  }));
  const plain = (fn, title) => fn().then((res) => ({
    res, title: [title, res?.impact?.title].filter(Boolean).join(' ') || title,
    detail: res?.impact?.detail ?? res?.detail ?? '', undo: res?.undo,
  }));
  const spendingCats = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group),
  }), [categories]);
  const accounts = cases?.accounts ?? [];
  const people = (cases?.people ?? []).filter((p) => p.toLowerCase() !== name.trim().toLowerCase());
  const choices = depositChoices(it.people, it.label);

  /** Commit the last answer: run the call, then hand the card to NeedsALook. */
  const finish = (answers, effect, run) => commit(() => run(), {
    answers: answers.map((p) => ({ ...p, label: p.label ?? answerLabel(flow, p) })), effect,
  });

  // The last answer of a step that asks (chips, an account, a kind…).
  const lastOf = (s, v, label) => [...path, { step: s, v, label }];
  const saveAsk = (s, v, label) => {
    const answers = lastOf(s, v, label);
    if (s.ask === 'category') {
      const effect = `Counts as ${categoryLabel(v)} spending.`;
      return finish(answers, effect, () => (it.kind === 'unsorted'
        ? plain(() => sortTransfers([it.txn.id], v, it.learnable && remember), `Sorted as ${categoryLabel(v)}.`)
        : plain(() => setCategory(it.txn.id, v, remember), `Moved to ${categoryLabel(v)}.`)));
    }
    if (s.ask === 'account') {
      const a = accounts.find((x) => x.id === v);
      if (stepId === 'account_in') {
        return finish(answers, `Not income. It comes off Savings this month${a ? `, from ${a.label}` : ''}.`,
          () => via({ case: 'out_of_savings', account: v || '' }, 'Sorted as taken out of savings.'));
      }
      return finish(answers, `Not spending. It adds ${amt} to Savings this month${a?.anchor ? ' and to your Anchor' : ''}.`,
        () => via({ case: 'saved', account: v || '', remember: !!(it.learnable && remember) },
          a ? `Put away to ${a.label}.` : 'Sorted as savings.'));
    }
    if (s.ask === 'kind') {
      return finish(answers, `Counts as ${INCOME_KINDS[v] ?? 'income'}.`, () => (it.kind === 'income'
        ? plain(() => setIncomeType(it.txn.id, v), `Counts as ${INCOME_KINDS[v] ?? 'income'}.`)
        : via({ case: 'pay', income_kind: v }, 'Sorted as income.')));
    }
    if (s.ask === 'joint') {
      const chosen = choices.find((c) => c.value === v);
      const effect = chosen?.who === 'me' ? 'A transfer, not income.'
        : `Covers ${chosen?.label}’s share of joint spending. Your spending goes down by ${amt}.`;
      return finish(answers, effect, () => plain(() => setJointFrom(it.txn.id, chosen.who, remember, chosen.person), 'Sorted.'));
    }
    if (s.ask === 'pick') {
      const c = s.candidates.find((x) => x.id === v);
      if (s.key === 'payback' && !v) {
        return finish(answers, 'Moves it to Lent. Not income.', () => via({ case: 'lent_back' }, 'Sorted as money you lent, paid back.'));
      }
      if (s.key === 'refund' && !v) {
        return finish(answers, `Comes off ${categoryLabel(cat)}. Not income.`, () => via({ case: 'refund', category: cat }, 'Sorted as a refund.'));
      }
      const effect = s.key === 'payback' ? `Comes off what you spent at ${c?.merchant}. Not income.`
        : s.key === 'refund' ? `Comes off ${c?.category || ''}. Not income.`
          : 'Pays back a work expense you left out. Not income.';
      return finish(answers, effect, () => via({ case: s.key, charge: v }, 'Sorted.'));
    }
    if (s.ask === 'name') {
      const how = answered('what_out');
      const who = v.trim();
      const effect = how === 'lent'
        ? `Not spending. Allowance goes up by ${amt} and ${who} owes you ${amt}.`
        : `Not spending. Allowance goes up by ${amt}.`;
      return finish(answers, effect, async () => {
        const res = await markTx(it.txn.id, how === 'lent' ? { case: 'lent' } : { case: 'paying_back', counted: true });
        // Only an e-Transfer carries a name at the bank; for anything else
        // the name is for the Sorted card alone.
        if (who && who !== nameIn(it.txn.merchant)) await setParty(it.txn.id, who).catch(() => {});
        return { res, title: res?.title || (how === 'lent' ? `Lent to ${who}.` : `Paying back ${who}.`),
                 detail: res?.detail || '', undo: res?.undo };
      });
    }
    if (s.ask === 'sender') {
      const who = v.trim();
      return finish(answers, `${who} paid you back. Not income.`, async () => {
        await setParty(it.txn.id, who);
        const res = await markTx(it.txn.id, { case: 'lent_back' });
        return { res, title: `${who} paid you back.`, detail: res?.detail || '', undo: res?.undo };
      });
    }
    return undefined;
  };

  // The last answer of a step with choices.
  const saveChoice = (sId, v, pathBefore) => {
    const s = flow.S[sId];
    const answers = [...pathBefore, { step: sId, v }];
    if (sId === 'match') {
      return finish(answers, 'Not income. The split shows as paid back.',
        () => plain(() => linkPayback(s.match.charge_id, it.txn.id, s.match.name), 'Linked.'));
    }
    if (sId === 'q1' && out) {                                   // "Yes, Groceries"
      return finish(answers, `Stays in ${categoryLabel(it.guess)}.`, () => plain(() => confirmTx(it.txn.id), 'Confirmed.'));
    }
    if (sId === 'q1') {                                          // my own money
      return finish(answers, 'A transfer. Not income.', () => (it.kind === 'joint_in'
        ? plain(() => setJointFrom(it.txn.id, 'me', false), 'Sorted as your own money.')
        : it.kind === 'income'
          ? plain(() => setCategory(it.txn.id, 'Transfers'), 'Sorted as your own money, not income.')
          : via({ case: 'own' }, 'Sorted as your own money.')));
    }
    if (sId === 'what_out') {
      const words = { moved: 'A transfer. Not spending, not income.',
                      work: 'Left out of your spending until the money comes back.',
                      not_mine: 'Left out of everything.' };
      return finish(answers, words[v] ?? '', () => (v === 'moved' && it.kind === 'unsorted'
        ? plain(() => sortTransfers([it.txn.id], 'Transfers', it.learnable && remember), 'Sorted as moved between your accounts.')
        : via(v === 'not_mine' ? { case: v, reason: '' } : { case: v }, 'Sorted.')));
    }
    if (sId === 'what_in') {
      const opt = s.options.find((o) => o.v === v);
      const words = { borrowed: 'Borrowed. Not income.', not_mine: 'Left out of everything.',
                      payback: 'Moves it to Lent. Not income.' };
      return finish(answers, words[v] ?? '', () => via(v === 'not_mine' ? { case: v, reason: '' } : { case: opt?.as || v }, 'Sorted.'));
    }
    return undefined;
  };

  /** A choice tapped on the open question: lead on, or commit. */
  const choose = (v) => {
    const opt = step.options?.find((o) => o.v === v);
    if (opt?.to) { setPath([...path, { step: stepId, v }]); return; }
    saveChoice(stepId, v, path);
  };

  /** A choice tapped on a reopened step `i`. */
  const rechoose = (i, v) => {
    const sId = path[i].step;
    const s = flow.S[sId];
    const was = s.options?.find((o) => o.v === path[i].v);
    const now = s.options?.find((o) => o.v === v);
    if (!now) return;
    setEditing(null);
    if (!now.to) { saveChoice(sId, v, path.slice(0, i)); return; }
    if (now.to === was?.to) {
      setPath(path.map((p, k) => (k === i ? { step: p.step, v } : p)));
    } else {
      setPath([...path.slice(0, i), { step: sId, v }]);
    }
  };

  // Undo in the card: the last answer comes back (or the question is left).
  const undoLast = () => {
    if (editing !== null) { setEditing(null); return; }
    if (path.length) { setPath(path.slice(0, -1)); return; }
    onBack?.();
  };

  const group = `q-${it.txn.id}-${stepId}`;
  const inputDone = (v) => {
    const who = v.trim();
    if (!who) return;
    if (step.ask === 'sender' && step.to) {
      setPath([...path, { step: stepId, v: who, label: who }]);
      return;
    }
    saveAsk(step, who, who);
  };

  return (
    <>
      <TxHead txn={it.txn} name={it.to} />
      <Progress done={path.length} total={total}
                trailing={(
                  <Pill className="nl-undo" onClick={undoLast} disabled={busy}
                        aria-label={path.length || editing !== null ? 'Undo the last answer' : 'Back to the list'}>
                    Undo
                  </Pill>
                )} />
      <Done path={path} flow={flow} editing={editing} busy={busy}
            onOpen={(i) => setEditing(editing === i ? null : i)}
            onPick={rechoose} />

      {step && (
        <>
          <h2 className="pk-h2 nl-q">{step.title}</h2>
          {step.sub && <p className="pk-muted nl-sub">{step.sub}</p>}
          {step.match && <RepaymentMatch match={step.match} />}

          {step.ask === 'category' && (
            <Choice type="checkbox" checked={remember} onChange={setRemember}
                    label={it.kind === 'unsorted' ? `Remember for ${it.to || it.txn.merchant}` : `Always for ${it.txn.merchant}`} />
          )}
          {step.options && (
            <div className="pk-choices" role="radiogroup" aria-label={step.title}>
              {step.options.map((o) => (
                <Choice key={o.v} name={group} checked={false} disabled={busy}
                        onChange={() => choose(o.v)} label={o.label} />
              ))}
            </div>
          )}
          {step.ask === 'category' && (
            <CategoryChips groups={spendingCats} value={cat} label={step.title}
                           onChange={(v) => { setCat(v); saveAsk(step, v, categoryLabel(v)); }} />
          )}
          {step.ask === 'account' && (
            <div className="pk-choices" role="radiogroup" aria-label={step.title}>
              {accounts.map((a) => (
                <Choice key={a.id} name={group} checked={false} disabled={busy}
                        onChange={() => saveAsk(step, a.id, a.label)} label={a.label} />
              ))}
              <Choice name={group} checked={false} disabled={busy}
                      onChange={() => saveAsk(step, '', 'Not sure')} label="Not sure" />
            </div>
          )}
          {step.ask === 'kind' && (
            <div className="pk-choices nl-grid" role="radiogroup" aria-label={step.title}>
              {Object.entries(INCOME_KINDS).map(([k, label]) => (
                <Choice key={k} name={group} checked={it.kind === 'income' && it.guess === k} disabled={busy}
                        onChange={() => saveAsk(step, k, label)} label={label} />
              ))}
            </div>
          )}
          {(step.ask === 'name' || step.ask === 'sender') && (
            <div className="txd-field nl-name">
              {step.ask === 'sender' && <label className="pk-label" htmlFor={group}>Their name</label>}
              <input id={group} type="text" value={name} maxLength={60} autoComplete="off"
                     aria-label={step.title} placeholder="First and last name" disabled={busy}
                     onChange={(e) => setName(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); inputDone(name); } }} />
              <p className="pk-label pk-muted">
                {step.ask === 'sender' ? 'Shown in your list from now on · press Enter to continue'
                  : 'Press Enter, or pick a name'}
              </p>
              {people.length > 0 && (
                <div className="nl-people">
                  {people.map((p) => (
                    <button key={p} type="button" className="nl-person" disabled={busy}
                            onClick={() => { setName(p); inputDone(p); }}>{p}</button>
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
              <Choice type="checkbox" checked={remember} onChange={setRemember}
                      label={`Remember for deposits from ${it.txn.merchant}`} />
              <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                {choices.map((c) => (
                  <Choice key={c.value} name={group} checked={false} disabled={busy}
                          onChange={() => saveAsk(step, c.value, c.label)}
                          label={c.label} description={c.description} />
                ))}
              </div>
              {onTab && (
                <button type="button" className="txd-link nl-other" onClick={() => onTab('accounts')}>
                  Who shares this account <PIcon name="chevronRight" size={14} />
                </button>
              )}
            </>
          )}
          {step.ask === 'pick' && (
            <>
              <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                {step.candidates.map((c) => (
                  <Choice key={c.id} name={group} checked={false} disabled={busy}
                          onChange={() => saveAsk(step, c.id, `${c.merchant} · ${shortDate(c.date)}`)}
                          label={`${c.merchant} · ${shortDate(c.date)}`}
                          description={[txAmount(c.amount, { signed: true }), c.category].filter(Boolean).join(' · ')} />
                ))}
                {step.none && (
                  <Choice name={group} checked={false} disabled={busy}
                          onChange={() => saveAsk(step, '', step.none)} label={step.none} />
                )}
                {step.key === 'refund' && (
                  <Choice name={group} checked={cat !== '' && false} disabled={busy}
                          onChange={() => setCat(cat || ' ')} label="None of these" />
                )}
              </div>
              {step.key === 'refund' && cat !== '' && (
                <CategoryChips groups={spendingCats} value={cat.trim()} label="What was it a refund of?"
                               onChange={(v) => { setCat(v); saveAsk(step, '', `A refund of ${categoryLabel(v)}`); }} />
              )}
            </>
          )}
        </>
      )}
      <div className="nl-actions">
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
      </div>
    </>
  );
}

/**
 * The answers so far, each a row that reopens its step in place (R-11,
 * R-12 and the edit states on the Current design page): the open step's
 * options expand where the row was, the other rows stay, and tapping the
 * row again folds it back.
 */
export function Done({ path, flow, editing = null, busy = false, onOpen, onPick }) {
  if (!path.length) return null;
  return (
    <div className="nl-done-list">
      {path.map((p, i) => {
        const s = flow.S[p.step];
        const label = answerLabel(flow, p);
        const open = editing === i && !!s?.options;
        return (
          <div key={`${p.step}-${i}`} className={`nl-done-wrap${open ? ' open' : ''}`}>
            <button type="button" className="nl-done" disabled={!onOpen || !s?.options}
                    aria-expanded={s?.options ? open : undefined}
                    aria-label={open ? `Close: ${s.title}` : `Change: ${label}`}
                    onClick={() => onOpen?.(i)}>
              <span className="nl-done-ring" aria-hidden="true" />
              <span className="nl-done-label">{open ? s.title : label}</span>
              {s?.options && <PIcon name={open ? 'chevronUp' : 'chevronDown'} size={14} />}
            </button>
            {open && (
              <div className="pk-choices nl-reopen" role="radiogroup" aria-label={s.title}>
                {s.options.map((o) => (
                  <Choice key={o.v} name={`re-${p.step}-${i}`} checked={o.v === p.v} disabled={busy}
                          onChange={() => onPick?.(i, o.v)} label={o.label} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
