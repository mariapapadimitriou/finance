import { useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, Choice, PButton, amountTone, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { RepaymentMatch, SplitThis } from './Splits.jsx';
import { depositChoices } from './joint.js';
import {
  INCOME_KINDS, confirmTx, dismissReview, getTxCases, linkPayback, markTx, searchCharges, setCategory,
  setIncomeType, setJointFrom, setParty, setSplit, sortTransfers, undoChange,
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
 *     list out at once, as tiles (`mode: 'all'`).
 *   - One control, one commit. Every option is a radio row, and tapping it
 *     is the commit: an answer that needs more (a category, an account, a
 *     name, which purchase) slides that question in underneath; the last
 *     answer saves at once. A name commits with Enter or a person chip. The
 *     only button is Skip for now, where there is a queue to skip in.
 *   - One Remember. "Remember for <merchant>" is a checkbox on the Sorted
 *     card, above What changed (2026-10-23): she answers first, then decides
 *     whether every one like it goes the same way.
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
/** Regular pay's Remember (2026-10-28): a rule for every deposit from them. */
export function payWords(c, merchant = '') {
  if (c?.key !== 'regular_pay' || !c.remember) return null;
  const who = (c.remember_label || '').replace(/^Always count deposits from /, '').replace(/ as my regular pay$/, '')
    || merchant;
  return { label: c.remember_label || `Always count deposits from ${who} as my regular pay`,
           rule: `Every deposit from ${who} counts as your regular pay from now on.`,
           description: 'The ones already here and every new one count as income' };
}

export function nameIn(text = '') {
  const m = text.match(/(?:e-?\s?transfer|interac)\s*(?:to|from)\s+(.+)$/i);
  return (m ? m[1] : '').replace(/\*+/g, '').trim();
}

/** What a payback does (THL-260): a purchase nobody split becomes a split
 * with whoever sent it; one already split just has their part paid. */
export function paybackEffect(cand, who, amt, rest = '') {
  // Part of it (2026-10-26): the rest counts as money in.
  const tail = rest ? ` The other ${rest} counts as money in.` : '';
  if (who && cand && !cand.split) {
    return `${cand.merchant} becomes a split with ${who}. Their ${amt} comes off what you spent. Not income.${tail}`;
  }
  return `${rest ? `${amt} comes off` : 'Comes off'} what you spent at ${cand?.merchant}. Not income.${tail}`;
}

/** How much of money in paid a purchase back (2026-10-26): the number she
 * typed when it's a part, or null for all of it (or nothing sensible). */
export function paidPartOf(typed, whole) {
  const n = Math.round(Number(typed) * 100) / 100;
  if (!(n > 0) || n >= whole - 0.005) return null;
  return n;
}

/** One payback, several purchases (2026-10-28): each purchase picked takes
 * what's still unpaid on it, up to what's left of the money, in the order
 * picked. `left` is what's unpaid on a purchase (its `amount` when unsaid). */
export function allocatePicks(budget, picks) {
  let rest = Math.round(budget * 100) / 100;
  const rows = picks.map((c) => {
    const room = Math.max(0, Math.round(Number(c.left ?? c.amount) * 100) / 100);
    const use = Math.round(Math.min(room, Math.max(rest, 0)) * 100) / 100;
    rest = Math.round((rest - use) * 100) / 100;
    return { ...c, use };
  });
  const used = Math.round(rows.reduce((n, r) => n + r.use, 0) * 100) / 100;
  return { rows, used, left: Math.max(0, Math.round((budget - used) * 100) / 100) };
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
    { key: 'moved', label: 'Moved between my accounts', group: 'not_spending', needs: null, effect: 'Your own money moving, so it isn’t counted as spending or income.', remember: 'destination' },
    { key: 'saved', label: 'Put into savings', group: 'not_spending', needs: null, effect: 'Adds to your total saved. It isn’t spending.', remember: 'destination' },
    { key: 'lent', label: 'Lent to someone', group: 'not_spending', needs: null, effect: 'Not counted as spending. Pearl watches for it coming back.', remember: 'merchant' },
    { key: 'paying_back', label: 'Paying back money I borrowed', group: 'not_spending', needs: 'borrowed', effect: 'Paying back a loan, so it isn’t counted as spending.', remember: null },
    { key: 'work', label: 'A work expense, to be reimbursed', group: 'not_mine', needs: null, effect: 'Left out of your spending until the money comes back.', remember: null },
    { key: 'not_mine', label: 'Not mine', group: 'not_mine', needs: 'reason', effect: 'Left out of all your numbers.', remember: 'exclusion' },
  ],
  in: [
    { key: 'pay', label: 'Pay', group: 'income', needs: 'income_kind', effect: 'Counts as income. Pick the kind: salary, bonus, benefits, interest or a refund of tax.', remember: null },
    { key: 'regular_pay', label: 'This is my regular pay', group: 'income', needs: null, effect: 'Pearl uses it for your monthly income from now on.', remember: 'payer' },
    { key: 'payback', label: 'Someone paying me back', group: 'not_income', needs: 'candidates', effect: 'Comes off what you spent for them. Never income.', remember: null },
    { key: 'refund', label: 'A refund', group: 'not_income', needs: 'refund', effect: 'Links to the purchase and comes off its category.', remember: null },
    { key: 'reimbursement', label: 'A reimbursement', group: 'not_income', needs: 'candidates', effect: 'Pays back a work expense. Both leave your numbers.', remember: null },
    { key: 'own', label: 'From my own account', group: 'not_income', needs: null, effect: 'Your own money moving, so it isn’t counted as income.', remember: 'destination' },
    { key: 'cash', label: 'A cash deposit', group: 'not_income', needs: null, effect: 'Cash you put in, so it isn’t counted as income.', remember: null },
    { key: 'out_of_savings', label: 'Taken out of my savings', group: 'not_income', needs: null, effect: 'Comes off your total saved. It isn’t income.', remember: 'destination' },
    { key: 'borrowed', label: 'Money I borrowed', group: 'not_income', needs: null, effect: 'A loan, so it isn’t counted as income.', remember: null },
    { key: 'lent_back', label: 'Paying back money I lent', group: 'not_income', needs: null, effect: 'A friend paying back what you lent, so it isn’t counted as income.', remember: null },
    { key: 'not_mine', label: 'Not mine', group: 'not_income', needs: 'reason', effect: 'Left out of all your numbers.', remember: 'exclusion' },
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
  spending: 'Spending', bill: 'A bill', shared: 'Split with others', moved: 'Moved between my accounts',
  saved: 'Saved', lent: 'Lent', paying_back: 'Paying someone back', work: 'A work expense',
  not_mine: 'Not mine', saved_part: 'Part put away',
  pay: 'Income', regular_pay: 'My regular pay', payback: 'Paying me back', refund: 'A refund',
  reimbursement: 'A reimbursement', own: 'My own money', cash: 'A cash deposit', out_of_savings: 'Out of savings',
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
    : c.key === 'payback' && nameless ? 'name'
      // One savings bucket (2026-10-23): no account to pick.
      : c.key === 'saved' || c.key === 'out_of_savings' ? null : to;
  return { v: c.key, label: c.label, done: DONE[c.key] ?? c.label, to: lead || undefined,
           effect: c.effect, case: c };
}

/**
 * What was this? as tiles (2026-10-23): a word or two and an icon each, the
 * way categories are picked, with the choices that are one idea two ways
 * folded into one tile that asks which (own money: another account or
 * savings; a loan: which way; not mine: a work expense or not at all).
 */
const TILE = {
  spending: ['A purchase', 'cart'], bill: ['A bill', 'zap'], shared: ['Split with others', 'users'],
  saved_part: ['Part put away', 'target'],
  pay: ['Pay', 'banknote'], payback: ['Paid back', 'paidBack'], refund: ['A refund', 'refresh'],
  reimbursement: ['Reimbursed', 'laptop'], joint_them: ['Someone else’s', 'user'], not_mine: ['Not mine', 'ban'],
};
// An icon for each kind of income (2026-10-23).
const KIND_ICONS = {
  salary: 'banknote', regular_pay: 'clock', bonus: 'sparkle', interest: 'percent', gifts: 'gift',
  government: 'landmark', tax_refund: 'refresh', other: 'dots',
};
// The usual ones first, Other last.
const KIND_ORDER = ['salary', 'regular_pay', 'bonus', 'interest', 'gifts', 'government', 'tax_refund', 'other'];
const kindOrder = (k) => (KIND_ORDER.includes(k) ? KIND_ORDER.indexOf(k) : KIND_ORDER.length - 1);
const FOLDS = {
  out: [
    { id: 'own', label: 'My own money', icon: 'arrows', title: 'Where did it go?', keys: {
      moved: ['Another of my accounts', 'Not spending or income.'],
      saved: ['Into savings', 'Adds to your total saved.'] } },
    { id: 'loan', label: 'A loan', icon: 'landmark', title: 'Which way did it go?', keys: {
      lent: ['I lent it to someone', 'Pearl watches for it coming back.'],
      paying_back: ['I’m paying back a loan', 'Not spending.'] } },
    { id: 'not', label: 'Not mine', icon: 'ban', title: 'Whose was it?', keys: {
      work: ['A work expense', 'Left out until it’s reimbursed.'],
      not_mine: ['Not mine at all', 'Left out of all your numbers.'] } },
  ],
  in: [
    { id: 'own', label: 'My own money', icon: 'arrows', title: 'Where did it come from?', keys: {
      own: ['Another of my accounts', 'Not income.'],
      cash: ['A cash deposit', 'Not income.'],
      out_of_savings: ['Out of savings', 'Comes off your total saved.'] } },
    { id: 'loan', label: 'A loan', icon: 'landmark', title: 'Which way did it go?', keys: {
      borrowed: ['I borrowed it', 'Not income.'],
      lent_back: ['Paying back money I lent', 'Not income.'] } },
  ],
};

/** The tiles for a list of cases, adding a step for each folded tile that
 * holds two. `parent` names those steps (`all_own`, `what_out_loan`). */
export function tilesFor(list, S, { out, parent, nameless = false }) {
  const folds = FOLDS[out ? 'out' : 'in'];
  const tiles = [];
  const seen = new Set();
  const hasPay = list.some((c) => c.key === 'pay');
  for (const c of list) {
    if (c.key === 'regular_pay' && hasPay) continue;          // "What kind of income?" offers it
    const fold = folds.find((f) => c.key in f.keys);
    if (fold) {
      if (seen.has(fold.id)) continue;
      seen.add(fold.id);
      const members = list.filter((m) => m.key in fold.keys);
      if (members.length === 1) {
        tiles.push({ ...optionFor(members[0], { nameless }), label: fold.label, icon: fold.icon });
        continue;
      }
      const id = `${parent}_${fold.id}`;
      const options = members.map((m) => ({
        ...optionFor(m, { nameless }), label: fold.keys[m.key][0], done: fold.keys[m.key][0],
        effect: fold.keys[m.key][1] }));
      // The dots count what is left: one more step only if an answer leads on.
      S[id] = { title: fold.title, left: options.some((o) => o.to) ? 2 : 1, options };
      tiles.push({ v: `g:${fold.id}`, label: fold.label, icon: fold.icon, done: fold.label, to: id });
      continue;
    }
    const [label, icon] = TILE[c.key] ?? [c.label, 'dots'];
    tiles.push({ ...optionFor(c, { nameless }), label, icon });
  }
  return tiles;
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
  const nameless = it.kind === 'who_sent' || !!it.nameless;
  const joint = it.kind === 'joint_in' || !!cases?.joint;
  const S = {};

  // ── Follow-ups, the same whichever door asked ───────────────────────
  S.cat = { title: 'What was it for?', left: 1, ask: 'category' };
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
  // Who sent it, then which purchase, always (2026-10-26): with no likely
  // match the step still finds any purchase, and only part of the money
  // may have paid it back.
  S.name = { title: 'Who sent this?', left: S.pick_payback ? 2 : 1, ask: 'sender',
             sub: 'Your bank left the name off. Pearl uses it to match paybacks.',
             to: S.pick_payback ? 'pick_payback' : undefined };


  // ── Everything at once (a transaction's panel, "It wasn’t a purchase"):
  // ── Everything at once (a transaction's panel, "It wasn’t a purchase") ──
  const rest = (skip, parent) => tilesFor(list.filter((c) => !skip.includes(c.key)), S, { out, parent, nameless });
  // Every option laid out at once (2026-10-23), no guess card first.
  S.all = { title: 'What was this?', left: 2, tiles: true, options: rest([], 'all') };
  // "Split with others", unticked (2026-10-25): on the category step of a
  // purchase, ticking it goes on to who it was with, the category kept.
  // Not on a joint account, where whose it was is asked instead.
  const canSplit = out && list.some((c) => c.key === 'shared');
  S.cat.splittable = canSplit;
  S.cat_split = { title: 'What was it for?', left: 2, ask: 'category', to: 'split' };

  if (mode === 'all') return { start: 'all', S };

  // ── One short question first (Needs a look, Quick sort) ──────────────
  if (out) {
    const unsure = it.kind === 'category' && guess && guess !== 'Other';
    // Split with others is spending (2026-10-25), asked as a box on the
    // purchase answers, unticked: "Yes, Personal Care" with it ticked goes on
    // to who it was with (a hidden twin of the answer).
    S.q1 = unsure ? {
      title: `Is this ${categoryLabel(guess)}?`, left: 3, splittable: canSplit, splitFor: { yes: 'split' },
      options: [
        { v: 'yes', label: `Yes, ${categoryLabel(guess)}`, done: categoryLabel(guess) },
        { v: 'split', label: `Yes, ${categoryLabel(guess)}`, done: `${categoryLabel(guess)} · split`, to: 'split', hidden: true },
        { v: 'other', label: 'No, a different category', done: 'A different category', to: 'cat' },
        { v: 'else', label: 'It wasn’t a purchase', done: 'Not a purchase', to: 'what_out' },
      ],
    } : {
      // The box is on "What was it for?" next, where only purchases go.
      title: 'Was this spending?', left: 3,
      options: [
        { v: 'spent', label: 'Yes, I spent something', done: 'Spending', to: 'cat' },
        { v: 'saved', label: 'No, I saved it', done: 'Saved' },
        { v: 'else', label: 'No, something else', done: 'Something else', to: 'what_out' },
      ],
    };
    // Everything else the server knows, minus what the first question covered.
    S.what_out = { title: 'What was it?', left: 2, tiles: true, options: rest(['spending', 'saved', 'shared'], 'what_out') };
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
  // From someone else (2026-10-28): an e-Transfer or Wealthsimple Pay with
  // another person's name asks whether they're paying her back before
  // "Is this income?", whose first answers are about her own money.
  const top = it.guess?.action === 'payback' && it.guess.charge?.likely ? it.guess.charge : null;
  const person = !match && !said && it.kind === 'money_in' && !out && S.pick_payback ? it.from : null;
  if (person) {
    S.person = {
      title: `Is ${person} paying you back?`, left: 3, top,
      options: [
        ...(top ? [{ v: 'top', label: `Yes, for ${top.merchant} · ${shortDate(top.date)}`,
                     done: `Paying me back for ${top.merchant}`, effect: txAmount(top.amount, { signed: true }) }] : []),
        { v: 'yes', label: top ? 'Yes, for something else' : 'Yes, they’re paying me back',
          done: 'Paying me back', to: 'pick_payback' },
        { v: 'no', label: 'No, it’s not a payback', done: 'Not a payback', to: 'q1' },
      ],
    };
  }
  S.q1 = {
    title: 'Is this income?', left: nameless ? 3 : 2,
    options: [
      { v: 'income', label: 'Yes, it’s income', done: 'Income', to: 'kind' },
      { v: 'own', label: 'No, I moved my own money', done: 'My own money' },
      // A cash deposit (2026-10-26): her own cash, not income.
      { v: 'cash', label: 'No, it’s a cash deposit', done: 'A cash deposit' },
      { v: 'else', label: 'No, something else', done: 'Something else', to: joint ? 'who_in' : 'what_in' },
    ],
  };
  S.what_in = { title: 'What was it?', left: 2, tiles: true, options: rest(['pay', 'regular_pay', 'own', 'cash', 'joint_them'], 'what_in') };
  return { start: match ? 'match' : said ? 'memo' : person ? 'person' : 'q1', S };
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
export function Pill({ children, className = '', icon = 'undo', ...rest }) {
  return (
    <button type="button" className={`nl-pill ${className}`} {...rest}>
      <PIcon name={icon} size={14} /> {children}
    </button>
  );
}

/** Where an answer leads. */
export function nextOf(flow, last) {
  const s = flow.S[last.step];
  if (s?.options) return s.options.find((o) => o.v === last.v)?.to;
  return s?.to;
}

/** Whether every answer is one of this card's steps (2026-10-25). */
export function validPath(flow, path) {
  return path.every((p) => !!flow.S[p.step]);
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

export default function SortCard({ it, categories = [], busy, act, commit, onSkip, onBack, onTab, onSplit, onPrevious,
                                   mode = 'stacked', initialPath = null, initialEdit = null,
                                   initialName = '', initialPick = null, showHead = true }) {
  const [cases, setCases] = useState(() => READY.get(it.txn.id) ?? null);
  // [{ step, v, label? }]: the answers so far, the last one still open.
  const [path, setPath] = useState(() => initialPath ?? []);
  // The row being changed in place (an index into `path`), if any.
  const [editing, setEditing] = useState(initialEdit);
  const [name, setName] = useState(() => initialName || nameIn(it.txn?.merchant) || it.to || '');
  const [cat, setCat] = useState('');
  // Split with others, asked on the purchase answers; no unless ticked.
  const [splitOn, setSplitOn] = useState(false);
  const [amount, setAmount] = useState('');
  // "Which purchase?": what she typed, and what the server found for it.
  const [find, setFind] = useState('');
  // Paid back: how much of it, all of it to start (2026-10-26).
  const [paidPart, setPaidPart] = useState(() => Math.abs(it.txn?.amount ?? 0).toFixed(2));
  // The purchases picked for a payback, in the order picked (2026-10-28).
  const [picks, setPicks] = useState([]);
  const [found, setFound] = useState(null);
  // Remember is asked on the last card, after the answer (2026-10-23),
  // unticked: a rule is hers to choose, never a default. The saving call
  // reads it here, so it can be run again with Remember on or off.
  const rememberRef = useRef(false);
  const rem = () => rememberRef.current;
  useEffect(() => {
    let live = true;
    loadCases(it.txn.id).then((d) => { if (live) setCases(d); }).catch(() => { if (live) setCases({ cases: [], groups: [] }); });
    return () => { live = false; };
  }, [it.txn.id]);

  const flow = useMemo(() => steps(it, cases, mode), [it, cases, mode]);
  // Answers that don't belong to this card's steps (a reopened card built
  // another way) start it over instead of leaving it blank (2026-10-25).
  useEffect(() => {
    if (cases && path.length && !validPath(flow, path)) { setPath([]); setEditing(null); }
  }, [cases, flow, path]);
  const stepIdNow = path.length ? nextOf(flow, path[path.length - 1]) : flow.start;
  // Any of her charges can be found (2026-10-23), a reimbursement's too:
  // no need to mark the expense first.
  const picking = flow.S[stepIdNow]?.ask === 'pick';
  useEffect(() => {
    if (!picking) { setFound(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      searchCharges(it.txn.id, find).then((d) => { if (live) setFound(d.charges ?? []); }).catch(() => { if (live) setFound([]); });
    }, find ? 200 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [it.txn.id, find, picking]);
  // A new card or step starts with nothing picked (2026-10-28).
  useEffect(() => { setPicks([]); }, [it.txn.id, stepIdNow]);
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
  // A split counts toward a category: an unsorted transfer picks one first.
  const needsCat = !it.txn.category || ['Unsorted transfers', 'Other'].includes(it.txn.category);
  // The category picked before the split (2026-10-25), when Split was ticked.
  const splitCat = path.find((p) => p.step === 'cat_split')?.v || '';
  const askCat = needsCat && !splitCat;
  const spendingCats = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const people = (cases?.people ?? []).filter((p) => p.toLowerCase() !== name.trim().toLowerCase());
  const jointChoices = depositChoices(it.people ?? cases?.joint_people ?? [], it.label ?? cases?.joint ?? '');
  // The Remember rule a case offers, worded one way everywhere.
  const canRemember = (c) => !!(c?.remember || it.learnable || it.kind === 'category' || it.kind === 'panel');

  /** Commit the last answer: run the call, then hand the card to its door. */
  // What the Sorted card says about her rule (2026-10-22): only when one was
  // saved — the server says so for a mark; a category call trusts the box.
  const ruleText = `Pearl will do the same for every ${it.to || it.txn.merchant} from now on.`;
  // Whether an answer can become a rule at all: not an e-Transfer with no
  // name (its reference changes every time), not an unsorted transfer Pearl
  // can't learn from.
  const ruleOk = it.kind !== 'who_sent' && !it.nameless && !(it.kind === 'unsorted' && !it.learnable)
    // Not for a name every transfer shares, like "Interac e-Transfer" (2026-10-23).
    && cases?.learnable !== false;
  // `words` (2026-10-28): a case's own Remember wording, like regular pay's
  // "Always count deposits from Acme as my regular pay".
  const finish = (answers, effect, run, ruleable = false, words = null) => {
    const go = (on) => {
      rememberRef.current = on;
      forgetCases(it.txn.id);
      return run().then((r) => ({ ...r, rule: (r?.res?.remember ?? on) ? (words?.rule ?? ruleText) : '' }));
    };
    return commit(() => go(false), {
      answers: answers.map((p) => {
        const st = flow.S[p.step];
        const [vis, at] = st?.options ? shownOptions(st.options, p.v) : [null, p.v];
        return { ...p, label: p.label ?? answerLabel(flow, p), title: st?.title, marked: at,
                 options: vis?.map((o) => ({ v: o.v, label: o.label })) };
      }), effect,
      remember: ruleable && ruleOk ? { label: words?.label ?? `Remember for ${it.to || it.txn.merchant}`,
                                       description: words?.description, redo: go } : null,
    });
  };
  const markCase = (c, extra = {}, answers, effect) => finish(answers, effect ?? c.effect,
    () => via({ case: c.key, ...(c.remember ? { remember: !!rem() } : {}), ...extra }, `Sorted as ${c.label.toLowerCase()}.`),
    !!c.remember, payWords(c, it.txn.merchant));

  // One savings bucket (2026-10-23): saved, or taken out, with no account.
  const saveSavings = (answers, into) => finish(answers,
    into ? `Adds ${amt} to your total saved. It isn’t spending.` : `Takes ${amt} off your total saved. It isn’t income.`,
    () => via({ case: into ? 'saved' : 'out_of_savings', remember: !!rem() },
      into ? 'Put into savings.' : 'Taken out of savings.'), !!byKey(into ? 'saved' : 'out_of_savings')?.remember);

  // The last answer of a step that asks (chips, a kind…).
  const saveAsk = (s, v, label) => {
    setEditing(null);
    const answers = [...path, { step: stepId, v, label }];
    const c = chosen;
    // Split ticked on a purchase's category: who it was with comes next.
    if (s.ask === 'category' && splitOn && s.splittable && (!c || c.key === 'spending')) {
      setPath([...path, { step: 'cat_split', v, label }]);
      return undefined;
    }
    if (s.ask === 'category') {
      if (c?.needs === 'borrowed') return markCase(c, { counted: false, category: v }, answers, `Counts as ${categoryLabel(v)} spending.`);
      if (c?.key === 'bill') return markCase(c, { category: v }, answers, `Counts as ${categoryLabel(v)}, in Essentials. Pearl plans for it next month.`);
      if (c?.key === 'saved_part') return markCase(c, { category: v, amount: Number(amount) || 0 }, answers);
      if (c?.key === 'refund') return markCase(c, { category: v }, answers, `Comes off ${categoryLabel(v)}. Not income.`);
      if (c?.key === 'spending' || mode === 'all') return markCase(c ?? { key: 'spending', label: 'A purchase', remember: 'merchant' }, { category: v }, answers, `Counts as ${categoryLabel(v)} spending.`);
      const effect = `Counts as ${categoryLabel(v)} spending.`;
      const unsorted = it.kind === 'unsorted' || it.txn.category === 'Unsorted transfers';
      return finish(answers, effect, () => (unsorted
        ? plain(() => sortTransfers([it.txn.id], v, !!(it.learnable || it.kind === 'panel') && rem()), `Sorted as ${categoryLabel(v)}.`)
        : plain(() => setCategory(it.txn.id, v, rem()), `Moved to ${categoryLabel(v)}.`)), canRemember(c));
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
      return finish(answers, effect, () => plain(() => setJointFrom(it.txn.id, ch.who, rem(), ch.person), 'Sorted.'), true);
    }
    if (s.ask === 'pick' && s.key === 'payback' && Array.isArray(v)) {   // several purchases
      const typed = (answered('name') || '').trim();
      const who = v[0]?.person || typed || it.from || nameIn(it.txn.merchant);
      const whole = Math.abs(it.txn.amount);
      const part = paidPartOf(paidPart, whole);
      const { rows, used } = allocatePicks(part ?? whole, v);
      const names = [...new Set(rows.map((r) => r.merchant))];
      const effect = `Comes off what you spent on ${rows.length} purchases${names.length === 1 ? ` at ${names[0]}` : ''}. Not income.`
        + (whole - used > 0.005 ? ` The other ${txAmount(whole - used)} counts as money in.` : '');
      const answersMany = [...path, { step: stepId, v: rows.map((r) => r.id).join(','),
                                              label: `${rows.length} purchases · ${txAmount(used)}` }];
      return finish(answersMany, effect, async () => {
        if (typed) await setParty(it.txn.id, typed).catch(() => {});
        return via({ case: 'payback', charges: rows.map((r) => ({ id: r.id, amount: r.use })),
                     ...(who ? { person: who } : {}), ...(part ? { amount: part } : {}) }, 'Sorted.');
      });
    }
    if (s.ask === 'pick') {
      const cand = s.candidates.find((x) => x.id === v) ?? (found ?? []).find((x) => x.id === v);
      if (s.key === 'payback' && !v) return finish(answers, 'A friend paying back what you lent, so it isn’t counted as income.', () => via({ case: 'lent_back' }, 'Sorted as money you lent, paid back.'));
      if (s.key === 'refund' && v === '') return undefined;                 // a category comes next
      // The name she typed on "Who sent this?", when the bank left it off.
      const typed = s.key === 'payback' ? (answered('name') || '').trim() : '';
      const who = cand?.person || (s.key === 'payback' ? typed || it.from || nameIn(it.txn.merchant) : '');
      const whole = Math.abs(it.txn.amount);
      const part = s.key === 'payback' ? paidPartOf(paidPart, whole) : null;
      const effect = s.key === 'payback'
        ? paybackEffect(cand, who, part ? txAmount(part) : amt, part ? txAmount(whole - part) : '')
          : s.key === 'refund' ? `Comes off ${cand?.category || ''}. Not income.`
            : 'Pays back a work expense. Not income.';
      return finish(answers, effect, async () => {
        if (typed) await setParty(it.txn.id, typed).catch(() => {});
        return via({ case: s.key, charge: v, ...(who ? { person: who } : {}), ...(part ? { amount: part } : {}) }, 'Sorted.');
      });
    }
    if (s.ask === 'name') {
      const how = c?.key || answered('what_out');
      const who = v.trim();
      const effect = how === 'lent'
        ? `Not spending. Allowance goes up by ${amt} and ${who} owes you ${amt}.`
        : `Not spending. Allowance goes up by ${amt}.`;
      return finish(answers, effect, async () => {
        const res = await markTx(it.txn.id, how === 'lent' ? { case: 'lent', remember: !!rem() } : { case: 'paying_back', counted: true });
        if (who && who !== nameIn(it.txn.merchant)) await setParty(it.txn.id, who).catch(() => {});
        return { res, title: res?.title || (how === 'lent' ? `Lent to ${who}.` : `Paying back ${who}.`),
                 detail: res?.detail || '', undo: res?.undo };
      }, how === 'lent');
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
      if (c.key === 'saved' || c.key === 'out_of_savings') return saveSavings(answers, c.key === 'saved');
      if (c.key === 'moved' && (it.kind === 'unsorted' || it.txn.category === 'Unsorted transfers')) {
        return finish(answers, c.effect, () => plain(() => sortTransfers([it.txn.id], 'Transfers', !!rem()), 'Sorted as moved between your accounts.'), true);
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
    if (sId === 'person' && v === 'top') {
      return finish(answers, `Comes off what you spent at ${s.top.merchant}. Not income.`,
        () => via({ case: 'payback', charge: s.top.id, person: it.from },
          `Linked to ${s.top.merchant}. Not income.`));
    }
    if (sId === 'match') {
      return finish(answers, 'Not income. The split shows as paid back.',
        () => plain(() => linkPayback(s.match.charge_id, it.txn.id, s.match.name), 'Linked.'));
    }
    if (sId === 'q1' && out && v === 'saved') {                             // "No, I saved it"
      return saveSavings(answers, true);
    }
    if (sId === 'q1' && out) {                                              // "Yes, Groceries"
      return finish(answers, `Stays in ${categoryLabel(it.guess)}.`, () => (rem()
        ? plain(() => setCategory(it.txn.id, it.guess, true), `${categoryLabel(it.guess)} for every ${it.to || it.txn.merchant}.`)
        : plain(() => confirmTx(it.txn.id), 'Confirmed.')), true);
    }
    if (sId === 'q1' && v === 'cash') {                                     // a cash deposit
      return finish(answers, 'Cash you put in, so it isn’t counted as income.', () => (it.kind === 'joint_in'
        ? plain(() => setJointFrom(it.txn.id, 'me', false), 'Sorted as a cash deposit.')
        : via({ case: 'cash' }, 'Sorted as a cash deposit.')));
    }
    if (sId === 'q1') {                                                     // my own money
      return finish(answers, 'Your own money moving, so it isn’t counted as income.', () => (it.kind === 'joint_in'
        ? plain(() => setJointFrom(it.txn.id, 'me', rem()), 'Sorted as your own money.')
        : it.kind === 'income'
          ? plain(() => setCategory(it.txn.id, 'Transfers', rem()), 'Sorted as your own money, not income.')
          : via({ case: 'own', remember: !!rem() }, 'Sorted as your own money.')), true);
    }
    if (sId === 'borrowed') {
      return markCase(chosen ?? byKey('paying_back'), { counted: true }, answers, 'Paying back a loan, so it isn’t counted as spending.');
    }
    return undefined;
  };

  /** A choice tapped on the open question: lead on, or commit. */
  const choose = (picked) => {
    setEditing(null);                       // a reopened row folds when the open question is answered
    const v = splitOn && step.splitFor?.[picked] ? step.splitFor[picked] : picked;
    const opt = step.options?.find((o) => o.v === v);
    // Split with others: its own page where the door has one (a
    // transaction's panel); otherwise the next step in this card
    // (2026-10-23), so she never leaves it.
    if (opt?.to === 'split' && onSplit) { onSplit(); return; }
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
    if (now.to === 'split' && onSplit) { onSplit(); return; }
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

  // A different answer picked on the Sorted card (2026-10-23): the change
  // was undone and the card reopened at that step; the new answer goes in.
  const picked = useRef(false);
  useEffect(() => {
    if (picked.current || !initialPick || stepId !== initialPick.step) return;
    picked.current = true;
    choose(initialPick.v);
  });
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
  const optionRows = (options, nameAttr, onPick) => options.filter((o) => !o.hidden).map((o) => (
    <Choice key={o.v} name={nameAttr} checked={false} disabled={busy}
            onChange={() => onPick(o.v)} label={o.label} description={o.effect} />
  ));

  return (
    <>
      {showHead && <TxHead txn={it.txn} name={it.to} />}
      {/* Undo only once there is an answer to take back (2026-10-22); before
          that, the back link above the card is the way out. */}
      <Progress done={path.length} total={total}
                trailing={(path.length > 0 || editing !== null) ? (
                  <Pill className="nl-undo" onClick={undoLast} disabled={busy} aria-label="Undo the last answer">
                    Undo
                  </Pill>
                ) : null} />
      <Done path={path} flow={flow} editing={editing} busy={busy}
            onOpen={(i) => setEditing(editing === i ? null : i)} onPick={rechoose} />

      {/* The whole list (Mark as…) waits for the server's answers, whose
          guess goes on top; one question at a time doesn't need to. */}
      {!cases && mode === 'all' && <CardSkeleton rows={6} />}
      {(cases || mode !== 'all') && step && (
        // Keyed by the step (2026-10-23): each new question slides in.
        <div className="nl-step" key={`${stepId}-${path.length}`}>
          <h2 className="pk-h2 nl-q">{step.title}</h2>
          {step.sub && <p className="pk-muted nl-sub">{step.sub}</p>}
          {step.match && <RepaymentMatch match={step.match} />}
          {step.splittable && (!chosen || chosen.key === 'spending') && (
            <Choice type="checkbox" checked={splitOn} disabled={busy} onChange={(on) => setSplitOn(on)}
                    icon="users" label="Split with others" />
          )}
          {step.tiles ? (
            <div className="nl-tiles" role="radiogroup" aria-label={step.title}>
              {step.options.map((o) => (
                <button key={o.v} type="button" role="radio" aria-checked="false" className="pk-ctile nl-tile"
                        disabled={busy} onClick={() => choose(o.v)}>
                  <span className="pk-ctile-icon" aria-hidden="true"><PIcon name={o.icon || 'dots'} size={20} /></span>
                  <span className="pk-ctile-label">{o.label}</span>
                </button>
              ))}
            </div>
          ) : step.groups ? step.groups.map((g) => (
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
            <CategoryChips groups={spendingCats} value={cat} label={step.title}
                           onChange={(v) => { setCat(v); saveAsk(step, v, categoryLabel(v)); }} />
          )}
          {step.ask === 'kind' && (
            // Tiles with an icon each (2026-10-23), like What was this?;
            // Pearl's guess has the dashed outline the category tiles use.
            <div className="nl-tiles" role="radiogroup" aria-label={step.title}>
              {[...Object.entries(cases?.income_kinds ?? INCOME_KINDS), ['regular_pay', 'My regular pay']]
                .sort((a, b) => kindOrder(a[0]) - kindOrder(b[0])).map(([k, label]) => (
                <button key={k} type="button" role="radio" aria-checked="false" disabled={busy}
                        className={`pk-ctile nl-tile${it.kind === 'income' && it.guess === k ? ' guess' : ''}`}
                        aria-label={it.kind === 'income' && it.guess === k ? `${label}, Pearl’s guess` : label}
                        onClick={() => saveAsk(step, k, label)}>
                  <span className="pk-ctile-icon" aria-hidden="true"><PIcon name={KIND_ICONS[k] || 'dots'} size={20} /></span>
                  <span className="pk-ctile-label">{label}</span>
                </button>
              ))}
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
              <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                {jointChoices.map((c) => (
                  <Choice key={c.value} name={group} checked={false} disabled={busy}
                          onChange={() => saveAsk(step, c.value, c.label)} label={c.label} description={c.description} />
                ))}
              </div>
              {onTab && (
                <button type="button" className="txd-link nl-other" onClick={() => onTab('accounts', { path })}>
                  Who shares this account <PIcon name="chevronRight" size={14} />
                </button>
              )}
            </>
          )}
          {step.ask === 'pick' && (() => {
            const seen = new Set(step.candidates.map((c) => c.id));
            const more = (found ?? []).filter((c) => !seen.has(c.id) || find);
            const shown = find ? (found ?? []) : step.candidates;
            // A payback can cover several purchases (2026-10-28): pick them
            // one by one; each takes what's unpaid on it, and once the money
            // is used up nothing else can be picked.
            const many = step.key === 'payback';
            const whole = Math.abs(it.txn.amount);
            const budget = paidPartOf(paidPart, whole) ?? whole;
            const alloc = allocatePicks(budget, picks);
            const keyOf = (c) => `${c.id}|${c.person || ''}`;
            const pickedRow = (c) => alloc.rows.find((r) => keyOf(r) === keyOf(c));
            const roomOf = (c) => Number(c.left ?? c.amount);
            const toggle = (c) => {
              if (pickedRow(c)) { setPicks(picks.filter((p) => keyOf(p) !== keyOf(c))); return; }
              // One purchase that takes all of it links straight away, as before.
              if (!picks.length && roomOf(c) >= budget - 0.005) {
                saveAsk(step, c.id, `${c.merchant} · ${shortDate(c.date)}`);
                return;
              }
              setPicks([...picks.filter((p) => p.id !== c.id), c]);
            };
            const rowFor = (c, extra) => {
              const on = many ? pickedRow(c) : null;
              const paidUp = many && roomOf(c) <= 0.005;
              const full = many && !on && alloc.left <= 0.005 && picks.length > 0;
              return (
                <Choice key={keyOf(c)} type={many ? 'checkbox' : 'radio'} name={group} checked={!!on}
                        disabled={busy || paidUp || full}
                        onChange={() => (many ? toggle(c) : saveAsk(step, c.id, `${c.merchant} · ${shortDate(c.date)}`))}
                        label={`${c.merchant} · ${shortDate(c.date)}`}
                        description={[txAmount(c.amount, { signed: true }), c.category,
                          c.person ? `${c.person}’s share` : null,
                          paidUp ? 'already paid back' : c.paid_back ? `${txAmount(c.paid_back)} paid back so far` : null,
                          on ? `${txAmount(on.use)} of this payback` : null,
                          c.memo ? 'what their message names' : null, extra].filter(Boolean).join(' · ')} />
              );
            };
            return (
              <>
                {step.key === 'payback' && (
                  // Not always all of it (2026-10-26): the rest counts as money in.
                  <div className="txd-field nl-paid-part">
                    <label className="pk-label" htmlFor={`${group}-part`}>How much of it was paying you back?</label>
                    <input id={`${group}-part`} type="number" inputMode="decimal" min="0.01" step="0.01"
                           max={Math.abs(it.txn.amount)} value={paidPart} disabled={busy}
                           onChange={(e) => setPaidPart(e.target.value)} />
                    {paidPartOf(paidPart, Math.abs(it.txn.amount)) && (
                      <p className="pk-label pk-muted">
                        {`The other ${txAmount(Math.abs(it.txn.amount) - paidPartOf(paidPart, Math.abs(it.txn.amount)))} counts as money in`}
                      </p>
                    )}
                  </div>
                )}
                <div className="txd-field nl-find">
                  <input type="search" value={find} aria-label="Find the purchase" placeholder="Find by name or amount"
                         autoComplete="off" disabled={busy} onChange={(e) => setFind(e.target.value)} />
                </div>
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
                  {many && picks.length > 0 && (
                    <div className="nl-picked" role="status">
                      <p className="nl-picked-total">
                        <strong>{`${txAmount(alloc.used)} of ${txAmount(budget)}`}</strong>
                        {` · ${alloc.rows.length} ${alloc.rows.length === 1 ? 'purchase' : 'purchases'}`}
                      </p>
                      <p className="pk-label pk-muted">
                        {alloc.left > 0.005
                          ? `${txAmount(alloc.left)} left. Pick another, or link these and the rest counts as money in.`
                          : 'All of it is used. Untick one to pick a different purchase.'}
                      </p>
                      <PButton disabled={busy} onClick={() => saveAsk(step, alloc.rows, `${alloc.rows.length} purchases`)}>
                        {`Link ${alloc.rows.length === 1 ? 'this purchase' : `these ${alloc.rows.length} purchases`}`}
                      </PButton>
                    </div>
                  )}
                  {!find && found && !found.length && !step.candidates.length && (
                    <p className="pk-muted">No spending in the last six months to link it to.</p>
                  )}
                </div>
              </>
            );
          })()}
          {step.ask === 'split' && (onSplit ? (
            <PButton variant="secondary" disabled={busy} onClick={() => onSplit()}>Say who it was with</PButton>
          ) : (
            <>
              {/* No category yet (an unsorted transfer): what it was for, first. */}
              {askCat && (
                <CategoryChips groups={spendingCats} value={cat} label="What was it for?" onChange={setCat} />
              )}
              {(!askCat || cat) && (
                <SplitThis tx={{ full_amount: Math.abs(it.txn.amount), splitting: null,
                                 category: categoryLabel(splitCat || cat || it.txn.category) }}
                           busy={busy}
                           onSave={(split) => {
                             const theirs = split.people.reduce((a, p) => a + (Number(p.amount) || 0), 0);
                             const yours = Math.max(0, Math.abs(it.txn.amount) - theirs);
                             const who = split.people.map((p) => p.name).join(', ');
                             // One answer for the step, so Undo reopens it.
                             const picked = splitCat || (askCat ? cat : '');
                             const answers = [...path, { step: stepId, v: 'split',
                               label: `${askCat ? `${categoryLabel(cat)} · ` : ''}Split with ${who}` }];
                             finish(answers, `Only your share counts: ${txAmount(yours)}.`, () => setSplit(it.txn.id,
                               { ...split, settle: true, ...(picked ? { category: picked } : {}) })
                               .then((res) => ({ res, title: `Split with ${who}.`,
                                                 detail: `Only your share counts: ${txAmount(yours)}.`, undo: res?.undo })));
                           }} />
              )}
            </>
          ))}
        </div>
      )}
      {/* Back on the left, forward on the right (2026-10-22). */}
      {(onSkip || onPrevious) && (
        <div className="nl-actions nl-bottom">
          {onPrevious && (
            <Pill icon="arrowLeft" className="nl-previous" disabled={busy} onClick={onPrevious} aria-label="Previous transaction">
              Previous
            </Pill>
          )}
          {onSkip && <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>Skip for now</PButton>}
        </div>
      )}
    </>
  );
}

const FOLD_MS = 220;

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
  // The row whose options are drawn: the open one, or the one folding shut
  // (kept for the slide, 2026-10-23).
  const [shown, setShown] = useState(editing);
  useEffect(() => {
    if (editing !== null) { setShown(editing); return undefined; }
    const t = setTimeout(() => setShown(null), FOLD_MS);
    return () => clearTimeout(t);
  }, [editing]);
  if (!path.length) return null;
  return (
    <div className="nl-done-list">
      {path.map((p, i) => {
        const s = flow.S[p.step];
        const label = answerLabel(flow, p);
        const open = editing === i && !!s?.options;
        const drawn = (open || shown === i) && !!s?.options;
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
            {drawn && (
              <div className={`nl-fold${open ? ' in' : ' out'}`}>
                <div className="pk-choices nl-reopen" role="radiogroup" aria-label={s.title}>
                  {shownOptions(s.options, p.v)[0].map((o) => (
                    <Choice key={o.v} name={`re-${p.step}-${i}`} checked={o.v === shownOptions(s.options, p.v)[1]}
                            disabled={busy || !open}
                            // The answer already chosen folds the row; a radio
                            // that is already on sends no change of its own.
                            onClick={o.v === shownOptions(s.options, p.v)[1] ? () => onOpen?.(i) : undefined}
                            onChange={() => onPick?.(i, o.v)} label={o.label} />
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * The options a reopened step shows (2026-10-26): never a hidden twin (the
 * "split" copy of "Yes, Groceries"), and the answer marked on the one she
 * sees. Returns [options, the value to mark].
 */
export function shownOptions(options, v) {
  const vis = options.filter((o) => !o.hidden);
  const was = options.find((o) => o.v === v);
  return [vis, was?.hidden ? vis.find((o) => o.label === was.label)?.v ?? v : v];
}

/**
 * Where a Sorted card's change reopens (its change undone): answer `i` open
 * in place, or — when another answer `pick` was chosen there (2026-10-23) —
 * at that step with the new answer going in.
 */
/**
 * On the Sorted card, the row to show after tapping step `i`'s marked
 * answer (2026-10-25): the next answer, opened, so the one after it can be
 * changed; after the last, the row folds shut.
 */
export function afterMarked(i, n) {
  return i < n - 1 ? i + 1 : null;
}

export function resumeFor(answers, i = answers.length - 1, pick) {
  const last = answers[answers.length - 1];
  const name = last?.step === 'who_to' || last?.step === 'name' ? last.label : '';
  if (pick !== undefined && answers[i]) {
    return { path: answers.slice(0, i), edit: null, name, pick: { step: answers[i].step, v: pick } };
  }
  return { path: answers.slice(0, -1), edit: i < answers.length - 1 ? i : null, name, pick: null };
}

/**
 * Remember ticked or unticked on the Sorted card (2026-10-23): the change is
 * put back and saved again with the rule on or off, so Undo still undoes
 * all of it. Resolves to the entry as it now is.
 */
export async function rememberEntry(entry, on) {
  if (!entry?.remember) return entry;
  if (entry.undo) await undoChange(entry.undo);
  const r = await entry.remember.redo(on);
  return { ...entry, title: r?.title || entry.title, detail: r?.detail || entry.detail,
           undo: r?.undo, rule: r?.rule || '', remembered: on };
}

/**
 * The Sorted card: every dot filled with "✓ Sorted", the answers as rows
 * (tap one to reopen that step), what the change did, and Next or Done.
 */
export function SortedCard({ entry, busy = false, isPast = false, nextLabel = 'Next', onNext, onUndo, onReopen, onPrevious,
                             onRemember, showHead = true }) {
  const { it, answers } = entry;
  // The answer open for a look, and the one folding shut.
  const [viewing, setViewing] = useState(null);
  const [shown, setShown] = useState(null);
  useEffect(() => {
    if (viewing !== null) { setShown(viewing); return undefined; }
    const t = setTimeout(() => setShown(null), FOLD_MS);
    return () => clearTimeout(t);
  }, [viewing]);
  return (
    <>
      {showHead && (it.txn ? <TxHead txn={it.txn} name={it.to} /> : (
        <p className="pk-h3">{monthName(`${it.month}-01`)} had three paycheques</p>
      ))}
      <Progress done={answers.length} total={Math.max(answers.length, 1)} sorted
                trailing={onUndo && <Pill className="nl-undo" disabled={busy} onClick={onUndo} aria-label="Undo this change">Undo</Pill>} />
      {/* Tapping an answer shows its question, the answer marked, and
          changes nothing (2026-10-23): Next is still there. Only another
          answer, Change, or Undo changes it. Tapping the marked answer
          again goes on to the next answer, opened (2026-10-25), so a wrong
          category is a tap away from Change instead of a dead end. */}
      {answers.length > 0 && (
        <div className="nl-done-list">
          {answers.map((a, i) => {
            const open = viewing === i;
            const drawn = open || shown === i;
            return (
              <div key={`${a.step ?? i}-${i}`} className={`nl-done-wrap${open ? ' open' : ''}`}>
                <button type="button" className="nl-done" disabled={busy}
                        aria-expanded={open} aria-label={open ? `Close: ${a.title || a.label}` : `See: ${a.label ?? a.v}`}
                        onClick={() => setViewing(open ? null : i)}>
                  <span className="nl-done-ring" aria-hidden="true" />
                  <span className="nl-done-label">{open && a.title ? a.title : (a.label ?? a.v)}</span>
                  <PIcon name={open ? 'chevronUp' : 'chevronDown'} size={14} />
                </button>
                {drawn && (
                  <div className={`nl-fold${open ? ' in' : ' out'}`}>
                    {a.options?.length ? (
                      <div className="pk-choices nl-reopen" role="radiogroup" aria-label={a.title || 'Your answer'}>
                        {a.options.map((o) => (
                          <Choice key={o.v} name={`seen-${entry.key}-${i}`} checked={o.v === (a.marked ?? a.v)}
                                  disabled={busy || !open || isPast}
                                  onClick={o.v === (a.marked ?? a.v) ? () => setViewing(afterMarked(i, answers.length)) : undefined}
                                  onChange={() => { if (o.v !== (a.marked ?? a.v)) onReopen?.(i, o.v); }} label={o.label} />
                        ))}
                      </div>
                    ) : (
                      <div className="nl-reopen nl-seen">
                        <span className="nl-seen-value"><PIcon name="check" size={14} /> {a.label ?? a.v}</span>
                        {onReopen && !isPast && (
                          <button type="button" className="nl-change" disabled={busy || !open}
                                  onClick={() => onReopen(i)}>Change</button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {/* Remember, after the answers and above What changed (2026-10-23):
          whether every one like it goes the same way. */}
      {entry.remember && onRemember && !isPast && (
        <Choice type="checkbox" checked={!!entry.remembered} disabled={busy}
                onChange={(on) => onRemember(on)} label={entry.remember.label}
                description={entry.remember.description ?? 'Sorts every transaction from them the same way from now on'} />
      )}
      {/* What changed (2026-10-22): what it is now, what that does to her
          numbers, and her rule if she saved one. A neutral box with a label,
          not an unexplained lilac one. */}
      {(entry.detail || entry.title) && (
        <div className="nl-effect" role="status">
          <p className="pk-overline">What changed</p>
          {entry.title && <p className="nl-effect-title">{entry.title}</p>}
          {entry.detail && entry.detail !== entry.title && <p className="nl-effect-detail">{entry.detail}</p>}
          {entry.rule && (
            <p className="nl-effect-rule"><PIcon name="check" size={14} /> {entry.rule}</p>
          )}
        </div>
      )}
      <div className="nl-actions nl-next nl-bottom">
        {/* Previous bottom left, in line with Next (2026-10-22). */}
        {onPrevious && (
          <Pill icon="arrowLeft" className="nl-previous" disabled={busy} onClick={onPrevious} aria-label="Previous transaction">
            Previous
          </Pill>
        )}
        {/* The same pill as Undo (2026-10-21), so the card's two ways out match. */}
        <button type="button" className="nl-pill nl-pill-go" disabled={busy} onClick={onNext}>
          {isPast ? 'Back to where I was' : nextLabel} <PIcon name="chevronRight" size={14} />
        </button>
      </div>
    </>
  );
}
