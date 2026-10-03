import { useState } from 'react';
import { Card, Empty, ErrorNote, Notice, StatusPill } from '../components/ui.jsx';
import { dateLabel, dismissFinding, money, pct, restoreFinding } from '../api.js';

const EFFORT = {
  'one-off': { label: 'Quick wins', hint: 'Do it once' },
  negotiate: { label: 'Negotiate', hint: 'One phone call' },
  habit: { label: 'Habits', hint: 'Takes ongoing effort' },
};

const CONFIDENCE = (c) =>
  (c >= 0.8 ? 'Likely' : c >= 0.55 ? 'Probably' : 'Worth checking');

export default function SavingsPanel({ insights, onRefresh, onTab }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  // The one just hidden, so it can be put back with a click.
  const [justHidden, setJustHidden] = useState(null);

  const findings = insights?.findings ?? [];
  const summary = insights?.summary ?? {};
  const observations = insights?.observations ?? [];
  const hidden = insights?.hidden ?? [];

  async function dismiss(f) {
    setBusy(f.id);
    setError(null);
    try {
      await dismissFinding(f.id);
      setJustHidden(f);
      await onRefresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function restore(id) {
    setError(null);
    try {
      await restoreFinding(id);
      setJustHidden(null);
      await onRefresh();
    } catch (e) {
      setError(e);
    }
  }

  const banner = (
    <>
      <ErrorNote error={error} />
      {justHidden && (
        <Notice>
          Hidden &ldquo;{justHidden.title}&rdquo;.{' '}
          <button className="link" onClick={() => restore(justHidden.id)}>Undo</button>
        </Notice>
      )}
    </>
  );


  if (findings.length === 0) {
    return (
      <div className="stack">
        {banner}
        <Observations rows={observations} onTab={onTab} />
        <Empty title="Nothing to cut right now">
          Spending looks tight, or there isn&apos;t enough history yet (most
          checks need 3+ months).
        </Empty>
        <HiddenList rows={hidden} onRestore={restore} />
      </div>
    );
  }

  const grouped = ['one-off', 'negotiate', 'habit']
    .map((effort) => [effort, findings.filter((f) => f.effort === effort)])
    .filter(([, list]) => list.length > 0);

  return (
    <div className="stack">
      {banner}
      <Observations rows={observations} onTab={onTab} />

      <div className="card hero-card">
        <div className="hero">
          <div className="figure num">{money(summary.weighted_annual ?? 0)}</div>
          <div className="caption">
            a year you could realistically save
            {' '}<span className="muted">
              (up to {money(summary.annual_total ?? 0)} if every idea pans out)
            </span>
          </div>
        </div>
      </div>


      {grouped.map(([effort, list]) => (
        <div key={effort} className="stack">
          <div className="section-head">
            <h2>{EFFORT[effort]?.label ?? effort}</h2>
            <span className="muted small">{EFFORT[effort]?.hint}</span>
            <span className="spacer" />
            <span className="muted small num">
              {money(list.reduce((s, f) => s + f.annual_saving, 0))}/yr
            </span>
          </div>
          {list.map((f) => (
            <Finding key={f.id} finding={f} busy={busy === f.id} onDismiss={() => dismiss(f)} />
          ))}
        </div>
      ))}

      <HiddenList rows={hidden} onRestore={restore} />
    </div>
  );
}

function Finding({ finding: f, busy, onDismiss }) {
  return (
    <section className={`card finding effort-${f.effort}`}>
      <div className="top">
        <div>
          <h3>{f.title}</h3>
          <div className="meta">
            <span className="pill" title={`${pct(f.confidence)} confidence`}>
              {CONFIDENCE(f.confidence)}
            </span>
            {f.category && <span className="pill">{f.category}</span>}
            {f.merchants?.slice(0, 3).map((m) => (
              <span className="pill" key={m}>{m}</span>
            ))}
            {f.merchants?.length > 3 && (
              <span className="muted small">+{f.merchants.length - 3} more</span>
            )}
          </div>
        </div>
        <div className="save">
          <div className="big num">{money(f.annual_saving)}</div>
          <div className="per">per year</div>
          <div className="per num">{money(f.monthly_saving)}/mo</div>
        </div>
      </div>

      <details className="evidence">
        <summary>Details</summary>
        <p className="small" style={{ color: 'var(--ink-2)' }}>{f.detail}</p>
        {f.assumption && <div className="assumption">{f.assumption}</div>}
        {f.evidence?.length > 0 && (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr><th>Date</th><th>Merchant</th><th>Card</th><th className="r">Amount</th></tr>
              </thead>
              <tbody>
                {f.evidence.map((e, i) => (
                  <tr key={`${e.date}-${e.merchant}-${i}`}>
                    <td>{dateLabel(e.date)}</td>
                    <td className="merchant">{e.merchant}</td>
                    <td className="muted">{e.account}</td>
                    <td className="r">{money(e.amount, { cents: true })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>

      <div className="row" style={{ marginTop: 12 }}>
        <span className="spacer" />
        <button className="btn quiet" onClick={onDismiss} disabled={busy}>
          {busy ? 'Hiding…' : 'Hide'}
        </button>
      </div>
    </section>
  );
}

/** Findings you hid, offered back by name. */
function HiddenList({ rows, onRestore }) {
  if (!rows || rows.length === 0) return null;
  return (
    <details className="card">
      <summary className="muted small" style={{ cursor: 'pointer' }}>
        {rows.length} hidden
      </summary>
      <div className="stack" style={{ gap: 8, marginTop: 12 }}>
        {rows.map((r) => (
          <div key={r.id} className="row" style={{ gap: 10 }}>
            <span>{r.title}</span>
            <span className="muted small num">{money(r.annual_saving)}/yr</span>
            <span className="spacer" />
            <button className="btn quiet" onClick={() => onRestore(r.id)}>Restore</button>
          </div>
        ))}
      </div>
    </details>
  );
}

const SEVERITY = {
  act: { state: 'critical', label: 'Act' },
  watch: { state: 'warning', label: 'Note' },
  good: { state: 'good', label: 'Good' },
};

/**
 * What your plan says about itself.
 *
 * Written in advance, each with the condition that makes it true, and shown
 * only when that condition holds — see finance/insights/profile.py. The
 * figures come from the same functions the tabs they link to use, so following
 * one of these never lands you on a page that disagrees with it.
 */
function Observations({ rows, onTab }) {
  if (!rows || rows.length === 0) return null;

  return (
    <Card title="About your plan">
      <div className="stack" style={{ gap: 16 }}>
        {rows.map((o) => {
          const tone = SEVERITY[o.severity] ?? SEVERITY.watch;
          return (
            <div key={o.id}>
              <div className="row" style={{ gap: 10, marginBottom: 4 }}>
                <StatusPill state={tone.state}>{tone.label}</StatusPill>
                <strong>{o.title}</strong>
                {o.metric && (
                  <>
                    <span className="spacer" />
                    <span className="num small muted">{o.metric}</span>
                  </>
                )}
              </div>
              {o.detail && (
                <details className="small" style={{ margin: '0 0 6px', color: 'var(--ink-2)' }}>
                  <summary style={{ cursor: 'pointer' }}>Why</summary>
                  <p style={{ margin: '6px 0 0' }}>{o.detail}</p>
                </details>
              )}
              {o.tab && o.action && onTab && (
                <button className="link" onClick={() => onTab(o.tab)}>
                  {o.action}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
