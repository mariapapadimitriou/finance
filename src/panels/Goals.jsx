import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getGoals } from '../api.js';
import { takeGoalsIntent } from '../router.js';
import {
  AnchorAccounts, AnchorCard, AnchorDetail, StartAnchor, TargetExplained,
} from './GoalsAnchor.jsx';
import { HowWorkedOut, ProjectionPage, UnusualMonths, WhatIf } from './GoalsProjection.jsx';
import { ChestDetail, ChestForm, ChestsSection } from './GoalsChests.jsx';
import { More, amount, monthYear } from './GoalsParts.jsx';

/**
 * Goals (Pearl Handoff: THL-131 Anchor, THL-132 projection, THL-179 overview
 * and treasure chests).
 *
 * The Anchor is pinned at the top and is the only goal with the phase's
 * shell; treasure chests and the saving goal sit below in a neutral style and
 * never move the phase. The Anchor's page, its projection and each chest open
 * inside this one, and the overline on each leads back.
 */
export default function Goals({ onTab, onChanged, version }) {
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState({ name: 'overview' });
  const [panel, setPanel] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return getGoals().then(setGoals).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  // Sent here by a recommendation (THL-12 R3): open where it said.
  const [intent, setIntent] = useState(takeGoalsIntent);
  useEffect(() => {
    if (!goals || !intent) return;
    setIntent(null);
    if (!goals.anchor.started) {
      if (intent.view === 'start') setPanel({ name: 'start' });
    } else if (intent.view === 'whatif') {
      setView({ name: 'projection' });
      setPanel({ name: 'whatif', monthly: intent.monthly });
    } else if (intent.view === 'anchor') {
      setView({ name: 'anchor' });
    }
  }, [goals, intent]);

  const go = (next) => {
    setView(next);
    window.scrollTo?.({ top: 0 });
  };
  // A change here can move safe to spend, so the rest of the app reloads too.
  const changed = useCallback(async () => {
    await load();
    onChanged?.();
  }, [load, onChanged]);
  // Endpoints that change the Anchor answer with the whole page's data.
  const took = (result) => { if (result?.anchor) setGoals(result); };

  if (error) return <div className="pk gl-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!goals) return <div className="pk gl-page"><p className="pk-muted" role="status">Loading your goals…</p></div>;

  const close = () => setPanel(null);
  let page;
  if (view.name === 'anchor' && goals.anchor.started) {
    page = (
      <AnchorDetail goals={goals} onBack={() => go({ name: 'overview' })}
                    onProjection={() => go({ name: 'projection' })}
                    onAccounts={() => setPanel({ name: 'accounts' })}
                    onExplain={() => setPanel({ name: 'explain' })} />
    );
  } else if (view.name === 'projection' && goals.anchor.started) {
    page = (
      <ProjectionPage goals={goals} onBack={() => go({ name: 'anchor' })} onTab={onTab}
                      onHow={() => setPanel({ name: 'how' })}
                      onWhatIf={() => setPanel({ name: 'whatif' })}
                      onMonths={() => setPanel({ name: 'months' })} />
    );
  } else if (view.name === 'chest') {
    page = (
      <ChestDetail goals={goals} id={view.id} version={version} onChanged={changed}
                   onBack={() => go({ name: 'overview' })} />
    );
  } else {
    page = (
      <Overview goals={goals} onTab={onTab}
                onStart={() => setPanel({ name: 'start' })}
                onAnchor={() => go({ name: 'anchor' })}
                onNewChest={(preset) => setPanel({ name: 'chest', preset })}
                onChest={(id) => go({ name: 'chest', id })} />
    );
  }

  return (
    <div className="pk gl-page">
      {page}

      {panel?.name === 'start' && (
        <StartAnchor goals={goals} onClose={close} onDone={took}
                     onSeeAnchor={() => { close(); go({ name: 'anchor' }); }} />
      )}
      {panel?.name === 'change' && (
        <StartAnchor goals={goals} editing onClose={close} onDone={took} onSeeAnchor={close} />
      )}
      {panel?.name === 'explain' && (
        <TargetExplained goals={goals} onClose={close}
                         onChange={() => setPanel({ name: 'change' })} />
      )}
      {panel?.name === 'accounts' && (
        <AnchorAccounts goals={goals} onClose={close} onDone={took} />
      )}
      {panel?.name === 'how' && (
        <HowWorkedOut goals={goals} onClose={close}
                      onMonths={() => setPanel({ name: 'months' })} />
      )}
      {panel?.name === 'whatif' && <WhatIf goals={goals} onClose={close} initial={panel.monthly ?? null} />}
      {panel?.name === 'months' && (
        <UnusualMonths goals={goals} onClose={close} onDone={took} />
      )}
      {panel?.name === 'chest' && (
        <ChestForm goals={goals} preset={panel.preset} onClose={close} onSaved={changed}
                   onStartAnchor={() => setPanel({ name: 'start' })} />
      )}
    </div>
  );
}

/** G-01 and G-02: the Anchor on top, chests below, then the saving goal. */
function Overview({ goals, onTab, onStart, onAnchor, onNewChest, onChest }) {
  return (
    <>
      <header className="gl-head">
        <p className="pk-overline accent">{monthYear(goals.month)}</p>
        <h1 className="pk-h1">Goals</h1>
      </header>
      <AnchorCard goals={goals} onStart={onStart} onOpen={onAnchor} onTab={onTab} />
      <ChestsSection goals={goals} onNew={onNewChest} onOpen={onChest}
                     onTreasure={onChest} />
      <SavingGoal goal={goals.saving_goal} onTab={onTab} />
    </>
  );
}

/** The plan's saving goal (THL-170), against what last month put away. */
function SavingGoal({ goal, onTab }) {
  if (!goal.set) {
    return (
      <section className="gl-card gl-row-card gl-goal" aria-label="Saving goal">
        <p className="gl-text gl-grow">No saving goal yet</p>
        <More onClick={() => onTab('plan')}>Set one</More>
      </section>
    );
  }
  const rate = goal.rate ? `${Math.round(goal.rate * 100)}% of take-home` : `${amount(goal.target)} a month`;
  return (
    <section className="gl-card gl-row-card gl-goal" aria-label="Saving goal">
      <div className="gl-stack gl-grow">
        <p className="pk-overline accent">Saving goal · {rate}</p>
        <p className="gl-text">
          {goal.last_month
            ? `Last month you saved ${amount(goal.saved)} of ${amount(goal.target)}`
            : `${amount(goal.target)} a month`}
        </p>
      </div>
      <More onClick={() => onTab('plan')}>{goal.saved >= goal.target ? 'See your plan' : 'See the gap'}</More>
    </section>
  );
}
