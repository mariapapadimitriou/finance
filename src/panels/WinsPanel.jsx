import { useCallback, useEffect, useRef, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  challengeToChest, getChallenge, getRecap, getWins, getWinsChallenges, money, startChallenge,
  stopChallenge,
} from '../api.js';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { MARKS } from '../pearl/ui.jsx';
import {
  onPathUrl, readPathUrl, setGoalsIntent, writeInsightsUrl, writePathUrl, writeProjectionsUrl,
} from '../router.js';
import { More } from './InsightsParts.jsx';
import { dayShort, monthName, monthYear } from './GoalsParts.jsx';
import StepScreen from './PathStep.jsx';
import './home.css';
import './insights.css';
import './growth.css';
import './wins.css';

/**
 * Wins (Pearl Handoff › Wins: THL-239 W-01 to W-04, THL-241 ST-01/02,
 * THL-242 CH-01 to CH-05, THL-243 RC-01/02; built as THL-246, THL-247,
 * THL-249, THL-250, THL-251), at /wins.
 *
 * In order: Your path (six milestones, the next one called out in her
 * numbers), Pearls earned (nine; unearned ones are dashed outlines that say
 * how to earn them), Streaks and the monthly recap side by side, Challenges
 * (in progress, then suggested from her spending), and a pointer to Save
 * when a milestone makes Learn or the calculator a good next read. No phase
 * names, nothing in rose, nothing taken away. The figures come from
 * `/api/wins` (finance/wins.py); the words are made there.
 *
 * A milestone opens its step's own screen (GR-02 to GR-04, PathStep.jsx) at
 * /wins/path/<step>.
 */

const STEP_FOR = { assessed: 'essentials', anchor_setup: 'setup', anchor_quarter: 'full',
                   anchor_half: 'full', anchor_full: 'full', invest: 'invest' };

/** A pearl: earned, next, to come, or a period Pearl couldn't tell. */
export function Pearl({ state = 'earned', size = '' }) {
  return <span className={`wn-pearl ${state}${size ? ` ${size}` : ''}`} aria-hidden="true" />;
}

export default function WinsPanel({ onTab, version }) {
  const [route, setRoute] = useState(() => readPathUrl() ?? { step: '' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [panel, setPanel] = useState(null);
  useEffect(() => onPathUrl(() => {
    const next = readPathUrl();
    if (next) setRoute(next);
  }), []);
  const load = useCallback(() => {
    setError(null);
    return getWins().then(setData).catch(setError);
  }, []);
  useEffect(() => { if (!route.step) load(); }, [load, version, route.step]);

  const open = (view) => { writeProjectionsUrl(view); onTab?.('projections'); };
  const show = (step) => { writePathUrl({ step }); window.scrollTo?.({ top: 0 }); };
  const toGoals = (view) => { setGoalsIntent({ view }); onTab?.('goals'); };
  const act = (action) => {
    if (!action) return;
    if (action === 'review') onTab?.('review');
    else if (action === 'invested') open('unveil');
    else if (action.startsWith('goals:')) toGoals(action.slice(6));
    else onTab?.(action);
  };
  const toSave = (to) => {
    if (to === 'calculator') open('calculator');
    else onTab?.(to === 'learn' ? 'learn' : 'goals');
  };

  if (route.step) {
    const nav = {
      onTab, back: () => show(''), toReady: () => open('ready'), toUnveil: () => open('unveil'),
      toGoals, toInsights: (month) => { writeInsightsUrl({ view: 'month', month }); onTab?.('insights'); },
    };
    return <StepScreen step={route.step} nav={nav} version={version} />;
  }
  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading your wins…</p></div>;

  const close = () => setPanel(null);
  const reload = async () => { await load(); };
  return (
    <>
      <WinsPage data={data} onAct={act} onStep={show} onSave={toSave}
                onStreak={(key) => setPanel({ name: 'streak', key })}
                onChallenges={() => setPanel({ name: 'challenges' })}
                onStart={(offer) => setPanel({ name: 'start', offer })}
                onChallenge={(id) => setPanel({ name: 'challenge', id })}
                onRecap={(month) => setPanel({ name: 'recap', month })} />
      {panel?.name === 'streak' && (
        <StreakPanel streak={data.streaks.find((s) => s.key === panel.key)} onClose={close} />
      )}
      {panel?.name === 'challenges' && (
        <ChallengesPanel onClose={close} onStart={(offer) => setPanel({ name: 'start', offer })} />
      )}
      {panel?.name === 'start' && (
        <StartChallengePanel offer={panel.offer} onClose={close}
                             onStarted={async (id) => { await reload(); setPanel({ name: 'challenge', id }); }} />
      )}
      {panel?.name === 'challenge' && (
        <ChallengePanel id={panel.id} onClose={close} onChanged={reload}
                        onOthers={() => setPanel({ name: 'challenges' })} />
      )}
      {panel?.name === 'recap' && (
        <RecapPanel month={panel.month} initial={data.recap?.month === panel.month ? data.recap : null}
                    onClose={close} onShare={() => setPanel({ name: 'share', month: panel.month })} />
      )}
      {panel?.name === 'share' && (
        <SharePanel month={panel.month} initial={data.recap?.month === panel.month ? data.recap : null}
                    onClose={close} onBack={() => setPanel({ name: 'recap', month: panel.month })} />
      )}
    </>
  );
}

/** W-01 to W-04. */
export function WinsPage({ data, onAct, onStep, onSave, onStreak, onChallenges, onStart, onChallenge, onRecap }) {
  const next = data.next;
  return (
    <div className="pk hm-page in-page wn-page">
      <header className="hm-head">
        <p className="pk-overline accent">{monthYear(data.month)}</p>
        <h1 className="pk-h1">Wins</h1>
      </header>

      <section className="hm-card" aria-labelledby="wn-path-title">
        <p className="pk-overline">Your path</p>
        <h2 className="pk-h2" id="wn-path-title">{data.heading}</h2>
        <ol className="wn-path" aria-label="Milestones on your path">
          {data.path.map((p) => (
            <li key={p.key} className={p.state} aria-current={p.state === 'next' ? 'step' : undefined}>
              <button type="button" className="wn-path-btn" onClick={() => onStep?.(STEP_FOR[p.key])}
                      aria-label={`${p.label}, ${p.state === 'earned' ? `earned ${p.when}` : p.when}`}>
                <Pearl state={p.state} />
                <span className="wn-label">{p.label}</span>
                <span className="wn-when">{p.when}</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="wn-next">
          <p className="pk-label">{next.title}</p>
          <p className="pk-h3">{next.line}</p>
          {next.label && <PButton onClick={() => onAct?.(next.action)}>{next.label}</PButton>}
        </div>
      </section>

      <section className="hm-card" aria-labelledby="wn-pearls-title">
        <div className="hm-row-between">
          <h2 className="pk-h2" id="wn-pearls-title">Pearls earned</h2>
          <span className="pk-label accent">{`${data.earned} of ${data.total}`}</span>
        </div>
        <ul className="wn-pearls" aria-label="Pearls">
          {data.pearls.map((p) => (
            <li key={p.key} className={`wn-pearl-card${p.earned ? '' : ' todo'}`}>
              <Pearl state={p.earned ? 'earned' : 'todo'} />
              <span className="wn-pearl-text">
                <span className="wn-title">{p.label}</span>
                <span className="wn-detail">
                  {p.earned ? `Earned ${dayShort(p.on)}${p.note ? ` · ${p.note}` : ''}` : p.how}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <div className="wn-grid">
        <section className="hm-card" aria-labelledby="wn-streaks-title">
          <div className="hm-row-between">
            <h2 className="pk-h2" id="wn-streaks-title">Streaks</h2>
            <More onClick={() => onStreak?.(data.streaks[0].key)}>See all</More>
          </div>
          <ul className="wn-streaks">
            {data.streaks.map((s) => (
              <li key={s.key}>
                <button type="button" className="wn-streak-btn" onClick={() => onStreak?.(s.key)}>
                  <span className="wn-streak-text">
                    <span className="wn-label">{s.label}</span>
                    <span className="wn-sub">{s.started ? `This run ${s.this_words}` : s.starts}</span>
                  </span>
                  {s.started && <span className="wn-streak-best">{s.best_words}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
        <RecapCard recap={data.recap} nextRecap={data.next_recap} onOpen={onRecap} />
      </div>

      <ChallengesCard challenges={data.challenges} onAll={onChallenges} onStart={onStart} onOpen={onChallenge} />

      {data.suggestion && (
        <div className="wn-pointer" role="note">
          <p>{data.suggestion.text}</p>
          <More onClick={() => onSave?.(data.suggestion.to)}>{data.suggestion.label}</More>
        </div>
      )}
    </div>
  );
}

/** The recap card on W-01 (or, for someone new, when the first one comes). */
export function RecapCard({ recap, nextRecap, onOpen }) {
  if (!recap) {
    return (
      <section className="hm-card" aria-labelledby="wn-recap-title">
        <p className="pk-overline">Monthly recap</p>
        <h2 className="pk-h2" id="wn-recap-title">{`Your first recap comes in ${nextRecap}`}</h2>
        <p className="pk-muted">At the start of each month, Pearl sums up what went well.</p>
      </section>
    );
  }
  const bits = recap.went_well.map((w, i) => {
    const t = w.text.replace(/\.$/, '');
    return i === 0 ? t : t.charAt(0).toLowerCase() + t.slice(1);
  });
  const line = bits.join(', ') + (recap.pearls.length ? ` and earned a pearl: ${recap.pearls[0].label}.` : '.');
  return (
    <section className="hm-card" aria-labelledby="wn-recap-title">
      <p className="pk-overline">{`${monthName(recap.month)} recap`}</p>
      <h2 className="pk-h2" id="wn-recap-title">{recap.title}</h2>
      <p className="pk-muted">{line.charAt(0).toUpperCase() + line.slice(1)}</p>
      <More onClick={() => onOpen?.(recap.month)}>See your recap</More>
    </section>
  );
}

/** Challenges on W-01: in progress, then three suggested from her spending. */
export function ChallengesCard({ challenges, onAll, onStart, onOpen }) {
  const { active, suggested, ready } = challenges;
  return (
    <section className="hm-card" aria-labelledby="wn-ch-title">
      <div className="hm-row-between">
        <h2 className="pk-h2" id="wn-ch-title">Challenges</h2>
        {ready && <More onClick={onAll}>See all</More>}
      </div>
      {!ready && (
        <p className="pk-muted">Once Pearl knows your usual spending, it suggests short challenges from it.
          Always optional.</p>
      )}
      {active.map((c) => (
        <button key={c.id} type="button" className="wn-active wn-streak-btn" onClick={() => onOpen?.(c.id)}>
          <span className="hm-row-between">
            <span className="wn-label">{c.title}</span>
            <span className="pk-label pk-muted">{c.words.days}</span>
          </span>
          <Bar progress={c.progress} tone={c.words.tone} label={c.title} />
          <span className="pk-label pk-muted">{c.words.line}</span>
        </button>
      ))}
      {ready && suggested.length > 0 && (
        <>
          <p className="pk-overline">Suggested from your spending</p>
          <div className="wn-suggested">
            {suggested.slice(0, 3).map((s) => (
              <article key={s.kind} className="wn-suggest">
                <span className="wn-label">{s.title}</span>
                <span className="wn-sub">{s.line}</span>
                <More onClick={() => onStart?.(s)}>Start</More>
              </article>
            ))}
          </div>
        </>
      )}
      {ready && suggested.length === 0 && active.length === 0 && (
        <p className="pk-muted">Nothing to suggest right now. Check back after a few more weeks.</p>
      )}
    </section>
  );
}

function Bar({ progress, tone, label }) {
  const pct = Math.round(Math.min(progress.share, 1) * 100);
  return (
    <span className={`wn-bar${tone === 'champagne' ? ' champagne' : ''}`} role="progressbar"
          aria-label={`${label}, ${money(progress.done, { cents: true })} of ${money(progress.target)}`}
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
      <span style={{ width: `${Math.max(pct, progress.done > 0 ? 3 : 0)}%` }} />
    </span>
  );
}

/** ST-01 and ST-02: one streak, its two figures and the last twelve periods. */
export function StreakPanel({ streak, onClose }) {
  if (!streak) return null;
  const s = streak;
  const letter = (p) => (s.unit === 'month' ? monthName(p.period).charAt(0)
    : String(Number(p.period.slice(8, 10))));
  return (
    <DetailPanel label={s.label} overline="Streak" onClose={onClose} className="on-card">
      <h1 className="pk-h1">{s.label}</h1>
      {s.new_best && s.started && (
        <div className="wn-note" role="status">
          <p className="wn-note-title">{`New best: ${s.this_words} in a row`}</p>
          {s.note && <p>{s.note}</p>}
        </div>
      )}
      <div className="wn-figures">
        <div className="wn-figure">
          <p className="pk-overline">This run</p>
          <p className="pk-h2">{s.started ? s.this_words : 'Not yet'}</p>
        </div>
        <div className="wn-figure">
          <p className="pk-overline">Best run</p>
          <p className="pk-h2">{s.started ? `${s.best} ${s.unit}${s.best === 1 ? '' : 's'}` : 'Not yet'}</p>
        </div>
      </div>
      {s.started ? (
        <div className="wn-periods" aria-label={`The last ${s.periods.length} ${s.unit}s`}>
          {s.periods.map((p) => (
            <span key={p.period} className="wn-period">
              <Pearl state={p.counted === true ? 'earned' : p.counted === false ? 'todo' : 'unknown'} size="sm" />
              {letter(p)}
              <span className="pk-sr">{p.counted === true ? 'counted' : p.counted === false ? 'didn’t count' : 'unknown'}</span>
            </span>
          ))}
        </div>
      ) : <p className="pk-muted">{s.starts}.</p>}
      {s.note && !s.new_best && <div className="wn-note"><p>{s.note}</p></div>}
      <p className="pk-muted">{s.rule}</p>
      <div className="gl-panel-foot">
        <PButton onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

/** CH-01: the challenges Pearl can price from her spending. */
export function ChallengesPanel({ onClose, onStart }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { getWinsChallenges().then(setData).catch(setError); }, []);
  return (
    <DetailPanel label="Try a challenge" overline="Challenges" onClose={onClose} className="on-card">
      <h1 className="pk-h1">Try a challenge</h1>
      <p className="gl-body">Short and optional, built from your own spending. Stop any time; nobody else
        sees them.</p>
      {error && <ErrorNote error={error} />}
      {data && data.suggested.length === 0 && (
        <p className="pk-muted">Nothing to suggest right now. Once Pearl knows your usual spending, it
          suggests short challenges from it.</p>
      )}
      <div className="wn-list">
        {(data?.suggested ?? []).map((s) => (
          <div key={s.kind} className="wn-row">
            <span className="wn-streak-text">
              <span className="wn-label">{s.title}</span>
              <span className="wn-sub">{s.line}</span>
            </span>
            <More onClick={() => onStart?.(s)}>Start</More>
          </div>
        ))}
      </div>
      <div className="gl-panel-foot">
        <PButton onClick={onClose}>Close</PButton>
      </div>
    </DetailPanel>
  );
}

const parseAmount = (text) => {
  const n = Number(String(text ?? '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(n) ? n : NaN;
};

/** CH-02: one challenge, with her target. */
export function StartChallengePanel({ offer, onClose, onStarted }) {
  const [target, setTarget] = useState(() => (offer.target != null ? money(offer.target) : ''));
  const [merchant, setMerchant] = useState(offer.options?.[0]?.merchant ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const value = parseAmount(target);
  const fixed = offer.kind === 'no_spend_weekend' || offer.kind === 'subscription_sweep';
  const lastMonth = monthName(prevMonth(offer.start.slice(0, 7)));
  const start = async () => {
    setBusy(true); setError('');
    try {
      const body = { kind: offer.kind };
      if (!fixed) body.target = value;
      if (offer.kind === 'subscription_sweep') body.merchant = merchant;
      const r = await startChallenge(body);
      onStarted?.(r.id);
    } catch (e) {
      setError(e.message); setBusy(false);
    }
  };
  return (
    <DetailPanel label={offer.title} overline="Challenge" onClose={onClose} className="on-card">
      <h1 className="pk-h1">{offer.title}</h1>
      {offer.baseline != null && offer.kind !== 'subscription_sweep' && (
        <div className="wn-figures">
          <div className="wn-figure">
            <p className="pk-overline">{offer.kind === 'coffee' ? lastMonth : offer.kind === 'anchor_boost' ? 'Your usual pace' : 'Your usual'}</p>
            <p className="pk-h2">{money(Math.round(offer.baseline))}</p>
          </div>
          <div className="wn-figure">
            <p className="pk-overline">{offer.kind === 'anchor_boost' ? 'Put away in 30 days' : fixed ? 'This weekend' : 'Try this month'}</p>
            <p className="pk-h2">{money(offer.target)}</p>
          </div>
        </div>
      )}
      {!fixed && (
        <div className="gl-field">
          <label htmlFor="wn-target">Your target</label>
          <input id="wn-target" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
          <p className="gl-hint">
            {offer.kind === 'anchor_boost' ? 'Pearl suggests $100 more than your usual pace'
              : 'Pearl suggests about 30% less than your usual'}
          </p>
        </div>
      )}
      {offer.kind === 'subscription_sweep' && (
        <div className="pk-choices" role="radiogroup" aria-label="Which subscription">
          {(offer.options ?? []).map((o) => (
            <Choice key={o.merchant} name="wn-sub" checked={merchant === o.merchant}
                    onChange={() => setMerchant(o.merchant)} label={o.merchant}
                    description={`${money(o.monthly, { cents: true })} a month`} />
          ))}
        </div>
      )}
      <div className="wn-note">
        <p className="wn-note-title">What counts</p>
        <p>{offer.counts}</p>
      </div>
      <p className="pk-muted">You can stop any time. Ending short is fine.</p>
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        <PButton disabled={busy || (!fixed && !(value >= 0)) || (offer.kind === 'subscription_sweep' && !merchant)}
                 onClick={start}>{busy ? 'Starting…' : 'Start the challenge'}</PButton>
        <PButton variant="secondary" onClick={onClose}>Not now</PButton>
      </div>
    </DetailPanel>
  );
}

function prevMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`;
}

/** CH-03 in progress, CH-04 finished (with the chest offer), CH-05 stopped. */
export function ChallengePanel({ id, onClose, onChanged, onOthers }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const [chest, setChest] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const load = useCallback(() => getChallenge(id).then((x) => {
    setD(x);
    if (x.chests?.length && chest == null) setChest(x.chests[0].id);
  }).catch(setError), [id]);                              // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  if (error) return <DetailPanel label="Challenge" overline="Challenge" onClose={onClose} className="on-card"><ErrorNote error={error} onRetry={load} /></DetailPanel>;
  if (!d) return <DetailPanel label="Challenge" overline="Challenge" onClose={onClose} className="on-card"><p className="pk-muted" role="status">Loading…</p></DetailPanel>;
  const { challenge: c, progress: p, words: w } = d;
  const boost = c.kind === 'anchor_boost';
  const result = c.result ?? {};
  const stop = async () => {
    setBusy(true);
    try { await stopChallenge(id); await onChanged?.(); await load(); }
    catch (e) { setNote(e.message); }
    finally { setBusy(false); }
  };
  const move = async () => {
    setBusy(true); setNote('');
    try {
      const r = await challengeToChest(id, chest);
      setNote(`Added ${money(r.added, { cents: true })} to ${r.chest}. Move the money from chequing to your savings when you’re ready.`);
      await onChanged?.(); await load();
    } catch (e) { setNote(e.message); }
    finally { setBusy(false); }
  };
  if (c.status === 'active') {
    return (
      <DetailPanel label={c.title} overline="Challenge" onClose={onClose} className="on-card">
        <h1 className="pk-h1">{c.title}</h1>
        <div className="wn-figures">
          <div className="wn-figure">
            <p className="pk-overline">{boost ? 'Put away so far' : 'Spent so far'}</p>
            <p className="pk-h2">{money(p.done, { cents: p.done % 1 !== 0 })}</p>
          </div>
          <div className="wn-figure">
            <p className="pk-overline">Days left</p>
            <p className="pk-h2">{p.days_left}</p>
          </div>
        </div>
        <Bar progress={p} tone={w.tone} label={c.title} />
        <p className="pk-muted">{w.line}</p>
        {d.recent.length > 0 && (
          <>
            <p className="pk-overline">Recent</p>
            <ul className="wn-recent">
              {d.recent.map((r) => (
                <li key={r.id}><span>{r.merchant}</span>
                  <span className="wn-amount">{boost ? '+' : '-'}{money(r.amount, { cents: true })}</span></li>
              ))}
            </ul>
          </>
        )}
        {note && <p className="txd-hint" role="alert">{note}</p>}
        <div className="gl-panel-foot">
          <PButton onClick={onClose}>Done</PButton>
          <PButton variant="secondary" disabled={busy} onClick={stop}>Stop the challenge</PButton>
        </div>
      </DetailPanel>
    );
  }
  if (c.status === 'stopped') {
    return (
      <DetailPanel label="Challenge stopped" overline="Challenge" onClose={onClose} className="on-card">
        <h1 className="pk-h1">Challenge stopped</h1>
        <p className="gl-body">{w.line}</p>
        <div className="gl-panel-foot">
          <PButton onClick={onClose}>Back to Wins</PButton>
          <PButton variant="secondary" onClick={onOthers}>See other challenges</PButton>
        </div>
      </DetailPanel>
    );
  }
  const saved = w.saved ?? 0;
  const offer = saved > 0 && !result.moved_to;
  return (
    <DetailPanel label={w.title} overline="Challenge done" onClose={onClose} className="on-card">
      <h1 className="pk-h1">{w.title}</h1>
      <p className="gl-body">{w.line}</p>
      {result.moved_to && <Alert tone="positive">{`${money(saved, { cents: true })} went to ${result.moved_name}.`}</Alert>}
      {offer && d.chests.length > 0 && (
        <>
          <p className="pk-label">{`Put the ${money(saved, { cents: saved % 1 !== 0 })} in a treasure chest?`}</p>
          <div className="pk-choices" role="radiogroup" aria-label="Which chest">
            {d.chests.map((ch) => (
              <Choice key={ch.id} name="wn-chest" checked={chest === ch.id} onChange={() => setChest(ch.id)}
                      label={ch.name} description={`${money(ch.held)} of ${money(ch.target)}`} />
            ))}
            <Choice name="wn-chest" checked={chest === 'none'} onChange={() => setChest('none')} label="Not now" />
          </div>
          <p className="pk-muted">
            {`Move ${money(saved, { cents: saved % 1 !== 0 })} from chequing to your savings, and Pearl adds it to the chest.`}
          </p>
        </>
      )}
      {offer && d.chests.length === 0 && (
        <p className="pk-muted">Start a treasure chest on Save and Pearl can put what you saved in it.</p>
      )}
      {note && <p className="txd-hint" role="status">{note}</p>}
      <div className="gl-panel-foot">
        {offer && d.chests.length > 0 && chest !== 'none' ? (
          <PButton disabled={busy} onClick={move}>
            {`Add ${money(saved, { cents: saved % 1 !== 0 })} to ${d.chests.find((x) => x.id === chest)?.name ?? 'the chest'}`}
          </PButton>
        ) : <PButton onClick={onClose}>Done</PButton>}
        {offer && d.chests.length > 0 && chest !== 'none' && (
          <PButton variant="secondary" onClick={onClose}>Not now</PButton>
        )}
      </div>
    </DetailPanel>
  );
}

/** RC-01: last month, leading with what went well. */
export function RecapPanel({ month, initial = null, onClose, onShare }) {
  const [r, setR] = useState(initial);
  const [error, setError] = useState(null);
  useEffect(() => { if (!initial) getRecap(month).then(setR).catch(setError); }, [month, initial]);
  if (error) return <DetailPanel label="Recap" overline="Recap" onClose={onClose} className="on-card"><ErrorNote error={error} /></DetailPanel>;
  if (!r) return <DetailPanel label="Recap" overline="Recap" onClose={onClose} className="on-card"><p className="pk-muted" role="status">Loading…</p></DetailPanel>;
  return (
    <DetailPanel label={r.title} overline={`${monthName(r.month)} recap`} onClose={onClose} className="on-card">
      <h1 className="pk-h1">{r.title}</h1>
      <p className="pk-overline">What went well</p>
      <ul className="wn-well">
        {r.went_well.map((w) => <li key={w.key}><Pearl state="earned" />{w.text}</li>)}
      </ul>
      {r.pearls.length > 0 && (
        <>
          <p className="pk-overline">{r.pearls.length === 1 ? 'Pearl earned' : 'Pearls earned'}</p>
          <ul className="wn-well">
            {r.pearls.map((p) => <li key={p.key}><Pearl state="earned" size="lg" />{`${p.label} · ${dayShort(p.on)}`}</li>)}
          </ul>
        </>
      )}
      {r.streaks && (
        <>
          <p className="pk-overline">Streaks</p>
          <p className="gl-body">{r.streaks}</p>
        </>
      )}
      {r.opportunity && (
        <div className="wn-note">
          <p className="wn-note-title">Next month’s opportunity</p>
          <p>{r.opportunity.text}</p>
        </div>
      )}
      <div className="gl-panel-foot">
        <PButton onClick={onShare}>Share my month</PButton>
        <PButton variant="secondary" onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

/** The share image's lines: wins as words; amounts only when she asks. */
export function shareLines(r, amounts = false) {
  return r.went_well.map((w) => (amounts && w.amount != null ? `${w.share} · ${money(w.amount)}` : w.share));
}

/** RC-02: the share image, amounts off by default. */
export function SharePanel({ month, initial = null, onClose, onBack }) {
  const [r, setR] = useState(initial);
  const [amounts, setAmounts] = useState(false);
  const [note, setNote] = useState('');
  const card = useRef(null);
  useEffect(() => { if (!initial) getRecap(month).then(setR).catch(() => {}); }, [month, initial]);
  if (!r) return <DetailPanel label="Share" overline="Share" onClose={onClose} className="on-card"><p className="pk-muted" role="status">Loading…</p></DetailPanel>;
  const lines = shareLines(r, amounts);
  const save = async () => {
    try {
      const png = await imageOf(r, lines);
      const a = document.createElement('a');
      a.href = png; a.download = `pearl-${r.month}.png`; a.click();
      setNote('Saved to your downloads.');
    } catch { setNote('Couldn’t make the image here. Try a screenshot of the card.'); }
  };
  return (
    <DetailPanel label="Share your month" overline="Share" onClose={onClose} className="on-card"
                 back={onBack ? { label: 'Recap', onClick: onBack } : undefined}>
      <h1 className="pk-h1">Share your month</h1>
      <div className="wn-share-card" ref={card} aria-label="Share image preview">
        <span className="wn-logo"><img src={MARKS.pearl} alt="" width="40" height="33" /> pearl</span>
        <Pearl state="earned" />
        <p className="pk-h2">{`My ${monthName(r.month)}`}</p>
        {lines.map((l) => <p key={l} className="wn-line">{l}</p>)}
      </div>
      <Choice type="checkbox" checked={amounts} onChange={setAmounts} label="Show amounts" />
      <p className="pk-muted">Amounts are off by default. Nothing else about your accounts is included.</p>
      {note && <p className="pk-label" role="status">{note}</p>}
      <div className="gl-panel-foot">
        <PButton onClick={save}>Save image</PButton>
        <PButton variant="secondary" onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

/** A 1080×1350 PNG of the share card, drawn on a canvas. */
async function imageOf(r, lines) {
  const W = 1080, H = 1350;
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fdf8f6'; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#1d1b2e'; ctx.textAlign = 'center';
  ctx.font = '600 72px Georgia, serif'; ctx.fillText('pearl', W / 2, 420);
  ctx.strokeStyle = '#b12a5b'; ctx.lineWidth = 6;
  ctx.fillStyle = '#e9ddf6'; ctx.beginPath(); ctx.arc(W / 2, 560, 70, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.arc(W / 2, 560, 30, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#1d1b2e'; ctx.font = '600 64px Georgia, serif';
  ctx.fillText(`My ${monthName(r.month)}`, W / 2, 720);
  ctx.font = '400 34px system-ui, sans-serif';
  lines.forEach((l, i) => ctx.fillText(l, W / 2, 800 + i * 56));
  return canvas.toDataURL('image/png');
}

export { STEP_FOR };
