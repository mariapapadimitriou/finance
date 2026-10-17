import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getGoals, getLearn } from '../api.js';
import {
  onSaveUrl, readSaveUrl, takeGoalsIntent, writeProjectionsUrl, writeSaveUrl,
} from '../router.js';
import {
  AnchorAccounts, AnchorCard, AnchorDetail, StartAnchor, TargetExplained,
} from './GoalsAnchor.jsx';
import { HowWorkedOut, ProjectionPage, UnusualMonths, WhatIf } from './GoalsProjection.jsx';
import { ChestDetail, ChestForm, ChestsSection } from './GoalsChests.jsx';
import { More, amount, monthYear, rangeShort } from './GoalsParts.jsx';
import { CALC_START, calculator, dollarsWords } from './projectionsMath.js';
import { MODULES } from './learnModules.js';

/**
 * Save (Pearl Handoff › Save, THL-240 SV-P01 to SV-P03; THL-248), at /save.
 *
 * In this order: the Anchor (THL-131), treasure chests (THL-169, THL-179),
 * then "What this could grow into" — when the Anchor reaches 3 months (the
 * projection, THL-132, at /save/anchor/projection), what regular investing
 * could grow to (the calculator, THL-135, at /save/calculator) and Learn at
 * your pace (THL-134, at /save/learn) — and the illustrative-rates footnote.
 * Someone new sees no projection card until the Anchor is set up; the
 * calculator and Learn are always open, nothing is locked behind a
 * milestone. Calm and illustrative: no product names, no recommendations.
 *
 * The Anchor's page (/save/anchor), its projection and each chest open
 * inside this one, and the overline on each leads back.
 */
export default function Goals({ onTab, onChanged, version }) {
  const [goals, setGoals] = useState(null);
  const [learn, setLearn] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState(() => ({ name: readSaveUrl()?.view || 'overview' }));
  const [panel, setPanel] = useState(null);

  const load = useCallback(() => {
    setError(null);
    getLearn().then(setLearn).catch(() => setLearn(null));
    return getGoals().then(setGoals).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  // Back and forward between Save's own addresses.
  useEffect(() => onSaveUrl(() => {
    const next = readSaveUrl();
    if (next) setView({ name: next.view || 'overview' });
  }), []);

  const go = (next) => {
    setView(next);
    if (['overview', 'anchor', 'projection'].includes(next.name)) {
      writeSaveUrl(next.name === 'overview' ? '' : next.name);
    }
    window.scrollTo?.({ top: 0 });
  };

  // Sent here by a recommendation (THL-12 R3) or the moments: open where it said.
  const [intent, setIntent] = useState(takeGoalsIntent);
  useEffect(() => {
    if (!goals || !intent) return;
    setIntent(null);
    if (!goals.anchor.started) {
      if (intent.view === 'start') setPanel({ name: 'start' });
    } else if (intent.view === 'whatif') {
      go({ name: 'projection' });
      setPanel({ name: 'whatif', monthly: intent.monthly });
    } else if (intent.view === 'anchor') {
      go({ name: 'anchor' });
    } else if (intent.view === 'projection') {
      // Projections' "See the projection" (THL-197 GR-33).
      go({ name: 'projection' });
    }
  }, [goals, intent]);                                      // eslint-disable-line react-hooks/exhaustive-deps

  // A change here can move Allowance, so the rest of the app reloads too.
  const changed = useCallback(async () => {
    await load();
    onChanged?.();
  }, [load, onChanged]);
  // Endpoints that change the Anchor answer with the whole page's data.
  const took = (result) => { if (result?.anchor) setGoals(result); };

  if (error) return <div className="pk gl-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!goals) return <div className="pk gl-page"><p className="pk-muted" role="status">Loading Save…</p></div>;

  const close = () => setPanel(null);
  const toWhatIf = () => { go({ name: 'projection' }); setPanel({ name: 'whatif' }); };
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
      <Overview goals={goals} learn={learn} onTab={onTab}
                onStart={() => setPanel({ name: 'start' })}
                onAnchor={() => go({ name: 'anchor' })}
                onProjection={() => go({ name: 'projection' })}
                onWhatIf={toWhatIf}
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
      {panel?.name === 'explain' && (
        <TargetExplained goals={goals} onClose={close} onWhatIf={toWhatIf} />
      )}
      {panel?.name === 'accounts' && (
        <AnchorAccounts goals={goals} onClose={close} onDone={took} />
      )}
      {panel?.name === 'how' && (
        <HowWorkedOut goals={goals} onClose={close}
                      onWhatIf={() => setPanel({ name: 'whatif' })}
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

/** SV-P01 and SV-P03: the Anchor on top, chests, then what it could grow into. */
export function Overview({ goals, learn, onTab, onStart, onAnchor, onProjection, onWhatIf, onNewChest, onChest }) {
  return (
    <>
      <header className="gl-head">
        <p className="pk-overline accent">{monthYear(goals.month)}</p>
        <h1 className="pk-h1">Save</h1>
      </header>
      <AnchorCard goals={goals} onStart={onStart} onOpen={onAnchor} onTab={onTab} />
      <ChestsSection goals={goals} onNew={onNewChest} onOpen={onChest}
                     onTreasure={onChest} />
      <GrowInto goals={goals} learn={learn} onTab={onTab} onProjection={onProjection} onWhatIf={onWhatIf} />
    </>
  );
}

export const RATES_NOTE = 'Illustrative rates of 3%, 5% and 7% a year, added monthly, before fees and taxes. Not a prediction or advice. Real returns go up and down and can be negative.';

/** The calculator card's words at its starting figures: "$13,970 – $17,310". */
export function calculatorWords(start = CALC_START) {
  const monthly = Number(start.monthly);
  const years = Number(start.years);
  const r = calculator(monthly, years);
  const values = r.rows.map((x) => x.value);
  return {
    figure: `${dollarsWords(Math.min(...values))} – ${dollarsWords(Math.max(...values))}`,
    line: `${dollarsWords(monthly)} a month for ${years} years (${dollarsWords(r.putIn)} put in), at illustrative 3% to 7% a year.`,
  };
}

/** The Learn card's words: "2 of 5 read" and what's next. */
export function learnWords(learn) {
  if (!learn) return { figure: 'Five short reads', line: 'The basics of investing, at your pace.', link: 'Start learning' };
  const done = new Set((learn.modules ?? []).filter((s) => s.done).map((s) => s.id));
  const read = learn.read ?? 0;
  const of = learn.of ?? 5;
  const next = read >= of ? null
    : MODULES.find((m) => m.id === learn.next) ?? MODULES.find((m) => !done.has(m.id));
  if (!next) return { figure: `${read} of ${of} read`, line: 'You’ve read them all.', link: 'Read again' };
  return {
    figure: `${read} of ${of} read`,
    line: `${read > 0 ? 'Next' : 'Start with'}: ${next.title} · ${next.minutes} min`,
    link: read > 0 ? 'Keep learning' : 'Start learning',
  };
}

/** The projection card's words: the range, and how the Anchor grows. */
export function projectionWords(a) {
  const p = a.projection;
  const pace = a.pace?.usual;
  const chests = a.chests_monthly > 0 ? ', less what your chests take' : '';
  if (p?.state === 'full') {
    return { figure: 'You’re there', line: 'Your Anchor covers 3 months of your usual Essentials.',
             link: 'See your Anchor', to: 'anchor' };
  }
  if (p?.state === 'range') {
    return {
      figure: rangeShort(p.from, p.to).replace('–', ' – '),
      line: pace > 0 ? `Growing about ${amount(Math.round(pace))} a month: what you put away${chests}.`
        : 'From your best and quietest months.',
      link: 'Try putting away more', to: 'whatif',
    };
  }
  return { figure: 'No date yet', line: 'Nothing put away lately. As soon as you save a little, we’ll show a range.',
           link: 'See why', to: 'projection' };
}

/** "What this could grow into": three cards, then the footnote. */
export function GrowInto({ goals, learn, onTab, onProjection, onWhatIf, onAnchor }) {
  const a = goals.anchor;
  const calc = calculatorWords();
  const read = learnWords(learn);
  const proj = a.started ? projectionWords(a) : null;
  const projGo = { whatif: onWhatIf, anchor: onAnchor ?? onProjection, projection: onProjection };
  const openCalculator = () => { writeProjectionsUrl('calculator'); onTab?.('projections'); };
  return (
    <section className="gl-section" aria-labelledby="grow-title">
      <div className="gl-stack tight">
        <h2 className="pk-h2" id="grow-title">What this could grow into</h2>
        <p className="pk-label pk-muted">Illustrative, to help you plan. Pearl never recommends a product.</p>
      </div>
      <div className={`gl-chests gl-grow-cards${proj ? '' : ' two'}`}>
        {proj && (
          <article className="gl-card gl-grow-card">
            <p className="pk-overline">When your Anchor reaches 3 months</p>
            <p className="pk-h2">{proj.figure}</p>
            <p className="gl-text pk-muted">{proj.line}</p>
            <More onClick={projGo[proj.to]}>{proj.link}</More>
          </article>
        )}
        <article className="gl-card gl-grow-card">
          <p className="pk-overline">What regular investing could grow to</p>
          <p className="pk-h2">{calc.figure}</p>
          <p className="gl-text pk-muted">{calc.line}</p>
          <More onClick={openCalculator}>Open the calculator</More>
        </article>
        <article className="gl-card gl-grow-card">
          <p className="pk-overline">Learn at your pace</p>
          <p className="pk-h2">{read.figure}</p>
          <p className="gl-text pk-muted">{read.line}</p>
          <More onClick={() => onTab?.('learn')}>{read.link}</More>
        </article>
      </div>
      <p className="pk-label pk-muted">{RATES_NOTE}</p>
    </section>
  );
}
