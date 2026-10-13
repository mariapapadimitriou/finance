import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getPath, money } from '../api.js';
import { PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import {
  onPathUrl, readPathUrl, setGoalsIntent, writeInsightsUrl, writePathUrl, writeProjectionsUrl,
} from '../router.js';
import { Mark, More } from './GoalsParts.jsx';
import { monthName, stepWords } from './HomePanel.jsx';
import { GrowthTabs } from './InsightsParts.jsx';
import StepScreen from './PathStep.jsx';
import './home.css';
import './insights.css';
import './growth.css';

/**
 * Growth › Path (THL-129 GR-01, at /growth): Protect → Build → Unveil, the
 * steps of the phase she's in with her own numbers, what else counts toward
 * Build, the one next step, and Ready to invest once Protect is done.
 *
 * Progress is in steps, never dollars (THL-129). Ahead phases show no steps
 * until they're current. Each step says where it stands in one line and
 * opens its own screen (GR-02 to GR-04, PathStep.jsx) at /growth/path/<step>.
 * When a rough month follows a done Protect, its card says "Keep it going"
 * and opens GR-04; Protect stays done.
 *
 * Ready to invest opens the readiness checklist (THL-135 GR-16), and the
 * Unveil card asks "Opened an investing account?" (THL-195 GR-37); both
 * live under Growth › Projections' addresses (Unveil.jsx).
 */

const PHASE_TEXT = {
  protect: 'Income, bills and Essentials covered',
  build: 'Your Anchor: one month of Essentials',
  unveil: 'Your first investment account',
};
const STATE_WORDS = { done: 'Done', now: 'Now', ahead: 'Ahead' };
const ACTIONS = { goals: 'goals', path: 'path', bills: 'income', income: 'income' };

/** One line on where a step stands, in her numbers where there are any. */
export function stepDetail(step, current) {
  if (step.done) return 'Done';
  if (step.key === 'essentials' && step.month) {
    return `In ${monthName(step.month)}: ${money(step.income)} came in, ${money(step.essentials)} went on Essentials`;
  }
  if (step.key === 'first_stop' && step.first_stop) return `Your first stop is ${money(step.first_stop)}`;
  if (step.key === 'full' && step.target) return `One month of Essentials: ${money(step.target)}`;
  if (step.key === 'saved_more') return `${step.count} of ${step.of} months so far`;
  if (step.key === 'cards') return 'A card balance grew last month';
  return current ? 'In progress' : 'Not yet';
}

export default function PathPanel({ onTab, version }) {
  const [route, setRoute] = useState(() => readPathUrl() ?? { step: '' });
  const [path, setPath] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => onPathUrl(() => {
    const next = readPathUrl();
    if (next) setRoute(next);
  }), []);
  const load = useCallback(() => {
    setError(null);
    return getPath().then(setPath).catch(setError);
  }, []);
  useEffect(() => { if (!route.step) load(); }, [load, version, route.step]);

  const open = (view) => { writeProjectionsUrl(view); onTab?.('projections'); };
  const show = (step) => { writePathUrl({ step }); window.scrollTo?.({ top: 0 }); };
  if (route.step) {
    const nav = {
      onTab, back: () => show(''), toReady: () => open('ready'), toUnveil: () => open('unveil'),
      toGoals: (view) => { setGoalsIntent({ view }); onTab?.('goals'); },
      toInsights: (month) => { writeInsightsUrl({ view: 'month', month }); onTab?.('insights'); },
    };
    return <StepScreen step={route.step} nav={nav} version={version} />;
  }
  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!path) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading your path…</p></div>;
  return <PathPage path={path} onAction={(a) => onTab?.(ACTIONS[a] ?? 'path')} onTab={onTab}
                   onStep={show} onReady={() => open('ready')} onUnveil={() => open('unveil')} />;
}

/** Has she opened an investing account, by her word or a linked one? */
const unveiled = (path) => path.phase === 'unveil' && path.steps.every((s) => s.done);

export function PathPage({ path, onAction, onReady, onUnveil, onStep, onTab }) {
  const phase = path.phases.find((p) => p.state === 'now');
  const current = path.step ? path.step - 1 : -1;
  return (
    <div className="pk hm-page in-page">
      <header className="hm-head">
        <p className="pk-overline accent">Your path</p>
        <h1 className="pk-h1">Growth</h1>
      </header>
      <GrowthTabs current="path" onTab={onTab} />

      <ol className="pt-phases" aria-label="Phases">
        {path.phases.map((p) => (
          <li key={p.key} className={`hm-card pt-phase ${p.state}`}
              aria-current={p.state === 'now' ? 'step' : undefined}>
            <Mark phase={p.key} width={72} />
            <span className="pk-h3">{p.label}</span>
            <span className="gr-pills">
              <span className={`pk-pill pt-state ${p.state}`}>{STATE_WORDS[p.state]}</span>
              {p.key === 'protect' && path.lapse && <span className="pk-pill neutral">Keep it going</span>}
            </span>
            <span className="pk-label pk-muted">{PHASE_TEXT[p.key]}</span>
            {p.key === 'protect' && path.lapse && onStep && (
              <More onClick={() => onStep('essentials')}>{`What happened in ${monthName(path.lapse.month)}`}</More>
            )}
            {p.key === 'unveil' && path.protect_done && !unveiled(path) && onUnveil && (
              <More onClick={onUnveil}>Opened one? Tell Pearl</More>
            )}
          </li>
        ))}
      </ol>

      <section className="hm-card pt-steps" aria-labelledby="pt-steps-title">
        <div className="hm-row-between">
          <h2 className="pk-h2" id="pt-steps-title">{`Steps in ${phase.label}`}</h2>
          <span className="pk-pill">{stepWords(path)}</span>
        </div>
        <StepList steps={path.steps} current={current} onStep={onStep} />
        {path.also.length > 0 && (
          <>
            <p className="pk-overline">{`Also counts toward ${phase.label}`}</p>
            <StepList steps={path.also} current={-1} onStep={onStep} />
          </>
        )}
      </section>

      <div className="pt-bottom">
        <section className="hm-card" aria-labelledby="pt-next-title">
          <p className="pk-overline">Your next step</p>
          <h2 className="pk-h2" id="pt-next-title">{path.next.text.replace(/^Next: /, '')}</h2>
          {path.next.action !== 'path' && (
            <PButton onClick={() => onAction(path.next.action)}>{path.next.label}</PButton>
          )}
        </section>
        {path.protect_done && (
          <section className="hm-card" aria-labelledby="pt-invest-title">
            <p className="pk-overline">Open since you finished Protect</p>
            <h2 className="pk-h2" id="pt-invest-title">Ready to invest</h2>
            <p className="pk-muted">A checklist to help you decide. Guidance, not a gate.</p>
            {onReady && <More onClick={onReady}>See the checklist</More>}
          </section>
        )}
      </div>
    </div>
  );
}

function StepList({ steps, current, onStep }) {
  return (
    <ul className="pt-list">
      {steps.map((s, i) => {
        const inner = (
          <>
            <span className={`pt-status ${s.done ? 'done' : i === current ? 'now' : ''}`} aria-hidden="true">
              {s.done && <PIcon name="check" size={16} />}
            </span>
            <span className="hm-row-text">
              <span>{s.label}<span className="pk-sr">{s.done ? ', done' : ', not done yet'}</span></span>
              <span className="hm-row-detail">{stepDetail(s, i === current)}</span>
            </span>
          </>
        );
        return (
          <li key={s.key}>
            {onStep ? (
              <button type="button" className="pt-step" onClick={() => onStep(s.key)}>
                {inner}
                <PIcon name="chevronRight" size={16} className="pt-step-go" />
              </button>
            ) : inner}
          </li>
        );
      })}
    </ul>
  );
}
