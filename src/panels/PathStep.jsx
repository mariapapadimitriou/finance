import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getPathStep, money, setMonthUnusual } from '../api.js';
import { Alert, PButton, StatusPill } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Mark, dayLong, monthName, rangeWords } from './GoalsParts.jsx';
import { More } from './InsightsParts.jsx';
import './home.css';
import './insights.css';
import './growth.css';

/**
 * A step on the path, on its own screen (Pearl THL-129, at
 * /growth/path/<step>): every step explains itself with her numbers (THL-10).
 *
 * GR-02 Step not done yet  Why it's not done yet, the figures behind it, and
 *                          what would help, with the one action that does.
 * GR-03 Step done          Why it's done, the figures, and that earned steps
 *                          stay earned.
 * GR-04 Keep it going      The basics are done and stay done (THL-53), but
 *                          the last full month's Essentials came to more than
 *                          its income. No red, nothing to fix; "Mark October
 *                          as unusual" (THL-59) and the month in Insights.
 *
 * The figures come from `/api/path/step/<key>`; the words are made here.
 */

export default function StepScreen({ step, nav, version }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getPathStep(step).then(setD).catch(setError);
  }, [step]);
  useEffect(() => { load(); }, [load, version]);
  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!d) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading this step…</p></div>;
  return <StepPage d={d} nav={{ ...nav, reload: load }} />;
}

const DONE_TITLES = {
  income: 'Your income is confirmed',
  bills: 'Your bills are confirmed',
  essentials: 'Your income covered your Essentials',
  setup: 'You set up your Anchor',
  full: 'Your Anchor covers 3 months',
  saved_more: 'You saved more than you spent',
  cards: 'Your card balances held steady',
  invest: 'You opened your first investment account',
};
const MONTHLY = ['essentials', 'full', 'saved_more', 'cards'];

const article = (label) => (label === 'Not sure' ? 'an investing account'
  : label === 'Non-registered' ? 'a non-registered account'
    : `${label === 'TFSA' ? 'a' : 'an'} ${label}`);

/** Money that is never shown as $0: "Nothing yet" instead. */
const held = (n) => (n > 0.004 ? money(n) : 'Nothing yet');

const lowerFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);

/** "Your next step stays the same: grow your Anchor to 3 months of Essentials." */
export function nextSentence(d) {
  const text = d.next?.text ?? '';
  if (!text.startsWith('Next: ')) return '';
  const [first] = text.slice(6).split(', so ');
  return `Your next step stays the same: ${lowerFirst(first).replace(/\.$/, '')}.`;
}

/**
 * Everything a step's screen says, from its figures: the title, the "why"
 * card (a line, rows and a total), how it was worked out, and what would
 * help (a line and actions, at most one of them primary).
 */
export function stepCopy(d, nav = {}) {
  const f = d.facts ?? {};
  const done = d.state === 'done' || d.state === 'lapsed';
  const out = { title: done ? DONE_TITLES[d.key] : d.label, why: { rows: [] }, how: null, help: null };
  const month = f.month ? monthName(f.month) : '';
  const goals = (view) => () => nav.toGoals?.(view);
  switch (d.key) {
    case 'income': {
      const found = ['detected', 'confirmed', 'cautious'].includes(f.source);
      out.why.text = done
        ? (found ? `Pearl found your pay${f.payer ? ` from ${f.payer}` : ''}${f.confirmed ? ', and you confirmed it.' : '.'}`
          : 'You told Pearl what you earn.')
        : 'Pearl hasn’t found regular pay yet. Your income is where safe-to-spend starts.';
      if (f.amount > 0) out.why.rows.push({ label: 'Coming in this month', value: money(f.amount) });
      if (!done) {
        out.help = { text: 'Add what you earn, or confirm the pay we found.',
                     actions: [{ label: 'Add your income', go: () => nav.onTab?.('income') }] };
      }
      break;
    }
    case 'bills':
      out.why.text = done ? (f.confirmed ? 'You confirmed your regular bills.' : 'Pearl found your regular bills.')
        : 'Pearl hasn’t found a regular bill yet, or you haven’t checked the ones it found.';
      if (f.count > 0) out.why.rows.push({ label: 'Regular bills', value: `${f.count}` });
      if (f.to_come > 0) out.why.rows.push({ label: 'Still to come this month', value: money(f.to_come) });
      if (!done) {
        out.help = { text: 'Check the bills we found, so none of them is a surprise.',
                     actions: [{ label: 'Check your bills', go: () => nav.onTab?.('income') }] };
      }
      break;
    case 'essentials':
      if (f.month) {
        out.why.rows = [{ label: 'Income', value: money(f.income) },
                        { label: 'Essentials', value: money(f.essentials) }];
        out.how = `Income is the pay and other money that came in during ${month}, not transfers between your own accounts. Essentials are the categories marked Essentials, like rent, groceries and bills, and only your share of anything split.`;
      }
      if (done) {
        out.why.text = f.month ? `In ${month}, your income covered your Essentials with money left over.`
          : 'Your income covered your Essentials.';
        if (f.month && f.left > 0.004) out.why.total = { label: 'Left over', value: money(f.left) };
      } else if (f.month) {
        out.why.text = `This is done when a month’s income covers your Essentials. In ${month}, it didn’t quite.`;
        out.why.total = { label: 'Short by', value: money(f.essentials - f.income) };
        out.help = { text: `We check again on ${dayLong(d.next_check)}. A month where what comes in covers your Essentials will do it.`,
                     actions: [{ label: `See ${month} in Insights`, go: () => nav.toInsights?.(f.month) }] };
      } else {
        out.why.text = 'We’ll know after your first full month.';
        out.help = { text: `We check on ${dayLong(d.next_check)}.`, actions: [] };
      }
      break;
    case 'setup':
      if (done) {
        out.why.text = `You picked the savings accounts that make up your Anchor${f.accounts > 0 ? ` (${f.accounts})` : ''}.`;
        if (f.counted > 0) out.why.rows.push({ label: 'Your Anchor now', value: money(f.counted) });
        out.how = 'Your Anchor is what those accounts hold, less what your treasure chests hold.';
      } else {
        out.why.text = 'Pick the savings accounts that make up your Anchor. Pearl adds them up and takes out what your chests hold.';
        out.help = { text: 'It takes a minute. Nothing moves; Pearl only reads the balances.',
                     actions: [{ label: 'Set up your Anchor', go: goals('start') }] };
      }
      break;
    case 'full': {
      if (f.target > 0) out.why.rows.push({ label: '3 months of your usual Essentials', value: money(f.target) });
      if (f.started) out.why.rows.push({ label: 'Your Anchor now', value: held(f.counted) });
      out.how = 'A usual month of Essentials is the average of your last 3 full months, rounded; unusual months are left out. Your Anchor is what the accounts you picked hold, less what your treasure chests hold.';
      if (done) {
        out.why.text = 'Your Anchor covers 3 months of your usual Essentials.';
      } else {
        out.why.text = 'This is done when your Anchor, the cash savings you choose less what your chests hold, covers 3 months of your usual Essentials.';
        if (f.started && f.to_go > 0) out.why.total = { label: 'Still to go', value: money(f.to_go) };
        if (f.started) {
          const chests = f.chests_monthly > 0.004 ? `: what you put away, less the ${money(f.chests_monthly)} your chests take` : '';
          const pace = f.pace > 0.004 ? `Your Anchor grows about ${money(f.pace)} a month${chests}.` : '';
          const when = f.projection
            ? ` At this pace you’ll likely reach 3 months between ${rangeWords(f.projection.from, f.projection.to)}.` : '';
          out.help = { text: pace ? `${pace}${when}` : 'Anything you put away moves it along.',
                       actions: [{ label: 'See your Anchor', go: goals('anchor') }] };
        } else {
          out.help = { text: 'Set up your Anchor, and we’ll show how it grows.',
                       actions: [{ label: 'Set up your Anchor', go: goals('start') }] };
        }
      }
      break;
    }
    case 'saved_more':
      out.why.text = done ? 'You saved more than you spent in 2 of the last 3 months.'
        : 'This counts once you save more than you spend in 2 of the last 3 months.';
      out.why.rows = (f.months ?? []).map((m) => {
        const diff = Math.abs(m.income - m.spent);
        const value = diff < 0.5 ? 'Even' : m.saved ? `${money(diff)} saved` : `${money(diff)} more spent`;
        return { label: monthName(m.month), value };
      });
      out.how = 'Saved means more came in than went out that month, leaving aside transfers between your own accounts.';
      if (!done && f.known_by) out.help = { text: `We’ll know by ${monthName(f.known_by)}.`, actions: [] };
      break;
    case 'cards': {
      const cards = f.cards ?? [];
      if (cards.length === 0) {
        out.why.text = 'There’s no credit card to check.';
      } else {
        out.why.text = done
          ? `In ${month || 'the last full month'}, what you paid on your cards covered what you spent.`
          : `In ${month || 'the last full month'}, a card balance grew: more went on it than was paid back.`;
        out.why.rows = cards.map((c) => ({ label: c.name,
                                           value: c.grew_by > 0.004 ? `Grew by ${money(c.grew_by)}` : 'Held steady' }));
        if (!done) {
          out.help = { text: 'Paying back at least what goes on a card each month keeps it from growing.', actions: [] };
        }
      }
      break;
    }
    case 'invest':
      if (done) {
        out.why.text = f.report ? `You told Pearl you opened ${article(f.report.label)}.`
          : 'An investment account is linked.';
        if (f.report) out.extra = { label: 'Change the kind of account', go: () => nav.toUnveil?.() };
      } else {
        out.why.text = 'This is done when you open your first investment account, wherever you choose.';
        out.help = { text: 'When you’re ready, tell Pearl and that milestone is done. Guidance, not a gate.',
                     actions: [{ label: 'I’ve opened one', go: () => nav.toUnveil?.() },
                               { label: 'See the checklist', go: () => nav.toReady?.(), variant: 'link' }] };
      }
      break;
    default:
      out.why.text = '';
  }
  if (done) {
    out.alert = MONTHLY.includes(d.key)
      ? `Checked on ${dayLong(d.checked_on)}. We check again each month, and earned steps stay earned, even after a rough month.`
      : 'Earned steps stay earned, even after a rough month.';
  }
  return out;
}

/** GR-04's opening line: what pushed Essentials past income. */
export function lapseLine(f) {
  const short = f.essentials - f.income;
  const words = short <= f.income * 0.15 ? 'a little more than' : 'more than';
  const b = f.biggest;
  if (b && b.amount >= short && b.amount >= f.essentials * 0.2) {
    return `One charge of ${money(b.amount)} at ${b.merchant} pushed Essentials to ${money(f.essentials)}, ${words} your income of ${money(f.income)}. That happens.`;
  }
  return `Essentials came to ${money(f.essentials)}, ${words} your income of ${money(f.income)}. That happens.`;
}

function BackLink({ onClick, children }) {
  return (
    <button type="button" className="in-back" onClick={onClick}>
      <PIcon name="chevronRight" size={12} className="in-flip" /> {children}
    </button>
  );
}

function Rows({ rows, total }) {
  return (
    <dl className="pj-parts gr-rows">
      {rows.map((r) => <div key={r.label}><dt>{r.label}</dt><dd>{r.value}</dd></div>)}
      {total && <div className="strong"><dt>{total.label}</dt><dd className="gr-total">{total.value}</dd></div>}
    </dl>
  );
}

function Head({ d, title }) {
  const overline = d.also ? `${d.phase_label} · Also counts` : `${d.phase_label} · Step ${d.index} of ${d.of}`;
  return (
    <div className="pj-title-row">
      <div className="hm-head">
        <p className="pk-overline accent">{overline}</p>
        <h1 className="pk-h1">{title}</h1>
      </div>
      <Mark phase={d.phase} width={58} />
    </div>
  );
}

const PILLS = {
  done: <StatusPill icon="check" tone="positive">Done</StatusPill>,
  now: <StatusPill icon="info" tone="info">In progress</StatusPill>,
  todo: <StatusPill icon="clock" tone="neutral">Not yet</StatusPill>,
  ahead: <StatusPill icon="clock" tone="neutral">Ahead</StatusPill>,
};

/** GR-02 and GR-03 (and GR-04 for a lapsed step). */
export function StepPage({ d, nav }) {
  const [how, setHow] = useState(false);
  if (d.state === 'lapsed') return <KeepItGoing d={d} nav={nav} />;
  const c = stepCopy(d, nav);
  const done = d.state === 'done';
  return (
    <div className="pk hm-page in-page gr-step">
      <header className="in-detail-head">
        <div className="in-back-row"><BackLink onClick={nav.back}>Path</BackLink></div>
        <Head d={d} title={c.title} />
        <div className="gr-pills">{PILLS[d.state]}</div>
      </header>
      <section className="hm-card in-card" aria-labelledby="gr-why-title">
        <h2 className="pk-h2" id="gr-why-title">{done ? 'Why it’s done' : 'Why it’s not done yet'}</h2>
        {c.why.text && <p className="pj-body pk-muted">{c.why.text}</p>}
        {(c.why.rows.length > 0 || c.why.total) && <Rows rows={c.why.rows} total={c.why.total} />}
        {c.how && (
          <>
            <button type="button" className="in-more gr-how" aria-expanded={how} onClick={() => setHow(!how)}>
              How we worked this out<span aria-hidden="true">  ›</span>
            </button>
            {how && <p className="pk-label pk-muted">{c.how}</p>}
          </>
        )}
        {c.extra && <More onClick={c.extra.go}>{c.extra.label}</More>}
      </section>
      {c.help && (c.help.text || c.help.actions.length > 0) && (
        <section className="hm-card in-card" aria-labelledby="gr-help-title">
          <h2 className="pk-h2" id="gr-help-title">What would help</h2>
          {c.help.text && <p className="pj-body">{c.help.text}</p>}
          {c.help.actions.length > 0 && (
            <div className="gr-actions">
              {c.help.actions.map((a, i) => (a.variant === 'link'
                ? <More key={a.label} onClick={a.go}>{a.label}</More>
                : <PButton key={a.label} variant={i === 0 ? 'primary' : 'secondary'} onClick={a.go}>{a.label}</PButton>))}
            </div>
          )}
        </section>
      )}
      {c.alert && <Alert tone="info">{c.alert}</Alert>}
    </div>
  );
}

/** GR-04 Keep it going. */
export function KeepItGoing({ d, nav }) {
  const f = d.facts;
  const month = monthName(f.month);
  const [unusual, setUnusual] = useState(!!f.unusual);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mark = async (value) => {
    setBusy(true); setError('');
    try {
      await (nav.markUnusual ?? setMonthUnusual)(f.month, value);
      setUnusual(value);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const next = nextSentence(d);
  return (
    <div className="pk hm-page in-page gr-step">
      <header className="in-detail-head">
        <div className="in-back-row"><BackLink onClick={nav.back}>Path</BackLink></div>
        <Head d={d} title="Keep it going" />
        <div className="gr-pills">
          {PILLS.done}
          <StatusPill icon={null} tone="neutral">Keep it going</StatusPill>
        </div>
      </header>
      <section className="hm-card in-card" aria-labelledby="gr-lapse-title">
        <h2 className="pk-h2" id="gr-lapse-title">{`${month} was a bigger month`}</h2>
        <p className="pj-body">{lapseLine(f)}</p>
        <Rows rows={[{ label: 'Income', value: money(f.income) },
                     { label: 'Essentials', value: money(f.essentials) }]} />
        <p className="pj-body gr-rule">The basics stay done. Nothing to fix; this is just so you know.</p>
        <div className="gr-actions">
          {unusual ? (
            <p className="pk-label pk-muted" role="status">
              {`${month} is marked unusual, so it’s left out of your usual month. `}
              <button type="button" className="in-text-btn" disabled={busy} onClick={() => mark(false)}>
                Put it back
              </button>
            </p>
          ) : (
            <PButton variant="secondary" disabled={busy} onClick={() => mark(true)}>
              {`Mark ${month} as unusual`}
            </PButton>
          )}
          <More onClick={() => nav.toInsights?.(f.month)}>{`See ${month} in Insights`}</More>
        </div>
        {error && <p className="pj-field-note" role="alert">{error}</p>}
      </section>
      <section className="hm-card in-card" aria-labelledby="gr-next-title">
        <h2 className="pk-h3" id="gr-next-title">What happens next</h2>
        <p className="pj-body pk-muted">{`We check again on ${dayLong(d.next_check)}.${next ? ` ${next}` : ''}`}</p>
      </section>
    </div>
  );
}
