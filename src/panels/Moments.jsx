import { money, seeMoment } from '../api.js';
import { PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Mark, monthName } from './GoalsParts.jsx';
import { UnveilDone } from './Unveil.jsx';
import { monthsWords } from './GoalsAnchor.jsx';
import './home.css';
import './insights.css';
import './projections.css';
import './growth.css';

/**
 * Placement and the moments a milestone is reached (Pearl THL-130; reworded
 * without phase names, THL-238; the Anchor as THL-230 has it).
 *
 * GR-06 Where you start        The last screen of onboarding (O-12, "First
 *                              look at your path"): where she starts, with
 *                              the steps already true credited and named.
 * GR-07 Starting further along The same, past the basics. Savings she
 *                              already has give her Anchor a head start; an
 *                              investment account already linked goes
 *                              straight to GR-10.
 * GR-08 The basics done        Full screen, once, on the next app open after
 * GR-09 The Anchor at 3 months the rule passes (`/api/moments`). No confetti,
 * GR-10 Investing started      points or streaks. GR-10 is Unveil.jsx's, on
 *                              the same layout.
 *
 * Each is the hero mark in its pearl glow, an overline, a title, one line, and
 * one primary action. The internal keys (`protect`, `build`, `unveil`) name
 * the artwork and settings; she never sees them.
 */

/** What each stretch of the path is called. */
export const PHASE_TITLES = { protect: 'The basics', build: 'Your Anchor', unveil: 'Grow your money' };
const START_TITLES = { protect: 'You start with the basics', build: 'You start at your Anchor',
                       unveil: 'You start at growing your money' };

/** The shared layout: GR-06 to GR-10. */
export function MomentLayout({ phase, overline, title, sub, children, labelledBy = 'gr-moment-title' }) {
  return (
    <div className="pk hm-page pj-done gr-moment" role="region" aria-labelledby={labelledBy}>
      <div className="pj-done-mark" aria-hidden="true"><Mark phase={phase} width={115} /></div>
      <p className="pk-overline accent">{overline}</p>
      <h1 className="pk-h1" id={labelledBy}>{title}</h1>
      {sub && <p className="pk-muted gr-moment-sub">{sub}</p>}
      {children}
    </div>
  );
}

const COUNT_WORDS = ['None', 'One', 'Two', 'All three'];

/** "$5,470 · 1.9 of 3 months". */
const ofThree = (counted, months) => `${money(counted)} · ${monthsWords(months).replace(' months', '').replace(' month', '')} of 3 months`;

/** Each credited row's words: a title and one line, in her numbers. */
export function placementRows(rows) {
  return rows.map((r) => {
    switch (r.key) {
      case 'income': {
        const found = ['detected', 'confirmed', 'cautious'].includes(r.source);
        return { ...r, title: 'Confirm your income',
                 detail: !r.done ? 'We haven’t found your pay yet'
                   : r.amount > 0 ? `About ${money(r.amount)} a month, ${found ? 'found from your pay' : 'from what you told us'}`
                     : 'Confirmed' };
      }
      case 'bills':
        return { ...r, title: 'Confirm your bills',
                 detail: r.count > 0 ? `${r.count} regular bill${r.count === 1 ? '' : 's'} found`
                   : r.done ? 'Confirmed' : 'None found yet' };
      case 'essentials':
        return { ...r, title: 'Sort your first month',
                 detail: !r.month ? 'After your first full month in Pearl'
                   : r.done ? `In ${monthName(r.month)}: ${money(r.income)} came in, ${money(r.essentials)} went on Essentials`
                     : `In ${monthName(r.month)}, Essentials came to more than your income` };
      case 'protect':
        return { ...r, title: 'The basics', detail: 'Income, bills and Essentials covered' };
      case 'anchor':
        return { ...r, title: 'Grow your Anchor to 3 months',
                 detail: r.started && r.counted > 0 && r.months != null ? ofThree(r.counted, r.months)
                   : r.target > 0 ? `Three months of Essentials: ${money(r.target)}` : 'Set it up when you’re ready' };
      case 'saved_more':
        return { ...r, title: 'Save more than you spend in 2 of 3 months',
                 detail: r.known_by ? `We’ll know by ${monthName(r.known_by)}`
                   : `${r.count} of the last ${r.of || 3} months so far` };
      case 'build':
        return { ...r, title: 'Your Anchor covers 3 months',
                 detail: r.counted > 0 ? `${money(r.counted)} · 3 months of Essentials`
                   : 'Three months of Essentials put away' };
      case 'invest':
        return { ...r, title: 'Open your first investment account',
                 detail: 'Whenever you’re ready. Guidance, not a gate.' };
      default:
        return { ...r, title: r.key, detail: '' };
    }
  });
}

/** GR-06 and GR-07's line under the title. */
export function placementSub(p) {
  if (p.phase === 'protect') {
    if (p.done === 0) return 'We’ve looked at your accounts. Here are the three basic steps.';
    return `We’ve looked at your accounts. ${COUNT_WORDS[p.done]} of the three basic steps ${p.done === 1 ? 'is' : 'are'} already done.`;
  }
  if (p.credit) {
    return `You already have ${money(p.credit.amount)} in savings outside your chests, so your Anchor has a head start. Your income and bills are confirmed too.`;
  }
  if (p.phase === 'build') {
    return 'Your income covers your Essentials and your bills are known, so the basics are already done.';
  }
  return 'The basics are done, and your Anchor already covers 3 months of Essentials.';
}

/** GR-06 Where you start, and GR-07 Starting further along. */
export function Placement({ data, onContinue, busy = false, error = '' }) {
  const rows = placementRows(data.rows);
  return (
    <MomentLayout phase={data.phase} overline="Here’s where you start"
                  title={START_TITLES[data.phase]} sub={placementSub(data)}>
      <ul className="hm-card gr-credited" aria-label="Your steps">
        {rows.map((r) => (
          <li key={r.key}>
            <span className={`pj-check${r.done ? ' done' : ''}`} aria-hidden="true">
              {r.done && <PIcon name="check" size={14} />}
            </span>
            <span className="hm-row-text">
              <span>{r.title}<span className="pk-sr">{r.done ? ', done' : ', not yet'}</span></span>
              <span className="hm-row-detail">{r.detail}</span>
            </span>
          </li>
        ))}
      </ul>
      {error && <p className="pj-field-note" role="alert">{error}</p>}
      <PButton onClick={onContinue} disabled={busy}>{busy ? 'One moment…' : 'See my path'}</PButton>
    </MomentLayout>
  );
}

/** GR-08 The basics done: her money, assessed, and the Anchor is next. */
export function ProtectDone({ anchorStarted = false, target = 0, onAnchor, onLater }) {
  const milestone = target > 0 ? ` (${money(target)})` : '';
  return (
    <MomentLayout phase="build" overline="The basics · Done" title="Here’s your money, assessed"
                  sub="Your income, bills and first month are sorted. Here’s your real picture.">
      <section className="gr-unlocked" aria-labelledby="gr-unlocked-title">
        <p className="pk-overline accent">Now open</p>
        <h2 className="pk-h2" id="gr-unlocked-title">Your Anchor</h2>
        <p className="pk-label pk-muted">
          {anchorStarted
            ? `Next: grow your Anchor to 3 months of Essentials${milestone}, so a big surprise doesn’t land on your credit card.`
            : `Next: set up your Anchor by picking your savings accounts. The milestone is 3 months of Essentials${milestone}.`}
        </p>
      </section>
      <PButton onClick={onAnchor}>{anchorStarted ? 'See your Anchor' : 'Set up your Anchor'}</PButton>
      <button type="button" className="in-text-btn gr-later" onClick={onLater}>Not now</button>
    </MomentLayout>
  );
}

/** GR-09's line: "$8,700 ready for big surprises, 3 months of Essentials. …" */
export function buildDoneLine(anchor = {}) {
  const tail = 'You’ve built your buffer. Growing your money is next.';
  if (!(anchor.target > 0)) return tail;
  return `${money(anchor.target)} ready for big surprises, 3 months of Essentials. ${tail}`;
}

/** GR-09 The Anchor covers 3 months. */
export function BuildDone({ anchor, onUnveil, onGoals }) {
  return (
    <MomentLayout phase="unveil" overline="Your Anchor · Done" title="Your Anchor covers 3 months"
                  sub={buildDoneLine(anchor)}>
      <PButton onClick={onUnveil}>See what’s next</PButton>
      <button type="button" className="in-text-btn gr-later" onClick={onGoals}>Back to Save</button>
    </MomentLayout>
  );
}

/**
 * The moment the app opens on, full screen and once: it's marked seen as
 * soon as she leaves it, whichever way. `go` takes a panel key; `toReady` and
 * `toAnchor` open those pages.
 */
export function MomentScreen({ moment, onClose, go, toReady, toAnchor }) {
  const leave = (then) => async () => {
    try { await seeMoment(moment.phase); } catch { /* it plays again next time; nothing lost */ }
    onClose?.();
    then?.();
  };
  if (moment.phase === 'protect') {
    return <ProtectDone anchorStarted={!!moment.anchor?.started} target={moment.anchor?.target ?? 0}
                        onLater={leave()}
                        onAnchor={leave(() => toAnchor(moment.anchor?.started ? 'anchor' : 'start'))} />;
  }
  if (moment.phase === 'build') {
    return <BuildDone anchor={moment.anchor} onUnveil={leave(toReady)} onGoals={leave(() => go('goals'))} />;
  }
  return <UnveilDone data={{ path: moment.path, report: null }} onPath={leave(() => go('path'))} />;
}
