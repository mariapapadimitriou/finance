import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  getUnveil, goToPartner, money, partnerNotify, partnerNotYet, reportInvesting,
} from '../api.js';
import { Choice, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { fromPartner } from '../router.js';
import { Mark } from './GoalsParts.jsx';
import { monthFull } from './insightsMath.js';
import { MomentLayout } from './Moments.jsx';
import { BeforeYouGo, OpenedOne, PartnerCard, WelcomeBack } from './Partner.jsx';

/**
 * Unveil: the readiness checklist and the self-report (Pearl THL-135 GR-16,
 * THL-195 GR-37, THL-130 GR-10). Reached from the Path (GR-01): its "Ready to
 * invest" card opens GR-16, and its Unveil card opens GR-37.
 *
 * GR-16 /growth/ready        Ready to invest: a checklist to help her decide,
 *                            guidance and not a gate, and beside it where the
 *                            partner handoff starts (THL-136, Partner.jsx):
 *                            GR-23 before Protect, GR-22 with no partner,
 *                            the partner's card when one is configured. Each
 *                            leads to GR-37 for an account opened anywhere.
 * GR-37 /growth/unveil       Opened an investing account? Asks the kind of
 *                            account only — never where, a login or a balance.
 *                            "Mark Unveil done" makes the path's Unveil step
 *                            done and leads to GR-10.
 * GR-10 /growth/unveil/done  Unveil done: the three phases, and the path, on
 *                            the moments' layout (Moments.jsx, GR-08, GR-09).
 *
 * "Read the basics" is Learn's five modules (THL-134): "2 of 5 modules", with
 * a link to the next, ticked once all five are read.
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
  const partner = {
    go: async () => { const r = await goToPartner(); window.location.assign(r.url); },
    notYet: async () => setData(await partnerNotYet()),
    notify: async () => setData(await partnerNotify()),
    opened: async () => {
      setData(await reportInvesting('not_sure', 'partner'));
      nav.onChanged?.();
      nav.show('done');
    },
  };
  if (view === 'done') return <UnveilDone data={data} onPath={() => nav.onTab?.('path')} />;
  return <ReadyPage data={data} nav={nav} partner={partner} returned={fromPartner()} />;
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
  const protect = checklist.find((c) => c.key === 'protect');
  return checklist.map((c) => {
    if (c.key === 'protect') {
      return { ...c, title: 'Protect is done',
               detail: c.done ? 'Your income covers your Essentials' : protectLeft(c),
               link: c.done ? null : c.next
                 ? { text: 'See the step', go: () => nav.toStep?.(c.next) }
                 : { text: 'See your path', go: () => nav.onTab?.('path') } };
    }
    if (c.key === 'anchor') {
      const of = `${money(c.counted / 100)} of ${money(c.target / 100)}`;
      if (!c.started && protect && !protect.done) {
        // GR-23: the Anchor is Build's, and Build hasn't started.
        return { ...c, todo: true, title: 'Your Anchor is under way', detail: 'Starts in Build', link: null };
      }
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
    const of = c.of ?? 5;
    return { ...c, title: 'Read the basics',
             detail: c.done ? `All ${of} modules read` : `${c.read ?? 0} of ${of} modules`,
             link: c.done ? null : { text: c.read > 0 ? 'Continue' : 'Start',
                                     go: () => nav.toLearn?.(c.next, 'ready') } };
  });
}

const LEFT_WORDS = { income: 'confirm your income', bills: 'confirm your bills',
                     essentials: 'your income covers your Essentials' };

/** GR-23's "1 step left: your income covers your Essentials". */
function protectLeft(c) {
  if (!c.left) return 'Income, bills and Essentials covered';
  const next = LEFT_WORDS[c.next] ?? 'see your path';
  return c.left === 1 ? `1 step left: ${next}` : `${c.left} steps left, starting with: ${next}`;
}

/** GR-16 Ready to invest, with the partner card (GR-19 to GR-23). */
export function ReadyPage({ data, nav, partner = {}, returned = false }) {
  const rows = checklistRows(data.checklist, nav);
  const report = data.report;
  const protectDone = !!data.checklist.find((c) => c.key === 'protect')?.done;
  const p = data.partner ?? { configured: false };
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dismissed, setDismissed] = useState(false);
  const welcome = !dismissed && p.configured && !report && protectDone && (p.welcome || returned);
  const run = (fn) => async () => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(e.message); setBusy(false); return; }
    setBusy(false);
  };
  return (
    <div className="pk hm-page in-page pj-page">
      {welcome && (
        <WelcomeBack name={p.name} busy={busy} onYes={() => setDialog('opened')}
                     onNotYet={run(async () => { await partner.notYet?.(); setDismissed(true); })} />
      )}
      <header className="in-detail-head">
        <div className="in-back-row"><BackLink onClick={() => nav.onTab?.('path')}>Path</BackLink></div>
        <div className="pj-title-row">
          <div className="hm-head">
            <p className="pk-overline accent">Unveil</p>
            <h1 className="pk-h1">Ready to invest</h1>
          </div>
          <span className={protectDone ? undefined : 'gr-faded'}><Mark phase="unveil" width={58} /></span>
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
                <span className={`pj-check${r.done ? ' done' : ''}${r.todo ? ' todo' : ''}`} aria-hidden="true">
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
        <div className="in-col">
          {report ? (
            <section className="hm-card in-card" aria-labelledby="pj-opened-title">
              <p className="pk-overline accent">When you’re ready</p>
              <h2 className="pk-h2" id="pj-opened-title">Opened an investing account?</h2>
              <p className="pk-label pk-muted">{`You told Pearl you opened ${article(report.label)}, so Unveil is done.`}</p>
              <Link onClick={() => nav.show('unveil')}>Change the kind of account</Link>
            </section>
          ) : (
            <PartnerCard partner={p} protectDone={protectDone} primary={!welcome} busy={busy}
                         onHow={() => setDialog('go')} onReport={() => nav.show('unveil')}
                         onNotify={run(() => partner.notify?.())}
                         onLearn={() => nav.toLearn?.('', '')} />
          )}
          {error && !dialog && <p className="pj-field-note" role="alert">{error}</p>}
          <Link onClick={() => nav.show('calculator')}>Try the growth calculator</Link>
        </div>
      </div>
      {dialog === 'go' && (
        <BeforeYouGo name={p.name} busy={busy} error={error}
                     onClose={() => { setDialog(null); setError(''); }}
                     onGo={run(() => partner.go?.())} />
      )}
      {dialog === 'opened' && (
        <OpenedOne busy={busy} error={error} onClose={() => { setDialog(null); setError(''); }}
                   onConfirm={run(() => partner.opened?.())} />
      )}
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

/** Is Unveil done: her word for it, or a linked investment account? */
const unveilDone = (data) => !!data.report
  || (data.path?.phase === 'unveil' && (data.path?.steps ?? []).length > 0
      && data.path.steps.every((s) => s.done));

/** GR-10 Unveil done, on the moments' layout (GR-08, GR-09). */
export function UnveilDone({ data, onPath }) {
  const phases = data.path?.phases ?? [];
  const unveiled = unveilDone(data);
  const isDone = (p) => p.state === 'done' || (p.key === 'unveil' && unveiled);
  const everything = phases.length > 0 && phases.every(isDone);
  return (
    <MomentLayout phase="unveil" overline="Unveil · Done" title="You opened your first investment account"
                  sub={everything ? 'Protect, Build and Unveil: all three done. What you’ve built stays yours.'
                    : 'Unveil is done. What you’ve built stays yours, and the rest of your path is still there.'}>
      <ol className="pj-done-phases" aria-label="Your path">
        {phases.map((p) => (
          <li key={p.key}>
            <Mark phase={p.key} width={64} />
            <span className="pk-h3">{p.label}</span>
            <span className="pk-label pk-muted">{isDone(p) ? 'Done ✓' : p.state === 'now' ? 'Now' : 'Ahead'}</span>
          </li>
        ))}
      </ol>
      <PButton onClick={onPath}>See your path</PButton>
    </MomentLayout>
  );
}
