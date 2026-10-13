import { money, seeMoment } from '../api.js';
import { PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Mark, monthName } from './GoalsParts.jsx';
import { More } from './InsightsParts.jsx';
import { UnveilDone } from './Unveil.jsx';
import './home.css';
import './insights.css';
import './projections.css';
import './growth.css';

/**
 * Placement and the moments a phase is done (Pearl THL-130).
 *
 * GR-06 Where you start        The last screen of onboarding (O-12, "First
 *                              look at your path"): the phase she starts in,
 *                              with the steps already true credited and named.
 * GR-07 Starting further along The same, past Protect. Savings that already
 *                              hold a month of Essentials are counted as her
 *                              Anchor; an investment account already linked
 *                              goes straight to GR-10.
 * GR-08 Protect done           Full screen, once, on the next app open after
 * GR-09 Build done             the rule passes (`/api/moments`). No confetti,
 * GR-10 Unveil done            points or streaks. GR-10 is Unveil.jsx's, on
 *                              the same layout.
 *
 * Each is the hero mark in its pearl glow, an overline, a title, one line, and
 * one primary action.
 */

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
        return { ...r, title: 'Your income covers your Essentials',
                 detail: !r.month ? 'We’ll know after your first full month'
                   : r.done ? `In ${monthName(r.month)}: ${money(r.income)} came in, ${money(r.essentials)} went on Essentials`
                     : `In ${monthName(r.month)}, Essentials came to more than your income` };
      case 'protect':
        return { ...r, title: 'Protect', detail: 'Income, bills and Essentials covered' };
      case 'anchor':
        return { ...r, title: 'Fill your Anchor',
                 detail: r.started && r.counted > 0 && r.target > 0 ? `${money(r.counted)} of ${money(r.target)}`
                   : r.target > 0 ? `One month of Essentials: ${money(r.target)}` : 'Start it when you’re ready' };
      case 'saved_more':
        return { ...r, title: 'Save more than you spend in 2 of 3 months',
                 detail: r.known_by ? `We’ll know by ${monthName(r.known_by)}`
                   : `${r.count} of the last ${r.of || 3} months so far` };
      case 'build':
        return { ...r, title: 'Fill your Anchor',
                 detail: r.counted > 0 && r.target > 0 ? `${money(r.counted)} of ${money(r.target)}`
                   : 'One month of Essentials set aside' };
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
    if (p.done === 0) return 'We’ve looked at your accounts. Here are the three Protect steps.';
    return `We’ve looked at your accounts. ${COUNT_WORDS[p.done]} of the three Protect steps ${p.done === 1 ? 'is' : 'are'} already done.`;
  }
  if (p.credit) {
    return `You already have ${money(p.credit.amount)} in savings, more than a month of Essentials. We’ve counted it as your Anchor.`;
  }
  if (p.phase === 'build') {
    return 'Your income covers your Essentials and your bills are known, so Protect is already done.';
  }
  return 'Protect and Build are already done: your Anchor holds a month of Essentials.';
}

const PHASE_TITLES = { protect: 'Protect', build: 'Build', unveil: 'Unveil' };

/** GR-06 Where you start, and GR-07 Starting further along. */
export function Placement({ data, onContinue, busy = false, error = '' }) {
  const rows = placementRows(data.rows);
  return (
    <MomentLayout phase={data.phase} overline="Here’s where you start"
                  title={`You start in ${PHASE_TITLES[data.phase]}`} sub={placementSub(data)}>
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

/** GR-08 Protect done: Ready to invest is open, the Anchor is next. */
export function ProtectDone({ anchorStarted = false, onAnchor, onReady, onLater }) {
  return (
    <MomentLayout phase="build" overline="Protect · Done" title="Protect is done"
                  sub="Your income covers your Essentials and your bills are known. That’s the base everything else sits on.">
      <section className="gr-unlocked" aria-labelledby="gr-unlocked-title">
        <p className="pk-overline accent">Now open</p>
        <h2 className="pk-h2" id="gr-unlocked-title">Ready to invest</h2>
        <p className="pk-label pk-muted">A checklist to help you decide when you’re ready. Guidance, not a gate.</p>
        <More onClick={onReady}>See the checklist</More>
      </section>
      <PButton onClick={onAnchor}>{anchorStarted ? 'See your Anchor' : 'Start your Anchor'}</PButton>
      <button type="button" className="in-text-btn gr-later" onClick={onLater}>Not now</button>
    </MomentLayout>
  );
}

const SIZE_WORDS = { 1: 'one month of Essentials', 2: 'two months of Essentials', 3: 'three months of Essentials' };

/** GR-09's line: "$2,150 set aside: one month of Essentials. …" */
export function buildDoneLine(anchor = {}) {
  const tail = 'You’ve built your buffer. Unveil is next.';
  if (!(anchor.target > 0)) return tail;
  const what = SIZE_WORDS[anchor.size ?? 1] ?? 'the target you set';
  return `${money(anchor.target)} set aside: ${what}. ${tail}`;
}

/** GR-09 Build done: the Anchor is full. */
export function BuildDone({ anchor, onUnveil, onGoals }) {
  return (
    <MomentLayout phase="unveil" overline="Build · Done" title="Your Anchor is full" sub={buildDoneLine(anchor)}>
      <PButton onClick={onUnveil}>See what Unveil means</PButton>
      <button type="button" className="in-text-btn gr-later" onClick={onGoals}>Back to Goals</button>
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
    return <ProtectDone anchorStarted={!!moment.anchor?.started} onLater={leave()}
                        onReady={leave(toReady)}
                        onAnchor={leave(() => toAnchor(moment.anchor?.started ? 'anchor' : 'start'))} />;
  }
  if (moment.phase === 'build') {
    return <BuildDone anchor={moment.anchor} onUnveil={leave(toReady)} onGoals={leave(() => go('goals'))} />;
  }
  return <UnveilDone data={{ path: moment.path, report: null }} onPath={leave(() => go('path'))} />;
}
