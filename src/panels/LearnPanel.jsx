import { useCallback, useEffect, useRef, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getLearn, saveLearn } from '../api.js';
import { Choice, PButton, StatusPill } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { onLearnUrl, readLearnUrl, writeLearnUrl, writeProjectionsUrl } from '../router.js';
import { More } from './InsightsParts.jsx';
import { DISCLAIMER, MODULES, SAFE_TO_SPEND, moduleById } from './learnModules.js';
import './home.css';
import './insights.css';
import './growth.css';

/**
 * Save › Learn (Pearl THL-134, at /save/learn; moved from Growth by
 * THL-248). Open to everyone from day one; nothing here is locked behind a
 * milestone.
 *
 * GR-11 /save/learn              Before you invest: five modules with how far
 *                                she's read, and two explainers.
 * GR-12 /save/learn/<module>     A module: back to Learn, four-segment
 *                                progress, one idea per screen, Back / Next.
 * GR-13                          Its last screen, a quick check: one question,
 *                                no score, no timer. Any answer shows the
 *                                explanation, calm either way.
 * GR-14                          Done: what she now knows, the checklist tick
 *                                it earned, and the next module. "Back to Ready
 *                                to invest" only when she came from it
 *                                (?from=ready).
 *
 * Her place is saved per screen on her account (`/api/learn`). The words are
 * in learnModules.js, a draft for securities counsel.
 */

export default function LearnPanel({ onTab, version }) {
  const [route, setRoute] = useState(() => readLearnUrl() ?? { module: '', from: '' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => onLearnUrl(() => {
    const next = readLearnUrl();
    if (next) setRoute(next);
  }), []);
  const load = useCallback(() => {
    setError(null);
    return getLearn().then(setData).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  const nav = {
    onTab,
    open: (module, from = route.from) => { writeLearnUrl({ module, from }); window.scrollTo?.({ top: 0 }); },
    list: () => { writeLearnUrl({}); window.scrollTo?.({ top: 0 }); },
    ready: () => { writeProjectionsUrl('ready'); onTab?.('projections'); },
    save: async (id, body) => { const d = await saveLearn(id, body); setData(d); return d; },
  };

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading Learn…</p></div>;
  if (route.module === SAFE_TO_SPEND.id) return <Explainer onBack={nav.list} onHome={() => onTab?.('home')} />;
  const module = moduleById(route.module);
  if (module) {
    return <ModulePage key={module.id} module={module} data={data} from={route.from} nav={nav} />;
  }
  return <LearnPage data={data} nav={nav} />;
}

function BackLink({ onClick, children }) {
  return (
    <button type="button" className="in-back" onClick={onClick}>
      <PIcon name="chevronRight" size={12} className="in-flip" /> {children}
    </button>
  );
}

const stateOf = (data, id) => data.modules.find((m) => m.id === id) ?? { screen: 0, done: false };

/** "2 of 4" while she's part-way, "Read" once finished, or nothing. */
export function moduleStatus(m) {
  if (m.done) return 'read';
  if (m.screen > 0) return 'reading';
  return 'new';
}

/** GR-11 Learn. */
export function LearnPage({ data, nav }) {
  return (
    <div className="pk hm-page in-page lr-page">
      <div className="in-back-row"><BackLink onClick={() => nav.onTab?.('goals')}>Save</BackLink></div>
      <header className="hm-head">
        <p className="pk-overline accent">Learn at your pace</p>
        <h1 className="pk-h1">Learn</h1>
      </header>
      <section className="hm-card in-card" aria-labelledby="lr-title">
        <div className="in-card-head">
          <h2 className="pk-h2" id="lr-title">Before you invest</h2>
          <span className="pk-label pk-muted">{`${data.read} of ${data.of} read`}</span>
        </div>
        <ul className="lr-modules">
          {MODULES.map((m) => {
            const s = stateOf(data, m.id);
            const status = moduleStatus(s);
            return (
              <li key={m.id}>
                <button type="button" className="lr-module" onClick={() => nav.open(m.id, '')}>
                  <span className={`lr-badge${status === 'read' ? ' done' : ''}`} aria-hidden="true">
                    {status === 'read' ? <PIcon name="check" size={20} /> : `${m.minutes} min`}
                  </span>
                  <span className="lr-module-text">
                    <span className="pk-h3">{m.title}</span>
                    <span className="pk-label pk-muted">{m.sub}</span>
                  </span>
                  {status === 'read' && <StatusPill icon="check" tone="positive">Read</StatusPill>}
                  {status === 'reading' && (
                    <StatusPill icon="info" tone="info">{`${Math.min(s.screen, s.screens)} of ${s.screens}`}</StatusPill>
                  )}
                  {status === 'new' && <span className="in-more">Start<span aria-hidden="true">  ›</span></span>}
                  {status !== 'new' && <span className="pk-sr">{`, ${m.minutes} minutes`}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
      <div className="lr-explainers">
        <section className="hm-card lr-explainer" aria-labelledby="lr-sts">
          <p className="pk-overline">Explainer</p>
          <h2 className="pk-h3" id="lr-sts">{SAFE_TO_SPEND.title}</h2>
          <More onClick={() => nav.open(SAFE_TO_SPEND.id, '')} label={`Read ${SAFE_TO_SPEND.title}`}>Read</More>
        </section>
        <section className="hm-card lr-explainer" aria-labelledby="lr-protect">
          <p className="pk-overline">Explainer</p>
          <h2 className="pk-h3" id="lr-protect">How we protect you</h2>
          <More onClick={() => nav.onTab?.('protect')} label="Read How we protect you">Read</More>
        </section>
      </div>
      <p className="pk-label pk-muted">{DISCLAIMER}</p>
    </div>
  );
}

function Segments({ of, upto }) {
  return (
    <div className="lr-progress" role="progressbar" aria-label="Module progress" aria-valuemin={0}
         aria-valuemax={of} aria-valuenow={upto}>
      {Array.from({ length: of }, (_, i) => <span key={i} className={i < upto ? 'on' : ''} />)}
    </div>
  );
}

/** One screen's table: three columns at most, short phrases (GR-12). */
function ScreenTable({ table }) {
  return (
    <div className="hm-card lr-table-card">
      <table className="lr-table">
        <caption className="pk-sr">{table.caption}</caption>
        <thead>
          <tr><td />{table.cols.map((c) => <th key={c} scope="col">{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map(([head, ...cells]) => (
            <tr key={head}>
              <th scope="row">{head}</th>
              {cells.map((c, i) => <td key={i} data-col={table.cols[i]}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** GR-12, GR-13 and GR-14: one module. */
export function ModulePage({ module, data, from = '', nav, initial }) {
  const saved = stateOf(data, module.id);
  const total = module.screens.length + 1;
  // Pick up where she left off, unless she's reading it again.
  const [screen, setScreen] = useState(() => initial
    ?? (saved.done ? 1 : Math.min(Math.max(saved.screen, 1), total)));
  const [finished, setFinished] = useState(initial === 'done');
  const [answer, setAnswer] = useState(saved.answer ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus?.(); }, [screen, finished]);

  const go = async (n) => {
    setError('');
    setScreen(n);
    window.scrollTo?.({ top: 0 });
    if (n > saved.screen) nav.save(module.id, { screen: n }).catch(() => {});
  };
  const choose = async (key) => {
    setAnswer(key);
    setError('');
    nav.save(module.id, { answer: key }).catch((e) => setError(e.message));
  };
  const finish = async () => {
    if (!answer) { setError('Choose an answer to finish.'); return; }
    setBusy(true);
    try {
      await nav.save(module.id, { done: true });
      setFinished(true);
      window.scrollTo?.({ top: 0 });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (finished) return <ModuleDone module={module} data={data} from={from} nav={nav} heading={heading} />;
  const check = screen === total;
  const s = module.screens[screen - 1];
  return (
    <div className="pk hm-page in-page lr-page">
      <div className="in-back-row">
        <BackLink onClick={nav.list}>Learn</BackLink>
        <span className="pk-label pk-muted">{`${module.title} · ${screen} of ${total}`}</span>
      </div>
      <Segments of={total} upto={screen} />
      {check ? (
        <Check module={module} answer={answer} onChoose={choose} heading={heading} />
      ) : (
        <section className="lr-screen" aria-labelledby="lr-screen-title">
          <h1 className="pk-h1" id="lr-screen-title" tabIndex={-1} ref={heading}>{s.title}</h1>
          {s.body.map((p) => <p key={p} className="lr-body">{p}</p>)}
          {s.table && <ScreenTable table={s.table} />}
        </section>
      )}
      {error && <p className="pj-field-note" role="alert">{error}</p>}
      <div className="lr-nav">
        <PButton variant="secondary" onClick={() => (screen > 1 ? go(screen - 1) : nav.list())}>Back</PButton>
        {!check && <p className="pk-label pk-muted lr-disclaimer">{DISCLAIMER}</p>}
        {check ? (
          <PButton onClick={finish} disabled={busy}>{busy ? 'Saving…' : 'Finish'}</PButton>
        ) : (
          <PButton onClick={() => go(screen + 1)}>Next</PButton>
        )}
      </div>
    </div>
  );
}

/** GR-13 Check yourself. */
export function Check({ module, answer, onChoose, heading }) {
  const c = module.check;
  const right = answer === c.answer;
  return (
    <section className="lr-screen" aria-labelledby="lr-check-title">
      <h1 className="pk-h1" id="lr-check-title" tabIndex={-1} ref={heading}>Quick check</h1>
      <fieldset className="pj-fieldset lr-check">
        <legend className="lr-body">{c.question}</legend>
        <div className="pk-choices">
          {c.options.map((o) => (
            <Choice key={o.key} name={`lr-${module.id}`} checked={answer === o.key} label={o.label}
                    onChange={() => onChoose(o.key)} />
          ))}
        </div>
      </fieldset>
      {answer && (
        <div className="lr-explain" role="status">
          <p className="pk-overline accent">{right ? 'That’s it' : 'Close!'}</p>
          <p>{right ? c.right : (c.close?.[answer] ?? c.right)}</p>
        </div>
      )}
    </section>
  );
}

const halfway = (screen, of) => (screen <= 0 ? '' : screen * 2 === of ? ' · you’re halfway'
  : screen * 2 < of ? ' · you’ve started' : ' · nearly done');

/** GR-14 Module done. */
export function ModuleDone({ module, data, from, nav, heading }) {
  const next = MODULES.find((m) => m.id !== module.id && !stateOf(data, m.id).done);
  const ns = next ? stateOf(data, next.id) : null;
  return (
    <div className="pk hm-page in-page lr-page">
      <div className="in-back-row"><BackLink onClick={nav.list}>Learn</BackLink></div>
      <Segments of={module.screens.length + 1} upto={module.screens.length + 1} />
      <section className="hm-card lr-done" aria-labelledby="lr-done-title">
        <span className="lr-tick" aria-hidden="true"><PIcon name="check" size={28} /></span>
        <h1 className="pk-h1" id="lr-done-title" tabIndex={-1} ref={heading}>{`You finished ${module.title}`}</h1>
        <p className="lr-body pk-muted">{module.done}</p>
        <StatusPill icon="check" tone="positive">
          {`Ready to invest checklist · modules read ${data.read} of ${data.of}`}
        </StatusPill>
      </section>
      {next ? (
        <section className="hm-card lr-next" aria-labelledby="lr-next-title">
          <p className="pk-overline accent">Up next</p>
          <div className="lr-next-row">
            <div className="in-stack">
              <h2 className="pk-h2" id="lr-next-title">{next.title}</h2>
              <span className="pk-label pk-muted">{`${next.minutes} min${halfway(ns.screen, ns.screens ?? 4)}`}</span>
            </div>
            <PButton className="lr-hug" onClick={() => nav.open(next.id)}>Continue</PButton>
          </div>
        </section>
      ) : (
        <section className="hm-card lr-next" aria-labelledby="lr-next-title">
          <p className="pk-overline accent">All read</p>
          <h2 className="pk-h2" id="lr-next-title">You’ve read all five modules</h2>
          <More onClick={nav.list}>Back to Learn</More>
        </section>
      )}
      {from === 'ready' && <More onClick={nav.ready}>Back to Ready to invest</More>}
    </div>
  );
}

/** How safe-to-spend works (THL-46), the first explainer under the modules. */
export function Explainer({ onBack, onHome }) {
  return (
    <div className="pk hm-page in-page lr-page">
      <div className="in-back-row"><BackLink onClick={onBack}>Learn</BackLink></div>
      <section className="lr-screen" aria-labelledby="lr-explainer-title">
        <p className="pk-overline accent">Explainer</p>
        <h1 className="pk-h1" id="lr-explainer-title">{SAFE_TO_SPEND.title}</h1>
        {SAFE_TO_SPEND.body.map((p) => <p key={p} className="lr-body">{p}</p>)}
      </section>
      <More onClick={onHome}>See yours on Home</More>
    </div>
  );
}
