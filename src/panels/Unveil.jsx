import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getUnveil, money, reportInvesting } from '../api.js';
import { Choice, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Mark } from './GoalsParts.jsx';
import { monthFull } from './insightsMath.js';

/**
 * Unveil: the readiness checklist and the self-report (Pearl THL-135 GR-16,
 * THL-195 GR-37, THL-130 GR-10). Reached from the Path (GR-01): its "Ready to
 * invest" card opens GR-16, and its Unveil card opens GR-37.
 *
 * GR-16 /growth/ready        Ready to invest: a checklist to help her decide,
 *                            guidance and not a gate, and "Opened an investing
 *                            account?" with "I've opened one" → GR-37.
 * GR-37 /growth/unveil       Opened an investing account? Asks the kind of
 *                            account only — never where, a login or a balance.
 *                            "Mark Unveil done" makes the path's Unveil step
 *                            done and leads to GR-10.
 * GR-10 /growth/unveil/done  Unveil done: the three phases, and the path.
 *
 * "Read the basics" waits on Learn, which isn't built: it shows as not done,
 * with no link, and says so.
 */

export default function UnveilScreens({ view, nav, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getUnveil().then(setData).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading…</p></div>;
  if (view === 'unveil') {
    return (
      <ReportPage data={data} onBack={() => nav.show('ready')}
                  onDone={async (type) => {
                    setData(await reportInvesting(type));
                    nav.onChanged?.();
                    nav.show('done');
                  }} />
    );
  }
  if (view === 'done') return <UnveilDone data={data} onPath={() => nav.onTab?.('path')} />;
  return <ReadyPage data={data} nav={nav} />;
}

function BackLink({ onClick, children }) {
  return (
    <button type="button" className="in-back" onClick={onClick}>
      <PIcon name="chevronRight" size={12} className="in-flip" /> {children}
    </button>
  );
}

function Link({ onClick, children, label }) {
  return (
    <button type="button" className="in-more" onClick={onClick} aria-label={label}>
      {children}<span aria-hidden="true">  ›</span>
    </button>
  );
}

/** Each checklist row's words and link, from the server's state. */
export function checklistRows(checklist, nav) {
  return checklist.map((c) => {
    if (c.key === 'protect') {
      return { ...c, title: c.done ? 'Protect is done' : 'Finish Protect',
               detail: c.done ? 'Your income covers your Essentials' : 'Income, bills and Essentials covered',
               link: c.done ? null : { text: 'See your path', go: () => nav.onTab?.('path') } };
    }
    if (c.key === 'anchor') {
      const of = `${money(c.counted / 100)} of ${money(c.target / 100)}`;
      return { ...c, title: c.done ? 'Your Anchor is full' : 'Your Anchor is under way',
               detail: !c.started ? 'Not started yet' : c.counted > 0 ? of : `Nothing in it yet, of ${money(c.target / 100)}`,
               link: c.done ? null : c.started
                 ? { text: 'See Anchor', go: () => nav.toGoals('anchor') }
                 : { text: 'Start your Anchor', go: () => nav.toGoals('start') } };
    }
    if (c.key === 'cards') {
      const months = c.months === 1 ? 'last month' : `the last ${c.months} months`;
      return { ...c, title: 'No card balance growing',
               detail: c.cards === 0 ? 'No credit card to check'
                 : c.done ? (c.months ? `Checked over ${months}` : 'Checked as each month ends')
                   : `A card balance grew in ${monthFull(c.grew_in)}`,
               link: null };
    }
    return { ...c, title: 'Read the basics', detail: 'Coming soon, with Learn', link: null };
  });
}

/** GR-16 Ready to invest. */
export function ReadyPage({ data, nav }) {
  const rows = checklistRows(data.checklist, nav);
  const report = data.report;
  return (
    <div className="pk hm-page in-page pj-page">
      <header className="in-detail-head">
        <div className="in-back-row"><BackLink onClick={() => nav.onTab?.('path')}>Path</BackLink></div>
        <div className="pj-title-row">
          <div className="hm-head">
            <p className="pk-overline accent">Unveil</p>
            <h1 className="pk-h1">Ready to invest</h1>
          </div>
          <Mark phase="unveil" width={58} />
        </div>
        <p className="pk-muted">A checklist to help you decide. It’s guidance, not a gate: you can go
          ahead whenever you like.</p>
      </header>
      <div className="pj-ready">
        <section className="hm-card in-card" aria-labelledby="pj-check-title">
          <h2 className="pk-h2" id="pj-check-title">Your checklist</h2>
          <ul className="pj-checklist">
            {rows.map((r) => (
              <li key={r.key}>
                <span className={`pj-check${r.done ? ' done' : ''}`} aria-hidden="true">
                  {r.done && <PIcon name="check" size={14} />}
                </span>
                <span className="hm-row-text">
                  <span>{r.title}<span className="pk-sr">{r.done ? ', done' : ', not yet'}</span></span>
                  <span className="hm-row-detail">{r.detail}</span>
                </span>
                {r.link && <Link onClick={r.link.go}>{r.link.text}</Link>}
              </li>
            ))}
          </ul>
          <div className="pj-why">
            <p className="pk-overline">Why both matter</p>
            <p className="pk-label pk-muted">Investments go up and down. An Anchor means a surprise bill
              never forces you to sell at a bad time. Many people build both at once.</p>
          </div>
        </section>
        <section className="hm-card in-card" aria-labelledby="pj-opened-title">
          <p className="pk-overline accent">When you’re ready</p>
          <h2 className="pk-h2" id="pj-opened-title">Opened an investing account?</h2>
          {report ? (
            <>
              <p className="pk-label pk-muted">{`You told Pearl you opened ${article(report.label)}, so Unveil is done.`}</p>
              <Link onClick={() => nav.show('unveil')}>Change the kind of account</Link>
            </>
          ) : (
            <>
              <p className="pk-label pk-muted">Open one wherever you like. Tell Pearl when you have, and
                Unveil is done.</p>
              <PButton onClick={() => nav.show('unveil')}>I’ve opened one</PButton>
            </>
          )}
          <Link onClick={() => nav.show('calculator')}>Try the growth calculator</Link>
        </section>
      </div>
    </div>
  );
}

// "a TFSA", "an RRSP", "an FHSA": said as letters.
const article = (label) => (label === 'Not sure' ? 'an investing account'
  : label === 'Non-registered' ? 'a non-registered account'
    : `${label === 'TFSA' ? 'a' : 'an'} ${label}`);

/** GR-37 Opened an investing account? */
export function ReportPage({ data, onBack, onDone }) {
  const [type, setType] = useState(data.report?.type ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    if (!type) { setError('Choose the kind of account.'); return; }
    setBusy(true); setError('');
    try { await onDone(type); }
    catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <form className="pk hm-page in-page pj-page" onSubmit={submit}>
      <header className="in-detail-head">
        <div className="in-back-row"><BackLink onClick={onBack}>Ready to invest</BackLink></div>
        <div className="hm-head">
          <p className="pk-overline accent">Unveil</p>
          <h1 className="pk-h1">Opened an investing account?</h1>
        </div>
      </header>
      <section className="hm-card in-card">
        <p className="pj-body">Wherever you opened it, tell Pearl and Unveil is done. We don’t ask
          where, and we never ask for a login or a balance.</p>
        <fieldset className="pj-fieldset">
          <legend className="pk-overline accent">What kind of account?</legend>
          <div className="pk-choices">
            {data.types.map((t) => (
              <Choice key={t.key} name="pj-account-type" checked={type === t.key} label={t.label}
                      onChange={() => { setType(t.key); setError(''); }} />
            ))}
          </div>
        </fieldset>
        {error && <p className="pj-field-note" role="alert">{error}</p>}
        <p className="pk-label pk-muted">You can undo this in Profile.</p>
      </section>
      <div className="in-actions">
        <PButton type="submit" disabled={busy}>{busy ? 'Saving…' : 'Mark Unveil done'}</PButton>
        <button type="button" className="in-text-btn" onClick={onBack}>Not yet</button>
      </div>
    </form>
  );
}

/** GR-10 Unveil done. */
export function UnveilDone({ data, onPath }) {
  const phases = data.path?.phases ?? [];
  const everything = phases.length > 0 && phases.every((p) => p.state === 'done'
    || (p.key === 'unveil' && data.report));
  return (
    <div className="pk hm-page pj-done">
      <div className="pj-done-mark" aria-hidden="true"><Mark phase="unveil" width={96} /></div>
      <p className="pk-overline accent">Unveil · Done</p>
      <h1 className="pk-h1">You opened your first investment account</h1>
      <p className="pk-muted">
        {everything ? 'Protect, Build and Unveil: all three done. What you’ve built stays yours.'
          : 'Unveil is done. What you’ve built stays yours, and the rest of your path is still there.'}
      </p>
      <ol className="pj-done-phases" aria-label="Your path">
        {phases.map((p) => {
          const done = p.state === 'done' || (p.key === 'unveil' && !!data.report);
          return (
            <li key={p.key}>
              <Mark phase={p.key} width={64} />
              <span className="pk-h3">{p.label}</span>
              <span className="pk-label pk-muted">{done ? 'Done ✓' : p.state === 'now' ? 'Now' : 'Ahead'}</span>
            </li>
          );
        })}
      </ol>
      <PButton onClick={onPath}>See your path</PButton>
    </div>
  );
}
