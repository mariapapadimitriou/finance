import { useState } from 'react';
import { Card, Empty } from '../components/ui.jsx';
import { dateLabel, dismissFinding, money, pct, restoreFinding, runNarrative } from '../api.js';

const EFFORT = {
  'one-off': { label: 'One-off action', hint: 'Cancel, dispute or switch once and it stays saved.' },
  habit: { label: 'Habit change', hint: 'Needs a sustained change, not a single decision.' },
  negotiate: { label: 'Negotiate', hint: 'A call or a cancellation threat usually settles it.' },
};

const CONFIDENCE = (c) =>
  (c >= 0.8 ? 'High confidence' : c >= 0.55 ? 'Moderate confidence' : 'Worth checking');

export default function SavingsPanel({ insights, onRefresh }) {
  const [busy, setBusy] = useState(null);
  const [narrative, setNarrative] = useState(null);
  const [narrativeError, setNarrativeError] = useState(null);

  const findings = insights?.findings ?? [];
  const summary = insights?.summary ?? {};
  const claude = insights?.narrative ?? {};

  async function dismiss(id) {
    setBusy(id);
    try {
      await dismissFinding(id);
      await onRefresh();
    } finally {
      setBusy(null);
    }
  }

  async function askClaude() {
    setBusy('narrative');
    setNarrativeError(null);
    try {
      setNarrative(await runNarrative());
    } catch (e) {
      setNarrativeError(e);
    } finally {
      setBusy(null);
    }
  }

  if (findings.length === 0) {
    return (
      <Empty title="Nothing to cut that we can see">
        Either your spending is already tight, or there isn&apos;t enough history
        yet. Most rules need three or more months to tell a habit from a
        one-off — import a longer date range and check back.
      </Empty>
    );
  }

  const grouped = ['one-off', 'negotiate', 'habit']
    .map((effort) => [effort, findings.filter((f) => f.effort === effort)])
    .filter(([, list]) => list.length > 0);

  return (
    <div className="stack">
      <Card>
        <div className="hero">
          <div className="figure num">{money(summary.weighted_annual ?? 0)}</div>
          <div className="caption">
            a year in identified savings, weighted by how confident each finding is.
            <br />
            Taken at face value the findings total {money(summary.annual_total ?? 0)};
            the weighted figure is the honest one.
          </div>
        </div>
        <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
          Every figure below is computed from your own transactions. Each finding
          states what it assumes, because a recommendation you can&apos;t audit is
          just a guess — open the evidence to see the exact charges behind it.
        </p>
      </Card>

      {(claude.available || narrative) && (
        <Card
          title="Written read"
          hint={claude.available
            ? 'Optional — sends category totals and merchant names to Claude, never individual transactions'
            : ''}
          actions={
            <button className="btn" onClick={askClaude} disabled={busy === 'narrative'}>
              {busy === 'narrative' ? 'Thinking…' : narrative ? 'Regenerate' : 'Ask Claude'}
            </button>
          }
        >
          {narrativeError && <div className="notice error">{String(narrativeError.message)}</div>}
          {narrative?.text
            ? <div className="narrative">{narrative.text}</div>
            : <p className="muted small" style={{ margin: 0 }}>
                The findings below stand on their own; this adds a written summary
                that ranks them for you.
              </p>}
        </Card>
      )}

      {!claude.available && (
        <div className="notice">
          <strong>Optional Claude summary is off.</strong> {claude.detail} The rule
          engine below works entirely offline and needs no key.
        </div>
      )}

      {grouped.map(([effort, list]) => (
        <div key={effort} className="stack">
          <div className="row">
            <h2>{EFFORT[effort]?.label ?? effort}</h2>
            <span className="muted small">{EFFORT[effort]?.hint}</span>
            <span className="spacer" />
            <span className="muted small num">
              {money(list.reduce((s, f) => s + f.annual_saving, 0))}/yr
            </span>
          </div>
          {list.map((f) => (
            <Finding key={f.id} finding={f} busy={busy === f.id} onDismiss={() => dismiss(f.id)} />
          ))}
        </div>
      ))}

      <DismissedNote onRefresh={onRefresh} />
    </div>
  );
}

function Finding({ finding: f, busy, onDismiss }) {
  return (
    <section className={`card finding effort-${f.effort}`}>
      <div className="top">
        <div>
          <h3>{f.title}</h3>
          <p>{f.detail}</p>
          <div className="meta">
            <span className="pill">{CONFIDENCE(f.confidence)} · {pct(f.confidence)}</span>
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

      {f.evidence?.length > 0 && (
        <details className="evidence">
          <summary>Show the {f.evidence.length} charges behind this</summary>
          <div className="table-wrap">
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
        </details>
      )}

      {f.assumption && <div className="assumption">Assumption: {f.assumption}</div>}

      <div className="row" style={{ marginTop: 12 }}>
        <span className="spacer" />
        <button className="btn quiet" onClick={onDismiss} disabled={busy}>
          {busy ? 'Dismissing…' : 'Not useful — hide this'}
        </button>
      </div>
    </section>
  );
}

function DismissedNote({ onRefresh }) {
  const [id, setId] = useState('');
  const [done, setDone] = useState(false);

  async function restore(e) {
    e.preventDefault();
    if (!id.trim()) return;
    await restoreFinding(id.trim());
    await onRefresh();
    setId('');
    setDone(true);
  }

  return (
    <details className="card">
      <summary className="muted small" style={{ cursor: 'pointer' }}>
        Restore a dismissed finding
      </summary>
      <form className="row" onSubmit={restore} style={{ marginTop: 12 }}>
        <input
          type="text"
          value={id}
          onChange={(e) => { setId(e.target.value); setDone(false); }}
          placeholder="Finding id (e.g. fees_1a2b3c4d5e)"
          style={{ flex: 1, minWidth: 220 }}
        />
        <button className="btn" type="submit">Restore</button>
        {done && <span className="small muted">Restored.</span>}
      </form>
    </details>
  );
}
