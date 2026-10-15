import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  answerCarryover, createLinkToken, dismissSuggestion, getHome, money, putHomeAnswers, saveExpected,
  syncPlaid, undoDismissSuggestion,
} from '../api.js';
import { loadPlaidScript } from '../plaid.js';
import { ActionToast, Alert, DetailPanel, PButton, StatusPill } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { ExpectedForm } from '../pearl/IncomeBills.jsx';
import { ProgressBar, SnapshotBar } from '../pearl/viz.jsx';
import { LensToggle, readLens, writeLens } from './Lens.jsx';
import { setGoalsIntent, writeTxUrl } from '../router.js';
import { Field, Mark } from './GoalsParts.jsx';
import { CarryoverPrompt, carryoverRow } from './HomeCarryover.jsx';
import { DebtsCard } from './DebtsPanel.jsx';
import { BudgetsCard } from './CategoryBudgetsPanel.jsx';
import { ForYou, WhyPanel, dismissedWords } from './ForYou.jsx';
import NotifyPrime from './NotifyPrime.jsx';
import './home.css';

/**
 * Home (Pearl THL-125 H-01/H-02, laid out as THL-129 GR-05; THL-44, THL-46).
 *
 * The landing screen. This step draws its header, the safe-to-spend card and
 * "How we worked this out" (X-01 to X-04). The cards below it (path,
 * snapshot, suggestions, needs a look, budgets, debts) arrive in
 * later steps, in that order (THL-9 decision L1). Home reads by the month
 * only: there is no week view.
 *
 * Copy rules from the THL-9 decisions: the hero is in cents, everything else
 * in whole dollars (S7); no display number carries a sign (S3); a month past
 * its plan says by how much and never shows $0 (S1); days left include
 * today (S6); with no income there is no number, only the question (E1).
 *
 * When data is missing or thin (THL-137, E10) Home is one of:
 *   E-01 no_data   — connect your bank, the path ahead, or two questions
 *   E-02 learning  — a rough estimate, "learning" with dates, starter questions
 *   E-03 irregular — a cautious estimate, labelled, with "Use a different amount"
 *   E-04 card_only — card spending only, and one prompt to link chequing
 * Rough and cautious numbers are shown rounded down to $10 (S7, E5). Exactly
 * one primary action on the page (E3); one alert at a time (C3).
 *
 * H-03: once she skipped the check's "We didn't spot a regular paycheque"
 * (I-03), the number is a rough estimate from the deposits we've seen, to
 * the nearest $50, and the one primary action is "Add your income" (I-03).
 *
 * The snapshot (THL-48, H-01) compares Income with what's expected, Essentials
 * and Lifestyle with her usual month and where she usually is by today
 * (THL-184), and Savings with the monthly plan. Pace follows THL-110's ±10%
 * rule; over pace or over the month is champagne, with words (L2).
 *
 * The path card (THL-129 GR-05) carries Home's one primary action: the next
 * step. "Needs a look" (THL-123) opens R-01 and hides at 0. A bank that wants
 * her to sign in again, or isn't answering, comes first among the alerts
 * (THL-120 C-02, C-03), and Reconnect signs in again in place (C-04, C-05).
 *
 * The afford-it card (THL-167) was removed (THL-235, 2026-10-14).
 * After the snapshot, "For you": up to two recommendation cards (THL-12,
 * ForYou.jsx), their actions secondary. Then budgets that need a look (THL-168 B-03, CategoryBudgetsPanel.jsx) and
 * debts (THL-49 D-01, DebtsPanel.jsx), each only when there's something.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
export const MONTH_NAMES = MONTHS;
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function parts(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return { y, m, d, weekday: DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] };
}

/** "October" from "2026-10" or "2026-10-09". */
export const monthName = (iso) => MONTHS[parts(`${iso.slice(0, 7)}-01`).m - 1];
/** "Oct 12". */
export const shortDate = (iso) => { const p = parts(iso); return `${MONTHS[p.m - 1].slice(0, 3)} ${p.d}`; };
/** "Friday, October 16". */
export const longDate = (iso) => { const p = parts(iso); return `${p.weekday}, ${MONTHS[p.m - 1]} ${p.d}`; };

/** An amount as shown: never signed, cents where the decisions ask for them. */
export const shown = (n, cents = false) => money(Math.abs(n), { cents });

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The safe-to-spend card's words, for every state (H-01, H-02, E1). */
export function heroCopy(s) {
  const month = monthName(s.month);
  const label = `Safe to spend in ${month}`;
  if (s.state === 'needs_income') {
    return {
      label, figure: null, pill: null,
      context: `Tell us what you expect to earn and we’ll work out what’s safe to spend in ${month}.`,
    };
  }
  const next = s.next_pay ? `Your next pay arrives on ${longDate(s.next_pay)}.` : null;
  if (s.state === 'ok' && s.income_source === 'deposits') {
    return {
      label: `${label} · rough estimate`, pill: 'Estimate',
      figure: s.shown >= 50 ? `About ${shown(s.shown)}` : 'Less than $50',
      context: 'Based on deposits we’ve seen. Add your income for a real number.',
    };
  }
  if (s.state === 'ok' && s.estimate === 'rough') {
    return {
      label, pill: 'Estimate',
      figure: s.shown >= 10 ? `About ${shown(s.shown)}` : 'Less than $10',
      context: s.income_source === 'told'
        ? 'Rough estimate from the income and rent you told us'
        : 'Rough estimate from your first few weeks',
    };
  }
  if (s.state === 'ok' && s.estimate === 'usual') {
    return {
      label, pill: 'Estimate',
      figure: s.shown >= 10 ? shown(s.shown) : 'Less than $10',
      context: `Based on your usual income, the average of ${usualMonths(s)}`,
    };
  }
  if (s.state === 'ok' && s.estimate === 'cautious') {
    return {
      label, pill: 'Cautious',
      figure: s.shown >= 10 ? shown(s.shown) : 'Less than $10',
      context: `Based on your lowest month of the last 3 (${shown(s.cautious.lowest)})`,
    };
  }
  if (s.state === 'over') {
    return {
      label, figure: shown(s.over_by, true), figureWords: 'past this month’s plan', pill: null,
      context: [next, 'That happens, and it’s easy to catch up.'].filter(Boolean).join(' '),
    };
  }
  if (s.amount === 0) {
    return {
      label, figure: null, pill: null,
      context: ['This month’s plan is used up exactly.', next].filter(Boolean).join(' '),
    };
  }
  return {
    label, figure: shown(s.amount, true), pill: 'On track',
    context: s.per_day >= 1
      ? `${plural(s.days_left, 'day')} left · about ${shown(s.per_day)} a day`
      : `${plural(s.days_left, 'day')} left`,
  };
}

/** "July, August and September": the months her usual income comes from. */
export function usualMonths(s) {
  const names = (s.usual?.months ?? []).map((m) => monthName(m));
  if (names.length < 2) return names.join('') || 'your last 3 months';
  return `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
}

const LINE_NOTES = { estimate: 'estimate', late: 'usually here by now' };

// What a row says instead of "$0.00" (S1: never $0 on Home).
const NOTHING = { income: 'None yet', bills: 'None', spent: 'Nothing yet', set_aside: 'Done' };

/** The sheet's rows and total (X-01, X-02), in the order they're subtracted. */
export function sheetRows(s) {
  const rows = s.rows.map((r) => {
    if (r.key === 'income') {
      const other = r.lines.some((l) => l.kind !== 'salary');
      let detail = `${plural(r.paycheques, 'paycheque')}${r.payer ? ` from ${r.payer}` : ''}${other ? ', and other income' : ''}`;
      if (r.source === 'entered' || r.source === 'told') detail = 'What you told us you earn';
      if (r.source === 'deposits') detail = 'Deposits we’ve seen in the last 30 days';
      if (r.source === 'usual') detail = `Your usual income: the average of ${usualMonths(s)}`;
      if (r.source === 'cautious') {
        detail = `Your lowest month of the last 3 was ${monthName(r.cautious.month)}, ${shown(r.cautious.lowest)}`;
      }
      return {
        key: r.key, label: 'Money coming in this month', detail, amount: r.amount,
        lines: r.lines.map((l) => ({
          label: l.date ? `${l.label} · ${shortDate(l.date)}${l.arrived ? '' : ' (on its way)'}` : l.label,
          amount: l.amount,
        })),
      };
    }
    if (r.key === 'bills') {
      let detail = 'Nothing else due this month';
      if (r.count === 1) detail = r.first ? `1 bill on ${shortDate(r.first)}` : '1 bill';
      else if (r.count > 1) {
        detail = r.first && r.last && r.first !== r.last
          ? `${r.count} bills between ${shortDate(r.first)} and ${shortDate(r.last)}`
          : `${r.count} bills this month`;
      }
      return {
        key: r.key, label: 'Bills still to come', detail, amount: r.amount,
        lines: r.lines.map((b) => {
          const notes = ['estimate', 'late'].filter((k) => b[k]).map((k) => LINE_NOTES[k]);
          if (b.told) notes.push('what you told us');
          const when = b.date ? ` · ${shortDate(b.date)}` : '';
          return { label: `${b.label}${when}${notes.length ? ` (${notes.join(', ')})` : ''}`,
                   amount: b.amount };
        }),
      };
    }
    if (r.key === 'carryover') {
      // THL-212: last month's surplus or shortfall, added or taken off.
      return { key: r.key, ...carryoverRow(r), amount: r.amount, lines: [] };
    }
    if (r.key === 'spent') {
      return {
        key: r.key, label: 'Already spent', amount: r.amount,
        detail: `${r.pending > 0 ? 'Includes pending' : 'Pending included'} · transfers and card payments don’t count`,
        lines: r.lines,
      };
    }
    return {
      key: r.key,
      label: r.goal === 'anchor' ? 'Set aside for your Anchor' : 'Set aside for your saving goal',
      detail: `Your monthly goal is ${shown(r.target)}${r.saved > 0 ? ` · ${shown(r.saved)} saved so far` : ''}`,
      amount: r.amount, lines: [],
    };
  });
  const total = s.state === 'over'
    ? { label: 'Past this month’s plan', amount: s.over_by,
        detail: s.next_pay ? `Your next pay arrives on ${longDate(s.next_pay)}` : null }
    : { label: 'Safe to spend', amount: s.amount,
        detail: s.per_day >= 1 ? `About ${shown(s.per_day)} a day for ${plural(s.days_left, 'day')}` : null };
  const withText = rows.map((r) => ({
    ...r, display: r.amount > 0 ? shown(r.amount, true) : NOTHING[r.key],
  }));
  // E5: the sheet keeps the exact rows and says what the card rounded.
  let note = null;
  if (s.state === 'ok' && s.income_source === 'deposits' && s.amount > 0) {
    note = s.shown >= 50 ? `Shown to the nearest $50, ${shown(s.shown)}.` : 'Shown as less than $50.';
  } else if (s.state === 'ok' && s.estimate && s.amount > 0) {
    note = s.shown >= 10 ? `Shown rounded down to ${shown(s.shown)}.` : 'Shown as less than $10.';
  }
  return {
    rows: withText,
    total: { ...total, display: total.amount > 0 ? shown(total.amount, true) : 'Nothing left', note },
  };
}

export default function HomePanel({ onTab, onChanged, version }) {
  const [home, setHome] = useState(null);
  const [error, setError] = useState(null);
  const [explain, setExplain] = useState(false);
  const [income, setIncome] = useState(false);
  const [expected, setExpected] = useState(false);
  const [reconnect, setReconnect] = useState(null);
  const [back, setBack] = useState(null);
  const [why, setWhy] = useState(null);
  const [hidden, setHidden] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return getHome().then(setHome).catch(setError);
  }, []);
  // `version` moves after every import and sync, so the number follows them.
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!home) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading Home…</p></div>;

  const s = home.safe_to_spend;
  const ds = home.data_state;
  const p = parts(`${home.month}-01`);
  const save = (answers) => putHomeAnswers(answers).then(setHome);
  // Linking a bank lives on Profile › Accounts since Connections went (C1).
  const link = () => onTab?.('accounts');
  // A card's action (THL-12 R3): the list it points at, or Goals.
  const act = (card) => {
    setWhy(null);
    if (card.action.to === 'transactions') {
      writeTxUrl({ filters: card.action.filters, from: 'home' }, { push: true });
    } else if (card.action.goals) {
      setGoalsIntent(card.action.goals);
    }
    onTab?.(card.action.to);
  };
  // "Not for me" (THL-62): gone at once, back with Undo.
  const notForMe = (card) => {
    setWhy(null);
    setHome((h) => ({ ...h, recommendations: h.recommendations.filter((c) => c.type !== card.type) }));
    setHidden(card.type);
    dismissSuggestion(card.type).catch(() => load());
  };
  const undo = () => {
    const type = hidden;
    setHidden(null);
    undoDismissSuggestion(type).then(load).catch(() => load());
  };
  return (
    <div className="pk hm-page">
      <header className="hm-head">
        <p className="pk-overline">{`${MONTHS[p.m - 1]} ${p.y}`}</p>
        <h1 className="pk-h1">Home</h1>
      </header>
      <HomeBody s={s} ds={ds} snap={home.snapshot} onSave={save} onLink={link}
                debts={home.debts} onDebts={() => onTab?.('debts')}
                budgets={home.budgets} onBudgets={() => onTab?.('budgets')}
                cards={home.recommendations} onCard={act} onWhy={setWhy} onNotForMe={notForMe}
                onChest={() => onTab?.('goals')}
                path={home.path} reviewCount={home.review_count}
                connections={home.connections} back={back} today={home.today}
                savings={home.savings}
                onPath={(action) => onTab?.(PATH_ACTIONS[action] ?? 'path')}
                onReview={() => onTab?.('review')}
                onReconnect={(c) => (c.state === 'needs_sign_in' ? setReconnect(c) : onTab?.('accounts'))}
                onExplain={() => setExplain(true)} onIncome={() => setIncome(true)}
                onAddIncome={() => setExpected(true)}
                carry={home.carryover}
                onCarry={(choice) => answerCarryover(home.carryover.month, choice).then(async () => {
                  await onChanged?.();
                  await load();
                })}
                onSeeWhere={(group) => {
                  // TX-02: the list, opened on this month and the group.
                  writeTxUrl({ filters: { month: s.month, group }, from: 'home' }, { push: true });
                  onTab?.('transactions');
                }} />
      {explain && s.rows.length > 0 && (
        <HowWeWorkedItOut s={s} onClose={() => setExplain(false)}
                          onEdit={() => {
                            setExplain(false);
                            // Income she gave us, or the cautious figure, is
                            // changed here; pay and bills are confirmed on
                            // Profile › Income and bills (THL-127).
                            if (['told', 'cautious', 'usual'].includes(s.income_source)) setIncome(true);
                            else if (s.income_source === 'deposits') setExpected(true);
                            else onTab?.('income');
                          }} />
      )}
      {why && <WhyPanel card={why} onClose={() => setWhy(null)} onAction={act} onNotForMe={notForMe} />}
      {hidden && <ActionToast title={dismissedWords(hidden)} onUndo={undo} onDone={() => setHidden(null)} />}
      {/* THL-139 N-01: once safe to spend has a number. */}
      <NotifyPrime sts={s} path={home.path} />
      {reconnect && (
        <ReconnectPanel connection={reconnect} onClose={() => setReconnect(null)}
                        onDone={async () => {
                          setReconnect(null);
                          setBack(reconnect.institution);
                          await onChanged?.();
                          await load();
                        }} />
      )}
      {expected && (
        // H-03's "Add your income": the check's I-03, over Home.
        <DetailPanel label="Add your income" overline="Your income" onClose={() => setExpected(false)}>
          <ExpectedForm expected={null} eyebrow={null} title="What you expect each month"
                        sub="Tell us roughly what comes in after tax."
                        onSkip={() => setExpected(false)} skipLabel="Cancel"
                        onSave={(amount, varies) => saveExpected(amount, varies).then(async () => {
                          setExpected(false);
                          await onChanged?.();
                          await load();
                        })} />
        </DetailPanel>
      )}
      {income && (
        <IncomePanel s={s} told={ds.answers.income} onClose={() => setIncome(false)}
                     onSave={(amount) => save({ income: amount, override: !!s.cautious })
                       .then(() => setIncome(false))}
                     onReset={() => save({ income: 0 }).then(() => setIncome(false))} />
      )}
    </div>
  );
}

/** Which Home to draw, by data state (THL-137). Exactly one primary action. */
// Where each path action goes (GR-05's button).
const PATH_ACTIONS = { goals: 'goals', path: 'path', bills: 'income', income: 'income' };

export function HomeBody({ s, ds, snap, onSave, onLink, onExplain, onIncome, onSeeWhere,
                           onAddIncome, carry = null, onCarry, path, reviewCount = 0,
                           connections = [], back = null, today,
                           onPath, onReview, onReconnect, onChest, debts = null, onDebts,
                           budgets = null, onBudgets, cards = [], onCard, onWhy, onNotForMe,
                           savings = null }) {
  const review = reviewCount > 0 && <NeedsALook count={reviewCount} onReview={onReview} />;
  if (ds.kind === 'no_data') {
    return (
      <>
        <ConnectCard failed={ds.linking_failed} onLink={onLink} primary />
        <PathPreview />
        <WithoutLinking onSave={onSave} />
      </>
    );
  }
  if (ds.kind === 'card_only') {
    return (
      <>
        <CardOnlyHero ds={ds} month={s.month} onLink={onLink} />
        <MonthSoFar month={s.month} lines={ds.card_spending.lines}
                    note="Usual-month comparisons start once we’ve seen a full month." />
        {review}
      </>
    );
  }
  const noAccounts = ds.history_days === 0;
  const alert = homeAlert(s, ds, snap, connections, back, today);
  const act = alert?.connection ? () => onReconnect?.(alert.connection)
    : alert?.group ? () => onSeeWhere?.(alert.group) : onIncome;
  if (s.income_source === 'deposits') {
    // H-03: the rough number, and adding her income is the one thing to do.
    return (
      <>
        {alert && (
          <Alert tone={alert.tone ?? 'info'} action={alert.action}
                 onAction={alert.action ? act : undefined}>
            {alert.text}
          </Alert>
        )}
        <SafeToSpendCard s={s} onExplain={onExplain} />
        <IncomeFirstCard phase={path?.phase ?? 'protect'} onAdd={onAddIncome} />
        {review}
      </>
    );
  }
  const trouble = connections.find((c) => c.state !== 'disconnected');
  return (
    <>
      {alert && (
        <Alert tone={alert.tone ?? 'info'} action={alert.action}
               onAction={alert.action ? act : undefined}>
          {alert.text}
        </Alert>
      )}
      <SafeToSpendCard s={s} onExplain={onExplain}
                       updated={trouble ? `${trouble.institution} last updated ${whenWords(trouble.last_synced, today)}` : null} />
      <CarryoverPrompt c={carry} safe={s} onAnswer={onCarry} onChest={onChest} onExplain={onExplain} />
      <SavingsCard savings={savings} nextPay={s.next_pay} onExplain={onExplain} />
      {ds.asks_questions && <StarterQuestions onSave={onSave} primary />}
      {path && ['normal', 'irregular'].includes(ds.kind) && (
        <PathCard path={path} onPath={onPath} primary={!ds.asks_questions} />
      )}
      {ds.kind === 'learning' && !noAccounts && (
        <MonthSoFar month={s.month}
                    lines={[{ label: 'Spent so far', amount: ds.spent_so_far },
                            { label: 'Regular bills found', count: ds.bills_found }]}
                    note={ds.comparisons_from
                      ? `We’ll compare with your usual month from ${longDate(ds.comparisons_from)}.`
                      : 'We’ll compare with your usual month once we’ve seen one.'} />
      )}
      {noAccounts && <ConnectCard failed={ds.linking_failed} onLink={onLink}
                                  primary={!ds.asks_questions} />}
      {snap && ['normal', 'irregular'].includes(ds.kind) && <Snapshot snap={snap} />}
      {['normal', 'irregular'].includes(ds.kind) && (
        <ForYou cards={cards} onAction={onCard} onWhy={onWhy} onNotForMe={onNotForMe} />
      )}
      {review}
      {['normal', 'irregular'].includes(ds.kind) && <BudgetsCard budgets={budgets} onSee={onBudgets} />}
      {debts?.count > 0 && <DebtsCard debts={debts} onSee={onDebts} />}
    </>
  );
}

/** "today", "Tuesday" within the week, else "Oct 2". */
export function whenWords(iso, today) {
  if (!iso) return 'a while ago';
  const day = iso.slice(0, 10);
  if (!today || day === today) return 'today';
  const days = Math.round((Date.parse(today) - Date.parse(day)) / 86400000);
  return days > 0 && days < 7 ? parts(day).weekday : shortDate(day);
}

/** One alert at a time, in the C3 order: connection, over plan, learning,
 * cautious. Signed back in (C-05) is said once, right after. */
export function homeAlert(s, ds, snap, connections = [], back = null, today = null) {
  const c = connections[0];
  if (c?.state === 'needs_sign_in') {
    const what = c.cards_only ? 'Card purchases' : 'Transactions';
    return { tone: 'caution', action: 'Reconnect', connection: c,
             text: `${c.institution} needs you to sign in again. ${what} since ${whenWords(c.last_synced, today)} aren’t counted yet.` };
  }
  if (c?.state === 'disconnected') {
    return { tone: 'caution', action: 'See accounts', connection: c,
             text: `${c.institution} is no longer connected, so its transactions aren’t coming in.` };
  }
  if (c?.state === 'bank_down') {
    return { tone: 'info', action: 'Details', connection: c,
             text: `${c.institution} isn’t responding right now. We’ll keep trying; there’s nothing you need to do.` };
  }
  if (back) return { tone: 'positive', text: `${back} is back up to date.` };
  if (s.income_source === 'deposits') {
    return { text: 'Tell us what you expect to earn and this number gets much more accurate.' };
  }
  if (s.state === 'over' && snap?.extra_went_to) {
    // H-02: where the extra went, and a way to see it (TX-02).
    return { tone: 'caution', text: `${snap.extra_went_to} is where the extra went.`,
             action: 'See where it went', group: snap.extra_went_to.toLowerCase() };
  }
  if (ds.kind === 'learning' && ds.history_days > 0 && ds.learning_until) {
    return {
      text: `Pearl is learning your patterns. Your number gets more exact after ${longDate(ds.learning_until)}, and comparisons with a usual month start on ${longDate(ds.comparisons_from)}.`,
    };
  }
  if (ds.kind === 'irregular' && s.income_source === 'usual') {
    return { text: `This uses your usual income, the average of ${usualMonths(s)}. If you expect something different, tell us.`,
             action: 'Use a different amount' };
  }
  if (ds.kind === 'irregular') {
    return { text: 'Your income changes month to month, so this is a cautious estimate.',
             action: 'Use a different amount' };
  }
  return null;
}

/** SafeToSpendCard (H-01, H-02). */
/** "$X" / "nothing yet" / "$X short", for a running total that can dip below zero. */
export function netWords(net) {
  if (Math.abs(net) < 0.005) return { figure: 'Nothing yet', short: false };
  return { figure: money(Math.abs(net)), short: net < 0 };
}

/** "$150 in, nothing taken out", "$500 in, $200 to chests, $100 taken out",
 * or what counts when nothing has (SV-01). */
export function putAwayWords(p, short) {
  if (short) return 'More taken out than put in';
  const parts = [];
  if (p.contributions > 0) parts.push(`${money(p.contributions)} in`);
  if ((p.chests ?? 0) > 0) parts.push(`${money(p.chests)} to chests`);
  if (p.withdrawals > 0) parts.push(`${money(p.withdrawals)} taken out`);
  else if (parts.length) parts.push('nothing taken out');
  return parts.length ? parts.join(', ') : 'Transfers you mark as saved, and money in your chests';
}

/** "$994 more out" when more went out than came in; otherwise the figure. */
export function leftOverFigure(net) {
  if (Math.abs(net) < 0.005) return 'Nothing yet';
  return net < 0 ? `${money(Math.abs(net))} more out` : money(net);
}

/** Savings this month (SV-01, THL-233): Put away and Left over so far,
 * each with what went into it. Never "$0"; below zero reads "$X more out",
 * never in red. */
export function SavingsCard({ savings, nextPay = null, onExplain }) {
  if (!savings || !savings.month) return null;
  const put = netWords(savings.put_away.net);
  const left = savings.left_over.net;
  const short = left < -0.005;
  const leftWords = short
    ? `Spent more than came in so far.${nextPay ? ` Your next pay lands ${longDate(nextPay)}.` : ''}`
    : `${money(savings.left_over.income)} in${savings.left_over.estimate ? ' (what you told Pearl)' : ''}, ${money(savings.left_over.spent)} spent so far`;
  return (
    <section className="hm-card hm-savings" aria-labelledby="hm-savings-title">
      <div className="hm-row-between">
        <h2 className="pk-h3" id="hm-savings-title">Savings this month</h2>
        {onExplain && (
          <button type="button" className="hm-link" onClick={onExplain}>How we worked this out ›</button>
        )}
      </div>
      <div className="hm-savings-tiles">
        <div className="hm-savings-tile">
          <p className="pk-overline">Put away</p>
          <p className="pk-amount">{put.figure}</p>
          <p className="pk-label pk-muted">{putAwayWords(savings.put_away, put.short)}</p>
        </div>
        <div className="hm-savings-tile">
          <p className="pk-overline">Left over so far</p>
          <p className="pk-amount">{leftOverFigure(left)}</p>
          <p className="pk-label pk-muted">{leftWords}</p>
        </div>
      </div>
    </section>
  );
}

export function SafeToSpendCard({ s, onExplain, updated = null }) {
  const c = heroCopy(s);
  const canExplain = s.rows.length > 0;
  return (
    <section className="hm-sts" aria-labelledby="hm-sts-label">
      <div className="hm-sts-top">
        <p className="hm-sts-label" id="hm-sts-label">{c.label}</p>
        {c.pill && <StatusPill icon={s.estimate ? 'info' : 'check'}>{c.pill}</StatusPill>}
      </div>
      {c.figure && (
        <p className="hm-sts-figure">
          <span className="pk-amount">{c.figure}</span>
          {c.figureWords && <span className="hm-sts-words">{` ${c.figureWords}`}</span>}
        </p>
      )}
      <p className="hm-sts-context">
        {c.context}
        {updated && ` · ${updated}`}
        {canExplain && (
          <>
            {' · '}
            <button type="button" className="hm-link" onClick={onExplain}>
              How we worked this out
            </button>
          </>
        )}
      </p>
    </section>
  );
}

/**
 * The ledger behind "How we worked this out" (X-01 to X-04): rows that add up
 * to a total, each opening in place on the lines behind it (X-02). The same
 * component explains a goal's projection (X-03, GoalsProjection.jsx).
 * A row is `{ key, label, detail, display, lines: [{ label, amount | display }] }`.
 */
export function Ledger({ rows, total }) {
  const [open, setOpen] = useState(null);
  return (
    <div className="hm-ledger">
      {rows.map((r) => {
        const expanded = open === r.key;
        const id = `hm-lines-${r.key}`;
        return (
          <div key={r.key} className="hm-row">
            <button type="button" className="hm-row-head" aria-expanded={expanded}
                    aria-controls={r.lines.length ? id : undefined}
                    disabled={!r.lines.length}
                    onClick={() => setOpen(expanded ? null : r.key)}>
              <PIcon name={expanded ? 'chevronDown' : 'chevronRight'} size={16} />
              <span className="hm-row-text">
                <span className="hm-row-label">{r.label}</span>
                {r.detail && <span className="hm-row-detail">{r.detail}</span>}
              </span>
              <span className="hm-row-amount">{r.display}</span>
            </button>
            {expanded && (
              <ul className="hm-lines" id={id}>
                {r.lines.map((l, i) => (
                  <li key={i}><span>{l.label}</span><span>{l.display ?? shown(l.amount, true)}</span></li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      <div className="hm-total">
        <span className="hm-row-text">
          <span className="pk-h3">{total.label}</span>
          {total.detail && <span className="hm-row-detail">{total.detail}</span>}
        </span>
        <span className="pk-h3">{total.display}</span>
      </div>
    </div>
  );
}

/** "How we worked this out" (X-01 to X-04): every input, adding up to the number. */
export function HowWeWorkedItOut({ s, onClose, onEdit }) {
  const { rows, total } = sheetRows(s);
  const title = s.state === 'over'
    ? `Past this month’s plan: ${shown(s.over_by, true)}`
    : s.amount <= 0 ? 'Safe to spend: nothing left'
      : s.estimate ? `Safe to spend: about ${shown(s.shown)}`
        : `Safe to spend: ${shown(s.amount, true)}`;
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} sheet className="hm-sheet">
      <h1 className="pk-h2">{title}</h1>
      <p className="pk-muted">{`Every number behind it, for ${monthName(s.month)}.`}</p>
      <Ledger rows={rows} total={total} />
      {total.note && <p className="pk-muted hm-note">{total.note}</p>}
      <button type="button" className="hm-link" onClick={onEdit}>
        Something look wrong? Edit your income or bills
      </button>
      <div className="hm-sheet-foot">
        <PButton variant="secondary" onClick={onClose}>Got it</PButton>
      </div>
    </DetailPanel>
  );
}

/** "$3,200", "3200", "3,200.50" → 3200.5; anything else → NaN. */
export function parseAmount(text) {
  const clean = String(text ?? '').replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return NaN;
  return Number(clean);
}

/** Starter questions (E-02): take-home pay and rent, for an estimate now. */
export function StarterQuestions({ onSave, primary = false, title = 'Help Pearl get it right sooner' }) {
  const [income, setIncome] = useState('');
  const [rent, setRent] = useState('');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const pay = parseAmount(income);
    const home = rent.trim() ? parseAmount(rent) : 0;
    if (!(pay > 0)) { setError({ field: 'income', text: 'Enter your monthly take-home pay, like 3200.' }); return; }
    if (Number.isNaN(home)) { setError({ field: 'rent', text: 'Enter your rent or mortgage, like 1650, or leave it empty.' }); return; }
    setError(null);
    setSaving(true);
    onSave({ income: pay, rent: home })
      .catch((err) => setError({ field: 'income', text: err.message }))
      .finally(() => setSaving(false));
  };
  return (
    <form className="hm-card" onSubmit={submit} aria-labelledby="hm-starter-title">
      <h2 className="pk-h3" id="hm-starter-title">{title}</h2>
      <p className="pk-muted">Two quick answers and we can estimate your month now.</p>
      <Field label="Monthly take-home pay" id="hm-income"
             error={error?.field === 'income' ? error.text : null}>
        <input id="hm-income" inputMode="decimal" autoComplete="off" placeholder="$4,300"
               value={income} onChange={(e) => setIncome(e.target.value)} />
      </Field>
      <Field label="Rent or mortgage" id="hm-rent"
             error={error?.field === 'rent' ? error.text : null}>
        <input id="hm-rent" inputMode="decimal" autoComplete="off" placeholder="$1,650"
               value={rent} onChange={(e) => setRent(e.target.value)} />
      </Field>
      <PButton type="submit" variant={primary ? 'primary' : 'secondary'} disabled={saving}>
        {saving ? 'Saving…' : 'Save answers'}
      </PButton>
    </form>
  );
}

/** E-01: nothing linked, or linking didn't finish. */
export function ConnectCard({ failed, onLink, primary = true }) {
  const [why, setWhy] = useState(false);
  return (
    <section className="hm-card hm-connect" aria-labelledby="hm-connect-title">
      <span className="pk-empty-icon"><PIcon name="search" size={24} /></span>
      <h2 className="pk-h3" id="hm-connect-title">Let’s connect your bank</h2>
      <p className="pk-muted">
        {failed
          ? 'Pearl works out what’s safe to spend from your accounts. Linking didn’t finish last time, and nothing was saved.'
          : 'Pearl works out what’s safe to spend from your accounts.'}
      </p>
      <PButton variant={primary ? 'primary' : 'secondary'} onClick={onLink}>
        {failed ? 'Try linking again' : 'Link your bank'}
      </PButton>
      <button type="button" className="hm-link" aria-expanded={why} onClick={() => setWhy(!why)}>
        Why Pearl needs this
      </button>
      {why && (
        <p className="pk-muted hm-why">
          Pearl reads what comes in, what’s due and what you’ve spent, so the number fits your
          month. It only reads; it can’t move money. You sign in through Plaid.
        </p>
      )}
    </section>
  );
}

const PATH = [
  { phase: 'protect', name: 'Protect', text: 'Know what’s coming in and going out' },
  { phase: 'build', name: 'Build', text: 'Build your Anchor' },
  { phase: 'unveil', name: 'Unveil', text: 'Start growing your money' },
];

/** E-01: the milestone path, as a preview. */
export function PathPreview() {
  return (
    <section className="hm-card" aria-labelledby="hm-path-title">
      <h2 className="pk-h3" id="hm-path-title">Your path</h2>
      <ol className="hm-path">
        {PATH.map((step) => (
          <li key={step.phase}>
            <Mark phase={step.phase} width={40} />
            <span className="pk-h3">{step.name}</span>
            <span className="pk-muted pk-label">{step.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** E-01: start without linking, with the two starter questions. */
export function WithoutLinking({ onSave }) {
  const [open, setOpen] = useState(false);
  if (open) return <StarterQuestions onSave={onSave} title="Two questions to start" />;
  return (
    <section className="hm-card" aria-labelledby="hm-nolink-title">
      <h2 className="pk-h3" id="hm-nolink-title">Prefer to start without linking?</h2>
      <p className="pk-muted">Tell us your take-home pay and rent and we’ll give you a rough estimate.</p>
      <button type="button" className="hm-link" onClick={() => setOpen(true)}>
        Answer two questions <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

/** E-02 and E-04: what's known this month, before the snapshot can compare. */
export function MonthSoFar({ month, lines, note }) {
  return (
    <section className="hm-card" aria-labelledby="hm-sofar-title">
      <h2 className="pk-h3" id="hm-sofar-title">{`${monthName(month)} so far`}</h2>
      <dl className="hm-facts">
        {lines.map((l) => (
          <div key={l.label}>
            <dt>{l.label}</dt>
            <dd>{'count' in l
              ? (l.count > 0 ? l.count : 'None yet')
              : (l.amount > 0 ? shown(l.amount) : 'Nothing yet')}</dd>
          </div>
        ))}
      </dl>
      {note && <p className="pk-muted pk-label">{note}</p>}
    </section>
  );
}

/** E-04: only a card linked, so spending only, and one prompt to link chequing. */
export function CardOnlyHero({ ds, month, onLink }) {
  const amount = ds.card_spending.amount;
  return (
    <section className="hm-card" aria-labelledby="hm-cardonly-title">
      <p className="pk-overline" id="hm-cardonly-title">{`Card spending in ${monthName(month)}`}</p>
      <p className="pk-amount">{amount > 0 ? shown(amount) : 'Nothing yet'}</p>
      <p className="pk-muted">
        With only a credit card linked we can see spending, but not what comes in, so there’s
        no safe-to-spend yet.
      </p>
      <PButton onClick={onLink}>Link your chequing account</PButton>
    </section>
  );
}

/** E-03: "Use a different amount" instead of the cautious figure. */
export function IncomePanel({ s, told, onClose, onSave, onReset }) {
  const [value, setValue] = useState(told ? String(told) : '');
  const [error, setError] = useState(null);
  const submit = (e) => {
    e.preventDefault();
    const amount = parseAmount(value);
    if (!(amount > 0)) { setError('Enter what you usually take home in a month, like 3800.'); return; }
    onSave(amount).catch((err) => setError(err.message));
  };
  return (
    <DetailPanel label="Use a different amount" overline="Your income" onClose={onClose}>
      <form className="hm-form" onSubmit={submit}>
        <h1 className="pk-h2">Use a different amount</h1>
        {s.income_source === 'cautious' && s.cautious ? (
          <p className="pk-muted">
            {`We used ${shown(s.cautious.lowest)}, your lowest month of the last 3. If you expect more, tell us what you usually take home in a month. You can change it any time.`}
          </p>
        ) : s.usual ? (
          <p className="pk-muted">
            {`Pearl’s estimate is ${shown(s.usual.average)} a month, the average of ${usualMonths(s)}. If you expect something different, use your own amount. You can change it any time.`}
          </p>
        ) : null}
        <Field label="Monthly take-home pay" id="hm-override" error={error}>
          <input id="hm-override" inputMode="decimal" autoComplete="off" value={value}
                 onChange={(e) => setValue(e.target.value)} />
        </Field>
        <PButton type="submit">Save</PButton>
        {told && (s.usual || s.cautious) && (
          <PButton variant="secondary" onClick={() => onReset().catch((err) => setError(err.message))}>
            {s.usual ? `Use Pearl’s estimate (${shown(s.usual.average)})`
              : `Go back to the cautious figure (${shown(s.cautious.lowest)})`}
          </PButton>
        )}
      </form>
    </DetailPanel>
  );
}

/** The props for each snapshot row's bar (H-01, H-02, E-03). Whole dollars;
 * no $0 and no empty bar anywhere (E10). */
export function snapshotRows(snap, lens = 'need') {
  // One lens at a time: Essentials and Lifestyle, or Fixed and Variable.
  const rows = snap.rows.filter((r) => (r.lens === 'kind') === (lens === 'kind')
    || !['essentials', 'lifestyle', 'fixed', 'variable'].includes(r.key));
  return rows.map((r) => {
    if (r.key === 'income') {
      const c = r.cautious;
      if (c) {
        return { key: r.key, category: r.label, share: r.received / c.lowest,
                 value: `${r.received > 0 ? shown(r.received) : 'Nothing'} so far · usually ${shown(c.lowest)} to ${shown(c.highest)}`,
                 note: 'Freelance months vary; this updates as payments arrive' };
      }
      if (r.expected) {
        const allIn = r.received >= r.expected;
        return { key: r.key, category: r.label, share: r.received / r.expected,
                 value: r.received > 0 ? `${shown(r.received)} of ${shown(r.expected)}`
                   : `None of ${shown(r.expected)} in yet`,
                 note: allIn ? 'All of this month’s pay is in'
                   : r.next_pay ? `Next pay on ${longDate(r.next_pay)}` : null };
      }
      return { key: r.key, category: r.label, share: null,
               value: r.received > 0 ? `${shown(r.received)} so far` : 'Nothing in yet', note: null };
    }
    if (r.key === 'savings') {
      if (r.planned) {
        return { key: r.key, category: 'Put away', share: r.saved / r.planned,
                 value: r.saved > 0 ? `${shown(r.saved)} of ${shown(r.planned)} planned`
                   : `None of ${shown(r.planned)} planned yet`,
                 note: r.goal === 'anchor' ? 'Your Anchor' : 'Your saving goal' };
      }
      return { key: r.key, category: 'Put away', share: null,
               note: r.saved > 0 ? 'Moved to your savings this month' : null,
               value: r.saved > 0 ? `${shown(r.saved)} this month` : 'Nothing put away yet this month' };
    }
    // Essentials and Lifestyle: against her usual month (THL-184).
    if (r.usual > 0 && r.spent > 0) {
      return { key: r.key, category: r.label, spent: Math.round(r.spent),
               usualMonth: Math.round(r.usual), usualByToday: r.usual_by_today,
               day: snap.day, daysInMonth: snap.days_in_month,
               monthsOfHistory: snap.months_of_history };
    }
    if (r.usual > 0) {
      return { key: r.key, category: r.label, share: 0,
               value: `Nothing yet · usually ${shown(r.usual)}`, note: null };
    }
    return { key: r.key, category: r.label, share: null,
             value: r.spent > 0 ? `${shown(r.spent)} so far` : 'Nothing yet',
             note: snap.comparisons_from
               ? `We’ll compare with your usual month from ${longDate(snap.comparisons_from)}.` : null };
  });
}

/** The snapshot card (THL-48): this month so far against a usual month. */
export function Snapshot({ snap }) {
  const [lens, setLensState] = useState(readLens);
  const setLens = (l) => { setLensState(l); writeLens(l); };
  const hasKinds = snap.rows.some((r) => r.lens === 'kind');
  return (
    <section className="hm-card hm-snapshot" aria-labelledby="hm-snap-title">
      <div className="hm-row-between">
        <h2 className="pk-h3" id="hm-snap-title">
          {`${monthName(snap.month)} so far, compared with a usual month`}
        </h2>
        {hasKinds && <LensToggle lens={lens} onChange={setLens} />}
      </div>
      {snapshotRows(snap, lens).map(({ key, ...row }) => <SnapshotBar key={key} {...row} />)}
    </section>
  );
}

const PHASE_WORDS = { protect: 'Protect', build: 'Build', unveil: 'Unveil' };

/** "Build · step 2 of 2" (GR-05). */
export function stepWords(path) {
  const phase = PHASE_WORDS[path.phase];
  return path.step ? `${phase} · step ${path.step} of ${path.of}` : `${phase} · every step done`;
}

/** The path card (THL-129 GR-05): the phases, where she is, and the one next
 * step, which is Home's primary action. */
export function PathCard({ path, onPath, primary = true }) {
  return (
    <section className="hm-card hm-pathcard" aria-labelledby="hm-pathcard-title">
      <div className="hm-row-between">
        <p className="pk-overline" id="hm-pathcard-title">Your path</p>
        <button type="button" className="hm-link" onClick={() => onPath?.('path')}>
          See your path
        </button>
      </div>
      <ol className="hm-phases" aria-label="Phases">
        {path.phases.map((ph) => (
          <li key={ph.key} className={`hm-phase ${ph.state}`}
              aria-current={ph.state === 'now' ? 'step' : undefined}>
            <Mark phase={ph.key} width={38} />
            <span>{ph.label}</span>
          </li>
        ))}
      </ol>
      <div className="hm-pathcard-next">
        <div className="hm-row-text">
          <span className="pk-label pk-muted">{stepWords(path)}</span>
          <span className="pk-h3">{path.next.text}</span>
        </div>
        {primary && (
          <PButton onClick={() => onPath?.(path.next.action)}>{path.next.label}</PButton>
        )}
      </div>
    </section>
  );
}

/** H-03's path card: before anything else on the path, her income. */
export function IncomeFirstCard({ phase, onAdd }) {
  return (
    <section className="hm-card hm-income-first" aria-labelledby="hm-income-first-title">
      <div className="hm-income-first-head">
        <Mark phase={phase} width={52} />
        <div className="hm-row-text">
          <p className="pk-overline accent">{`Your path · ${PHASE_WORDS[phase]}`}</p>
          <h2 className="pk-h3" id="hm-income-first-title">First, add your income</h2>
        </div>
      </div>
      <p className="pk-label pk-muted">Needed for an accurate safe-to-spend</p>
      <ProgressBar label="Your income" value="not added yet" share={0} showLabel={false} />
      <p>It takes about 30 seconds.</p>
      <PButton onClick={onAdd}>Add your income</PButton>
    </section>
  );
}

/** "3 transactions need a look" (THL-123, H-01): hidden at 0, opens R-01. */
export function NeedsALook({ count, onReview }) {
  return (
    <section className="hm-card" aria-labelledby="hm-look-title">
      <h2 className="pk-h3" id="hm-look-title">
        {count === 1 ? '1 transaction needs a look' : `${count} transactions need a look`}
      </h2>
      <p className="pk-muted">We weren’t sure how to sort these. Sorting them keeps your numbers right.</p>
      <button type="button" className="hm-link" onClick={onReview}>
        Review <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

/** C-04: sign in to the bank again, through Plaid in update mode. */
export function ReconnectPanel({ connection, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inst = connection.institution;
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const [Plaid, { link_token: token }] = await Promise.all([
        loadPlaidScript(), createLinkToken(connection.item_id)]);
      Plaid.create({
        token,
        // Update mode: the connection carries on, so there's nothing to
        // exchange. Sync straight away so Home is current again.
        onSuccess: async () => {
          try { await syncPlaid(true); } catch { /* the next sync catches up */ }
          setBusy(false);
          onDone?.();
        },
        onExit: (err) => {
          setBusy(false);
          if (err) setError(err.display_message || err.error_message || 'Signing in didn’t finish. You can try again.');
        },
      }).open();
    } catch (err) {
      setBusy(false);
      setError(err.message);
    }
  };
  return (
    <DetailPanel label={`Sign in to ${inst} again`} overline="Reconnect" onClose={onClose}>
      <h1 className="pk-h2">{`Sign in to ${inst} again`}</h1>
      <p className="pk-muted">
        Banks ask you to sign in again every so often. It’s routine, and nothing is wrong with
        your account.
      </p>
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton onClick={start} disabled={busy}>{busy ? 'Opening…' : `Continue to ${inst}`}</PButton>
      <PButton variant="secondary" onClick={onClose}>Not now</PButton>
      <p className="pk-label pk-muted">You’ll sign in through Plaid. Pearl stays read-only.</p>
    </DetailPanel>
  );
}
