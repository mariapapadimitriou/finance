import { useEffect, useMemo, useState } from 'react';
import { Avatar, Choice, PButton, amountTone, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { RepaymentMatch } from './Splits.jsx';
import { depositChoices } from './joint.js';
import {
  INCOME_KINDS, confirmTx, dismissReview, getTxCases, linkPayback, markTx, searchCharges, setCategory,
  setIncomeType, setJointFrom, setParty, sortTransfers,
} from '../api.js';
import './stacked.css';

/**
 * The sort card (2026-10-21): the one way a transaction gets sorted, wherever
 * she is. Needs a look, a transaction's own panel, Quick sort and a
 * selection all render this card, so the questions, the options, the
 * control and the way back are the same every time.
 *
 *   - One option list. Every answer comes from the server's case list
 *     (finance/marks.py: 10 cases for money out, 11 for money in), with the
 *     same words and the same groups in every door. The card asks them one
 *     short step at a time (`mode: 'stacked'`, the default) or lays the whole
 *     list out at once, grouped, Pearl's best guess first (`mode: 'all'`).
 *   - One control, one commit. Every option is a radio row, and tapping it
 *     is the commit: an answer that needs more (a category, an account, a
 *     name, which purchase) slides that question in underneath; the last
 *     answer saves at once. A name commits with Enter or a person chip. The
 *     only button is Skip for now, where there is a queue to skip in.
 *   - One Remember. "Remember for <merchant>" is a checkbox above the choices
 *     it applies to, worded the same everywhere.
 *   - One way back. Undo sits at the right end of the dots' line and takes
 *     back the last answer; an answered row reopens its step in place, with
 *     the other answers still visible, and folds again on a second tap.
 *   - One ending. The last answer hands `commit` the call and the answers;
 *     the door around the card shows the Sorted card (SortedCard) with what
 *     it did and Next / Done.
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
const monthName = (iso) => MONTHS[Number(iso.slice(5, 7)) - 1] ?? '';

/** "e-Transfer to M. Papas" → "M. Papas". */
export function nameIn(text = '') {
  const m = text.match(/(?:e-?\s?transfer|interac)\s*(?:to|from)\s+(.+)$/i);
  return (m ? m[1] : '').replace(/\*+/g, '').trim();
}

const isOut = (it) => (it.txn?.amount ?? 0) > 0;

// What the server says about each transaction's answers, kept for the visit
// so opening Mark as… again — or straight after the panel opened — draws
// at once (2026-10-21). A saved answer drops its entry.
const CASES = new Map();
const READY = new Map();
export function loadCases(id) {
  if (!CASES.has(id)) {
    CASES.set(id, getTxCases(id)
      .then((d) => { READY.set(id, d); return d; })
      .catch((e) => { CASES.delete(id); throw e; }));
  }
  return CASES.get(id);
}
/** Start fetching a transaction's answers before Mark as… is pressed. */
export const prefetchCases = (id) => { loadCases(id).catch(() => {}); };
export const forgetCases = (id) => { CASES.delete(id); READY.delete(id); };

/**
 * The same list the server keeps (finance/marks.py OUT_CASES / IN_CASES),
 * used until getTxCases answers so the card never shows an empty list. The
 * server's copy wins once it arrives: it adds candidates and accounts and
 * drops the cases that don't apply.
 */
export const DEFAULT_GROUPS = {
  out: [{ key: 'spending', label: 'Spending' }, { key: 'not_spending', label: 'Not spending' }, { key: 'not_mine', label: 'Not mine' }],
  in: [{ key: 'income', label: 'Income' }, { key: 'not_income', label: 'Or it isn’t income' }],
};
export const DEFAULT_CASES = {
  out: [
    { key: 'spending', label: 'A purchase', group: 'spending', needs: 'category', effect: 'Counts as spending in a category you pick.', remember: 'merchant' },
    { key: 'bill', label: 'A bill', group: 'spending', needs: 'category', effect: 'Counts as spending, in Essentials, and Pearl plans for it next month.', remember: 'merchant' },
    { key: 'shared', label: 'Paid for a group', group: 'spending', needs: 'split', effect: 'The full amount counts as yours until they pay you back.', remember: null },
    { key: 'moved', label: 'Moved between my accounts', group: 'not_spending', needs: null, effect: 'A transfer. Not spending, not income.', remember: 'destination' },
    { key: 'saved', label: 'Put into savings', group: 'not_spending', needs: 'account', effect: 'Moved to one of your savings accounts. It isn’t spending, and it counts toward Savings this month.', remember: 'destination' },
    { key: 'lent', label: 'Lent to someone', group: 'not_spending', needs: null, effect: 'Lent. Not spending; Pearl watches for it coming back.', remember: 'merchant' },
    { key: 'paying_back', label: 'Paying back money I borrowed', group: 'not_spending', needs: 'borrowed', effect: 'Borrowed. Not spending.', remember: null },
    { key: 'work', label: 'A work expense, to be reimbursed', group: 'not_mine', needs: null, effect: 'Left out of your spending until the money comes back.', remember: null },
    { key: 'not_mine', label: 'Not mine', group: 'not_mine', needs: 'reason', effect: 'Left out of everything.', remember: 'exclusion' },
  ],
  in: [
    { key: 'pay', label: 'Pay', group: 'income', needs: 'income_kind', effect: 'Counts as income. Pick the kind: salary, bonus, benefits, interest or a refund of tax.', remember: null },
    { key: 'regular_pay', label: 'This is my regular pay', group: 'income', needs: null, effect: 'Pearl uses it for your monthly income from now on.', remember: null },
    { key: 'payback', label: 'Someone paying me back', group: 'not_income', needs: 'candidates', effect: 'Comes off what you spent for them. Never income.', remember: null },
    { key: 'refund', label: 'A refund', group: 'not_income', needs: 'refund', effect: 'Links to the purchase and comes off its category.', remember: null },
    { key: 'reimbursement', label: 'A reimbursement', group: 'not_income', needs: 'candidates', effect: 'Pays back a work expense you left out.', remember: null },
    { key: 'own', label: 'From my own account', group: 'not_income', needs: null, effect: 'A transfer. Not income.', remember: 'destination' },
    { key: 'out_of_savings', label: 'Taken out of my savings', group: 'not_income', needs: 'account', effect: 'Counts against Savings this month.', remember: 'destination' },
    { key: 'borrowed', label: 'Money I borrowed', group: 'not_income', needs: null, effect: 'Borrowed. Not income.', remember: null },
    { key: 'lent_back', label: 'Paying back money I lent', group: 'not_income', needs: null, effect: 'Moves it to Lent. Not income.', remember: null },
    { key: 'not_mine', label: 'Not mine', group: 'not_income', needs: 'reason', effect: 'Left out of everything.', remember: 'exclusion' },
  ],
};
/** The server's answer, or the default list until it comes. */
function withDefaults(it, cases) {
  const side = isOut(it) ? 'out' : 'in';
  const fill = (c) => ({ ...(DEFAULT_CASES[side].find((d) => d.key === c.key) ?? {}), ...c });
  if (cases?.cases?.length) {
    return { ...cases, cases: cases.cases.map(fill), groups: cases.groups?.length ? cases.groups : DEFAULT_GROUPS[side] };
  }
  return { ...(cases ?? {}), cases: DEFAULT_CASES[side].map((d) => ({ ...d })), groups: DEFAULT_GROUPS[side] };
}

// The short line each case folds into once answered.
export const DONE = {
  spending: 'Spending', bill: 'A bill', shared: 'Paid for a group', moved: 'Moved between my accounts',
  saved: 'Saved', lent: 'Lent', paying_back: 'Paying someone back', work: 'A work expense',
  not_mine: 'Not mine', saved_part: 'Part put away',
  pay: 'Income', regular_pay: 'My regular pay', payback: 'Paying me back', refund: 'A refund',
  reimbursement: 'A reimbursement', own: 'My own money', out_of_savings: 'Out of savings',
  borrowed: 'Borrowed', lent_back: 'Paying back money I lent', joint_them: 'Someone else put this in',
};

/** A server case as an option: where it leads is what it needs. */
function optionFor(c, { nameless = false } = {}) {
  const to = {
    category: 'cat', account: 'account', income_kind: 'kind', candidates: `pick_${c.key}`,
    refund: 'pick_refund', person: 'who_in', amount: 'amount', borrowed: 'borrowed', split: 'split',
  }[c.needs] ?? null;
  // Lent and paying someone back ask who (R-12); a payback with no name from
  // the bank asks who sent it first (R-09).
  const lead = c.key === 'lent' || c.key === 'paying_back' ? 'who_to'
    : c.key === 'payback' && nameless ? 'name' : to;
  return { v: c.key, label: c.label, done: DONE[c.key] ?? c.label, to: lead || undefined,
           effect: c.effect, case: c };
}

/**
 * The questions for one transaction, as steps. Each step has a title, what
 * it asks (choices, chips, a name…), and for each choice where it leads
 * (`to`) or nothing, when it's the last answer. `left` is how many steps
 * remain at most, counting this one, for the dots.
 *
 * `it` is a review item ({ kind, txn, guess, to, learnable, people, label })
 * or a bare { txn } from a panel; `cases` is getTxCases' answer; `mode` is
 * 'stacked' (one short question first) or 'all' (the whole list first).
 */
export function steps(it, cases, mode = 'stacked') {
  const out = isOut(it);
  const guess = it.guess && typeof it.guess === 'string' ? it.guess : '';
  cases = withDefaults(it, cases);
  const list = cases.cases;
  const nameless = it.kind === 'who_sent';
  const joint = it.kind === 'joint_in' || !!cases?.joint;
  const S = {};

  // ── Follow-ups, the same whichever door asked ───────────────────────
  S.cat = { title: 'What was it for?', left: 1, ask: 'category' };
  S.account = { title: out ? 'Which account did it go to?' : 'Which account did it come from?', left: 1, ask: 'account' };
  S.kind = { title: 'What kind of income?', left: 1, ask: 'kind' };
  S.who_to = { title: 'Who to?', left: 1, ask: 'name' };
  S.who_in = { title: 'Who put this in?', left: 1, ask: 'joint',
               sub: 'A deposit to your joint account. Until you answer, it counts as nothing.' };
  S.amount = { title: 'How much was put away?', left: 1, ask: 'amount' };
  S.borrowed = { title: 'What you bought with it', left: 1, options: [
    { v: 'counted', label: 'What I bought with it is already in Pearl', done: 'Already in Pearl' },
    { v: 'not_counted', label: 'What I bought with it isn’t in Pearl', done: 'Not in Pearl yet', to: 'cat' },
  ] };
  S.split = { title: 'Who was it with?', left: 1, ask: 'split' };
  for (const c of list) {
    if (c.needs === 'candidates') {
      S[`pick_${c.key}`] = { title: c.key === 'payback' ? 'Which purchase is it for?' : 'Which expense does it pay back?',
                             left: 1, ask: 'pick', key: c.key, candidates: c.candidates ?? [],
                             none: c.key === 'payback' ? 'None of these: money I lent' : null };
    }
    if (c.needs === 'refund') {
      S.pick_refund = { title: 'Which purchase is it a refund of?', left: 1, ask: 'pick', key: 'refund',
                        candidates: c.candidates ?? [] };
    }
  }
  S.name = { title: 'Who sent this?', left: S.pick_payback?.candidates.length ? 2 : 1, ask: 'sender',
             sub: 'Your bank left the name off. Pearl uses it to match paybacks.',
             to: S.pick_payback?.candidates.length ? 'pick_payback' : undefined };

  const groups = cases.groups;
  const best = list.find((c) => c.key === cases?.best);

  // ── The whole list at once (a transaction's panel, "It wasn’t a purchase") ──
  const rest = (skip) => list.filter((c) => !skip.includes(c.key)).map((c) => optionFor(c, { nameless }));
  S.all = {
    title: 'What was this?', left: 2,
    groups: [
      ...(best ? [{ key: 'best', label: 'Pearl’s best guess', options: [optionFor(best, { nameless })] }] : []),
      ...groups.map((g) => ({ key: g.key, label: g.label,
        options: list.filter((c) => c.group === g.key && c.key !== best?.key).map((c) => optionFor(c, { nameless })) })),
    ].filter((g) => g.options.length),
  };
  S.all.options = S.all.groups.flatMap((g) => g.options);

  if (mode === 'all') return { start: 'all', S };

  // ── One short question first (Needs a look, Quick sort) ──────────────
  if (out) {
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
    // Everything else the server knows, minus what the first question covered.
    S.what_out = { title: 'What was it?', left: 2, options: rest(['spending', 'saved']) };
    return { start: 'q1', S };
  }
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
  // A friend's message that names a purchase ("uber eats"), 2026-10-21:
  // asked first, one tap to link it.
  const said = !match && (it.guess?.action === 'memo' ? it.guess.charge : cases.memo_match);
  if (said) {
    const who = nameIn(it.txn.merchant) || it.txn.merchant;
    S.memo = {
      title: `Is ${who} paying you back for ${said.merchant}?`, left: 3, said,
      sub: `Their message says “${cases.memo || it.txn.memo || it.guess?.memo || ''}”.`,
      options: [
        { v: 'yes', label: `Yes, for ${said.merchant} · ${shortDate(said.date)}`,
          done: `Paying me back for ${said.merchant}`,
          effect: `${txAmount(said.amount, { signed: true })}${said.paid_back ? ` · ${txAmount(said.paid_back)} paid back so far` : ''}` },
        { v: 'other', label: 'Yes, for something else', done: 'Paying me back', to: 'pick_payback' },
        { v: 'no', label: 'No, it’s not a payback', done: 'Not a payback', to: 'q1' },
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
  S.what_in = { title: 'What was it?', left: 2, options: rest(['pay', 'regular_pay', 'own', 'joint_them']) };
  return { start: match ? 'match' : said ? 'memo' : 'q1', S };
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
        <span className="pk-label pk-muted">{`${txn.date ? longDate(txn.date) : ''}${where}`}</span>
        {/* An e-Transfer's message, when the bank passed it on. */}
        {txn.memo && <span className="nl-memo">“{txn.memo}”</span>}
      </div>
      <span className={`nl-tx-amt ${amountTone(inflow)}`}>{amount}</span>
    </div>
  );
}

/** The small pill at the end of the dots' line or above the card: "↶ Undo", "↶ Previous". */
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
  if (s?.options) return s.options.find((o) => o.v === p.v)?.done ?? p.label ?? p.v;
  return p.label ?? p.v;
}

/** The server case an answer on the path chose, if any. */
function caseOn(flow, path) {
  for (let i = path.length - 1; i >= 0; i -= 1) {
    const opt = flow.S[path[i].step]?.options?.find((o) => o.v === path[i].v);
    if (opt?.case) return opt.case;
  }
  return null;
}

export default function SortCard({ it, categories = [], busy, act, commit, onSkip, onBack, onTab, onSplit,
                                   mode = 'stacked', initialPath = null, initialEdit = null,
                                   initialName = '', showHead = true }) {
  const [cases, setCases] = useState(() => READY.get(it.txn.id) ?? null);
  // [{ step, v, label? }]: the answers so far, the last one still open.
  const [path, setPath] = useState(() => initialPath ?? []);
  // The row being changed in place (an index into `path`), if any.
  const [editing, setEditing] = useState(initialEdit);
  const [name, setName] = useState(() => initialName || nameIn(it.txn?.merchant) || it.to || '');
  const [cat, setCat] = useState('');
  const [amount, setAmount] = useState('');
  // "Which purchase?": what she typed, and what the server found for it.
  const [find, setFind] = useState('');
  const [found, setFound] = useState(null);
  const [remember, setRemember] = useState(it.kind === 'joint_in' || !!it.learnable);
  useEffect(() => {
    let live = true;
    loadCases(it.txn.id).then((d) => { if (live) setCases(d); }).catch(() => { if (live) setCases({ cases: [], groups: [] }); });
    return () => { live = false; };
  }, [it.txn.id]);

  const flow = useMemo(() => steps(it, cases, mode), [it, cases, mode]);
  const stepIdNow = path.length ? nextOf(flow, path[path.length - 1]) : flow.start;
  const picking = flow.S[stepIdNow]?.ask === 'pick' && flow.S[stepIdNow]?.key !== 'reimbursement';
  useEffect(() => {
    if (!picking) { setFound(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      searchCharges(it.txn.id, find).then((d) => { if (live) setFound(d.charges ?? []); }).catch(() => { if (live) setFound([]); });
    }, find ? 200 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [it.txn.id, find, picking]);
  const stepId = path.length ? nextOf(flow, path[path.length - 1]) : flow.start;
  const step = flow.S[stepId];
  const total = path.length + (step?.left ?? 1);
  const amt = txAmount(Math.abs(it.txn.amount));
  const out = isOut(it);
  const chosen = caseOn(flow, path);
  const byKey = (k) => withDefaults(it, cases).cases.find((c) => c.key === k);
  const answered = (k) => path.find((p) => p.step === k)?.v;

  // ── What an answer does, and saving it ───────────────────────────────
  const via = (body, title) => markTx(it.txn.id, body).then((res) => ({
    res, title: res?.title || title, detail: res?.detail || '', undo: res?.undo,
  }));
  const plain = (fn, title) => fn().then((res) => ({
    res, title: [title, res?.impact?.title].filter(Boolean).join(' ') || title,
    detail: res?.impact?.detail ?? res?.detail ?? '', undo: res?.undo,
  }));
  const spendingCats = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const accounts = cases?.accounts ?? [];
  const people = (cases?.people ?? []).filter((p) => p.toLowerCase() !== name.trim().toLowerCase());
  const jointChoices = depositChoices(it.people ?? cases?.joint_people ?? [], it.label ?? cases?.joint ?? '');
  // The Remember rule a case offers, worded one way everywhere.
  const rememberFor = (c) => (c?.remember ? `Remember for ${it.to || it.txn.merchant}` : null);
  const canRemember = (c) => !!(c?.remember || it.learnable || it.kind === 'category' || it.kind === 'panel');

  /** Commit the last answer: run the call, then hand the card to its door. */
  const finish = (answers, effect, run) => commit(() => { forgetCases(it.txn.id); return run(); }, {
    answers: answers.map((p) => ({ ...p, label: p.label ?? answerLabel(flow, p) })), effect,
  });
  const markCase = (c, extra = {}, answers, effect) => finish(answers, effect ?? c.effect,
    () => via({ case: c.key, ...(c.remember ? { remember: !!remember } : {}), ...extra }, `Sorted as ${c.label.toLowerCase()}.`));

  // The last answer of a step that asks (chips, an account, a kind…).
  const saveAsk = (s, v, label) => {
    const answers = [...path, { step: stepId, v, label }];
    const c = chosen;
    if (s.ask === 'category') {
      if (c?.needs === 'borrowed') return markCase(c, { counted: false, category: v }, answers, `Counts as ${categoryLabel(v)} spending.`);
      if (c?.key === 'bill') return markCase(c, { category: v }, answers, `Counts as ${categoryLabel(v)}, in Essentials. Pearl plans for it next month.`);
      if (c?.key === 'saved_part') return markCase(c, { category: v, amount: Number(amount) || 0 }, answers);
      if (c?.key === 'refund') return markCase(c, { category: v }, answers, `Comes off ${categoryLabel(v)}. Not income.`);
      if (c?.key === 'spending' || mode === 'all') return markCase(c ?? { key: 'spending', label: 'A purchase', remember: 'merchant' }, { category: v }, answers, `Counts as ${categoryLabel(v)} spending.`);
      const effect = `Counts as ${categoryLabel(v)} spending.`;
      const unsorted = it.kind === 'unsorted' || it.txn.category === 'Unsorted transfers';
      return finish(answers, effect, () => (unsorted
        ? plain(() => sortTransfers([it.txn.id], v, !!(it.learnable || it.kind === 'panel') && remember), `Sorted as ${categoryLabel(v)}.`)
        : plain(() => setCategory(it.txn.id, v, remember), `Moved to ${categoryLabel(v)}.`)));
    }
    if (s.ask === 'account') {
      const a = accounts.find((x) => x.id === v);
      if (!out || c?.key === 'out_of_savings') {
        return finish(answers, `Not income. It comes off Savings this month${a ? `, from ${a.label}` : ''}.`,
          () => via({ case: 'out_of_savings', account: v || '' }, 'Sorted as taken out of savings.'));
      }
      return finish(answers, `Not spending. It adds ${amt} to Savings this month${a?.anchor ? ' and to your Anchor' : ''}.`,
        () => via({ case: 'saved', account: v || '', remember: !!((it.learnable || c?.remember) && remember) },
          a ? `Put away to ${a.label}.` : 'Sorted as savings.'));
    }
    if (s.ask === 'kind') {
      if (v === 'regular_pay') return markCase(byKey('regular_pay') ?? { key: 'regular_pay', label: 'My regular pay' }, {}, answers, 'Pearl uses it for your monthly income from now on.');
      return finish(answers, `Counts as ${INCOME_KINDS[v] ?? 'income'}.`, () => (it.kind === 'income'
        ? plain(() => setIncomeType(it.txn.id, v), `Counts as ${INCOME_KINDS[v] ?? 'income'}.`)
        : via({ case: 'pay', income_kind: v }, 'Sorted as income.')));
    }
    if (s.ask === 'joint') {
      const ch = jointChoices.find((x) => x.value === v);
      const effect = ch?.who === 'me' ? 'A transfer, not income.'
        : `Covers ${ch?.label}’s share of joint spending. Your spending goes down by ${amt}.`;
      return finish(answers, effect, () => plain(() => setJointFrom(it.txn.id, ch.who, remember, ch.person), 'Sorted.'));
    }
    if (s.ask === 'pick') {
      const cand = s.candidates.find((x) => x.id === v) ?? (found ?? []).find((x) => x.id === v);
      if (s.key === 'payback' && !v) return finish(answers, 'Moves it to Lent. Not income.', () => via({ case: 'lent_back' }, 'Sorted as money you lent, paid back.'));
      if (s.key === 'refund' && v === '') return undefined;                 // a category comes next
      const effect = s.key === 'payback' ? `Comes off what you spent at ${cand?.merchant}. Not income.`
        : s.key === 'refund' ? `Comes off ${cand?.category || ''}. Not income.`
          : 'Pays back a work expense you left out. Not income.';
      const who = cand?.person || (s.key === 'payback' ? nameIn(it.txn.merchant) : '');
      return finish(answers, effect, () => via({ case: s.key, charge: v, ...(who ? { person: who } : {}) }, 'Sorted.'));
    }
    if (s.ask === 'name') {
      const how = c?.key || answered('what_out');
      const who = v.trim();
      const effect = how === 'lent'
        ? `Not spending. Allowance goes up by ${amt} and ${who} owes you ${amt}.`
        : `Not spending. Allowance goes up by ${amt}.`;
      return finish(answers, effect, async () => {
        const res = await markTx(it.txn.id, how === 'lent' ? { case: 'lent', remember: !!remember } : { case: 'paying_back', counted: true });
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
    if (s.ask === 'amount') {
      return undefined;                                                      // a category comes next
    }
    return undefined;
  };

  // The last answer of a step with choices.
  const saveChoice = (sId, v, pathBefore) => {
    const s = flow.S[sId];
    const opt = s.options.find((o) => o.v === v);
    const answers = [...pathBefore, { step: sId, v }];
    if (opt?.case) {
      const c = opt.case;
      if (c.key === 'moved' && (it.kind === 'unsorted' || it.txn.category === 'Unsorted transfers')) {
        return finish(answers, c.effect, () => plain(() => sortTransfers([it.txn.id], 'Transfers', it.learnable && remember), 'Sorted as moved between your accounts.'));
      }
      if (c.key === 'not_mine') return markCase(c, { reason: '' }, answers);
      return markCase(c, {}, answers);
    }
    if (sId === 'memo') {
      const who = nameIn(it.txn.merchant);
      return finish(answers, `Comes off what you spent at ${s.said.merchant}. Not income.`,
        () => via({ case: 'payback', charge: s.said.id, ...(who ? { person: who } : {}) },
          `Linked to ${s.said.merchant}. Not income.`));
    }
    if (sId === 'match') {
      return finish(answers, 'Not income. The split shows as paid back.',
        () => plain(() => linkPayback(s.match.charge_id, it.txn.id, s.match.name), 'Linked.'));
    }
    if (sId === 'q1' && out) {                                              // "Yes, Groceries"
      return finish(answers, `Stays in ${categoryLabel(it.guess)}.`, () => plain(() => confirmTx(it.txn.id), 'Confirmed.'));
    }
    if (sId === 'q1') {                                                     // my own money
      return finish(answers, 'A transfer. Not income.', () => (it.kind === 'joint_in'
        ? plain(() => setJointFrom(it.txn.id, 'me', false), 'Sorted as your own money.')
        : it.kind === 'income'
          ? plain(() => setCategory(it.txn.id, 'Transfers'), 'Sorted as your own money, not income.')
          : via({ case: 'own' }, 'Sorted as your own money.')));
    }
    if (sId === 'borrowed') {
      return markCase(chosen ?? byKey('paying_back'), { counted: true }, answers, 'Borrowed. Not spending.');
    }
    return undefined;
  };

  /** A choice tapped on the open question: lead on, or commit. */
  const choose = (v) => {
    const opt = step.options?.find((o) => o.v === v);
    if (opt?.to === 'split') { onSplit?.(); return; }
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
    if (now.to === 'split') { onSplit?.(); return; }
    if (!now.to) { saveChoice(sId, v, path.slice(0, i)); return; }
    if (now.to === was?.to) setPath(path.map((p, k) => (k === i ? { step: p.step, v } : p)));
    else setPath([...path.slice(0, i), { step: sId, v }]);
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
    if (step.ask === 'sender' && step.to) { setPath([...path, { step: stepId, v: who, label: who }]); return; }
    saveAsk(step, who, who);
  };
  const amountDone = () => {
    if (!(Number(amount) > 0)) return;
    setPath([...path, { step: stepId, v: amount, label: `${txAmount(Number(amount))} put away` }]);
    setAmount(amount);
  };
  const rememberBox = (c) => (canRemember(c) ? (
    <Choice type="checkbox" checked={remember} onChange={setRemember}
            label={rememberFor(c) || `Remember for ${it.to || it.txn.merchant}`} />
  ) : null);
  const optionRows = (options, nameAttr, onPick) => options.map((o) => (
    <Choice key={o.v} name={nameAttr} checked={false} disabled={busy}
            onChange={() => onPick(o.v)} label={o.label} description={o.effect} />
  ));

  return (
    <>
      {showHead && <TxHead txn={it.txn} name={it.to} />}
      <Progress done={path.length} total={total}
                trailing={(
                  <Pill className="nl-undo" onClick={undoLast} disabled={busy}
                        aria-label={path.length || editing !== null ? 'Undo the last answer' : 'Back to the list'}>
                    Undo
                  </Pill>
                )} />
      <Done path={path} flow={flow} editing={editing} busy={busy}
            onOpen={(i) => setEditing(editing === i ? null : i)} onPick={rechoose} />

      {/* The whole list (Mark as…) waits for the server's answers, whose best
          guess goes on top; one question at a time doesn't need to. */}
      {!cases && mode === 'all' && <CardSkeleton rows={6} />}
      {(cases || mode !== 'all') && step && (
        <>
          <h2 className="pk-h2 nl-q">{step.title}</h2>
          {step.sub && <p className="pk-muted nl-sub">{step.sub}</p>}
          {step.match && <RepaymentMatch match={step.match} />}

          {step.groups ? step.groups.map((g) => (
            <div key={g.key} className="nl-group">
              <p className="pk-overline">{g.label}</p>
              <div className="pk-choices" role="radiogroup" aria-label={g.label}>
                {optionRows(g.options, `${group}-${g.key}`, choose)}
              </div>
            </div>
          )) : step.options && (
            <div className="pk-choices" role="radiogroup" aria-label={step.title}>
              {optionRows(step.options, group, choose)}
            </div>
          )}
          {step.ask === 'category' && (
            <>
              {rememberBox(chosen)}
              <CategoryChips groups={spendingCats} value={cat} label={step.title}
                             onChange={(v) => { setCat(v); saveAsk(step, v, categoryLabel(v)); }} />
            </>
          )}
          {step.ask === 'account' && (
            <>
              {rememberBox(chosen)}
              <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                {accounts.map((a) => (
                  <Choice key={a.id} name={group} checked={false} disabled={busy} description={a.sub}
                          onChange={() => saveAsk(step, a.id, a.label)} label={a.label} />
                ))}
                <Choice name={group} checked={false} disabled={busy}
                        onChange={() => saveAsk(step, '', 'Somewhere Pearl can’t see')} label="Somewhere Pearl can’t see"
                        description={out ? 'Still counts as put away' : 'Still comes off what you put away'} />
              </div>
            </>
          )}
          {step.ask === 'kind' && (
            <div className="pk-choices nl-grid" role="radiogroup" aria-label={step.title}>
              {Object.entries(cases?.income_kinds ?? INCOME_KINDS).map(([k, label]) => (
                <Choice key={k} name={group} checked={it.kind === 'income' && it.guess === k} disabled={busy}
                        onChange={() => saveAsk(step, k, label)} label={label} />
              ))}
              <Choice name={group} checked={false} disabled={busy}
                      onChange={() => saveAsk(step, 'regular_pay', 'My regular pay')} label="This is my regular pay" />
            </div>
          )}
          {step.ask === 'amount' && (
            <div className="txd-field nl-name">
              <input id={group} type="number" inputMode="decimal" min="0.01" step="0.01" value={amount}
                     aria-label={step.title} placeholder="0.00" disabled={busy}
                     onChange={(e) => setAmount(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); amountDone(); } }} />
              <p className="pk-label pk-muted">Press Enter; the rest counts as spending</p>
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
                {step.ask === 'sender' ? 'Shown in your list from now on · press Enter to continue' : 'Press Enter, or pick a name'}
              </p>
              {people.length > 0 && (
                <div className="nl-people">
                  {people.map((p) => (
                    <button key={p} type="button" className="nl-person" disabled={busy}
                            onClick={() => { setName(p); inputDone(p); }}>{p}</button>
                  ))}
                </div>
              )}
              {step.ask === 'sender' && act && (
                <button type="button" className="txd-link nl-other" disabled={busy}
                        onClick={() => act(() => dismissReview(it.key), () => 'Kept your bank’s name')}>
                  Use your bank’s name instead
                </button>
              )}
            </div>
          )}
          {step.ask === 'joint' && (
            <>
              <Choice type="checkbox" checked={remember} onChange={setRemember} label={`Remember for ${it.txn.merchant}`} />
              <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                {jointChoices.map((c) => (
                  <Choice key={c.value} name={group} checked={false} disabled={busy}
                          onChange={() => saveAsk(step, c.value, c.label)} label={c.label} description={c.description} />
                ))}
              </div>
              {onTab && (
                <button type="button" className="txd-link nl-other" onClick={() => onTab('accounts')}>
                  Who shares this account <PIcon name="chevronRight" size={14} />
                </button>
              )}
            </>
          )}
          {step.ask === 'pick' && (() => {
            const seen = new Set(step.candidates.map((c) => c.id));
            const more = (found ?? []).filter((c) => !seen.has(c.id) || find);
            const shown = find ? (found ?? []) : step.candidates;
            const rowFor = (c, extra) => (
              <Choice key={`${c.id}|${c.person || ''}`} name={group} checked={false} disabled={busy}
                      onChange={() => saveAsk(step, c.id, `${c.merchant} · ${shortDate(c.date)}`)}
                      label={`${c.merchant} · ${shortDate(c.date)}`}
                      description={[txAmount(c.amount, { signed: true }), c.category,
                        c.person ? `${c.person}’s share` : null,
                        c.paid_back ? `${txAmount(c.paid_back)} paid back so far` : null,
                        c.memo ? 'what their message names' : null, extra].filter(Boolean).join(' · ')} />
            );
            return (
              <>
                {step.key !== 'reimbursement' && (
                  <div className="txd-field nl-find">
                    <input type="search" value={find} aria-label="Find the purchase" placeholder="Find by name or amount"
                           autoComplete="off" disabled={busy} onChange={(e) => setFind(e.target.value)} />
                  </div>
                )}
                <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                  {shown.map((c) => rowFor(c))}
                  {!find && more.slice(0, 6).map((c) => rowFor(c))}
                  {step.none && !find && (
                    <Choice name={group} checked={false} disabled={busy}
                            onChange={() => saveAsk(step, '', step.none)} label={step.none} />
                  )}
                  {step.key === 'refund' && !find && (
                    <Choice name={group} checked={false} disabled={busy}
                            onChange={() => setPath([...path, { step: stepId, v: '', label: 'None of these' }])}
                            label="None of these" description="Pick the category it comes off" />
                  )}
                  {find && found && !found.length && (
                    <p className="pk-muted">Nothing called “{find}” in the last six months of spending.</p>
                  )}
                  {step.key === 'reimbursement' && !step.candidates.length && (
                    <p className="pk-muted">Pearl can’t see a work expense this pays back yet. Mark the expense first, from its own page.</p>
                  )}
                </div>
              </>
            );
          })()}
          {step.ask === 'split' && (
            <PButton variant="secondary" disabled={busy} onClick={() => onSplit?.()}>Say who it was with</PButton>
          )}
        </>
      )}
      {onSkip && (
        <div className="nl-actions">
          <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>
        </div>
      )}
    </>
  );
}

/** The question's shape while its answers load: a title and ghost rows, so
 * the list doesn't arrive in two goes and jump (2026-10-21). */
function CardSkeleton({ rows = 3 }) {
  return (
    <div className="nl-skeleton" aria-busy="true" aria-label="Loading the choices">
      <span className="nl-ghost nl-ghost-title" />
      {Array.from({ length: rows }, (_, i) => <span key={i} className="nl-ghost nl-ghost-row" />)}
    </div>
  );
}

/**
 * The answers so far, each a row that reopens its step in place: the open
 * step's options expand where the row was, the other rows stay, and
 * tapping the row again folds it back.
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

/**
 * The Sorted card: every dot filled with "✓ Sorted", the answers as rows
 * (tap one to reopen that step), what the change did, and Next or Done.
 */
export function SortedCard({ entry, busy = false, isPast = false, nextLabel = 'Next', onNext, onUndo, onReopen,
                             showHead = true }) {
  const { it, answers } = entry;
  return (
    <>
      {showHead && (it.txn ? <TxHead txn={it.txn} name={it.to} /> : (
        <p className="pk-h3">{monthName(`${it.month}-01`)} had three paycheques</p>
      ))}
      <Progress done={answers.length} total={Math.max(answers.length, 1)} sorted
                trailing={onUndo && <Pill className="nl-undo" disabled={busy} onClick={onUndo} aria-label="Undo this change">Undo</Pill>} />
      {answers.length > 0 && (
        <div className="nl-done-list">
          {answers.map((a, i) => (
            <button key={`${a.step ?? i}-${i}`} type="button" className="nl-done" disabled={busy || !onReopen}
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
        {/* The same pill as Undo (2026-10-21), so the card's two ways out match. */}
        <button type="button" className="nl-pill nl-pill-go" disabled={busy} onClick={onNext}>
          {isPast ? 'Back to where I was' : nextLabel} <PIcon name="chevronRight" size={14} />
        </button>
      </div>
    </>
  );
}
