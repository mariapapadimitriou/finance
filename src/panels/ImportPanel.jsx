import { useEffect, useRef, useState } from 'react';
import { Card, ErrorNote } from '../components/ui.jsx';
import { clearLedger, getImports, getSources, importFiles, money } from '../api.js';

export default function ImportPanel({ accounts, onImported }) {
  const [sources, setSources] = useState(null);
  const [history, setHistory] = useState([]);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);

  async function refresh() {
    const [s, h] = await Promise.all([getSources(), getImports()]);
    setSources(s);
    setHistory(h.imports ?? []);
  }

  useEffect(() => { refresh().catch(setError); }, []);

  async function handleFiles(fileList) {
    const files = Array.from(fileList || []);
    if (files.length === 0) return;

    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const payload = await Promise.all(files.map(async (f) => ({
        name: f.name,
        content: await f.text(),
      })));
      const r = await importFiles(payload);
      setResults(r.results);
      await refresh();
      await onImported();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function reset() {
    if (!window.confirm(
      'Delete every imported transaction? Budgets and category corrections are kept. '
      + 'This cannot be undone, but you can re-import your CSVs.'
    )) return;
    await clearLedger();
    await refresh();
    await onImported();
  }

  const csv = sources?.sources?.find((s) => s.key === 'csv');
  const others = sources?.sources?.filter((s) => s.key !== 'csv') ?? [];

  return (
    <div className="stack">
      <div
        className={`dropzone${over ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <h3>{busy ? 'Importing…' : 'Drop your card statements here'}</h3>
        <p style={{ margin: '6px 0 14px' }}>
          CSV exports from any card. The issuer&apos;s format is detected
          automatically, and re-importing an overlapping date range is safe —
          duplicates are dropped, not double-counted.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          multiple
          onChange={(e) => handleFiles(e.target.files)}
          style={{ display: 'none' }}
          id="file-input"
        />
        <button className="btn primary" onClick={() => inputRef.current?.click()} disabled={busy}>
          Choose files
        </button>
      </div>

      <ErrorNote error={error} />

      {results && (
        <Card title="Import results">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th><th>Detected format</th><th>Card</th>
                  <th className="r">Imported</th><th className="r">Duplicates</th>
                  <th className="r">Skipped</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.filename}>
                    <td className="merchant">{r.filename}</td>
                    <td>
                      {r.format_label}
                      <div className="desc">{Math.round(r.confidence * 100)}% match</div>
                    </td>
                    <td className="muted">{r.account_name}</td>
                    <td className="r">{r.imported}</td>
                    <td className="r muted">{r.duplicates}</td>
                    <td className="r muted">{r.skipped_rows}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {results.flatMap((r) => (r.warnings ?? []).map((w) => (
            <div className="notice" key={`${r.filename}-${w}`} style={{ marginTop: 10 }}>
              <strong>{r.filename}:</strong> {w}
            </div>
          )))}
        </Card>
      )}

      <div className="grid cols-2">
        <Card title="How to get your CSVs" hint={csv?.detail}>
          <ol className="steps">
            {(csv?.setup_steps ?? []).map((s) => <li key={s}>{s}</li>)}
          </ol>
          <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
            Everything is parsed locally and stored in a SQLite file on this
            machine. Nothing is uploaded anywhere.
          </p>
        </Card>

        <Card title="Automatic sync" hint="Alternatives to downloading CSVs by hand">
          {others.map((s) => (
            <div key={s.key} style={{ marginBottom: 14 }}>
              <div className="row">
                <strong>{s.label}</strong>
                <span className={`pill ${s.available ? 'good' : ''}`}>
                  {s.available ? 'Configured' : 'Not configured'}
                </span>
              </div>
              <p className="small muted" style={{ margin: '6px 0' }}>{s.detail}</p>
              {!s.available && s.setup_steps?.length > 0 && (
                <details>
                  <summary className="small" style={{ cursor: 'pointer', color: 'var(--series-1)' }}>
                    Setup steps
                  </summary>
                  <ol className="steps">
                    {s.setup_steps.map((step) => <li key={step}>{step}</li>)}
                  </ol>
                  {s.setup_url && (
                    <p className="small">
                      <a href={s.setup_url} target="_blank" rel="noreferrer">{s.setup_url}</a>
                    </p>
                  )}
                </details>
              )}
            </div>
          ))}
        </Card>
      </div>

      {accounts.length > 0 && (
        <Card title="Cards in your ledger">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Card</th><th className="r">Transactions</th>
                  <th>Covers</th><th className="r">Total spend</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.account_id}>
                    <td className="merchant">{a.account_name}</td>
                    <td className="r">{a.transactions}</td>
                    <td className="muted">{a.first_date} → {a.last_date}</td>
                    <td className="r">{money(a.total_spend)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {history.length > 0 && (
        <Card title="Import history">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th><th>File</th><th>Format</th>
                  <th className="r">Imported</th><th className="r">Duplicates</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td className="muted">{h.created_at?.slice(0, 16)}</td>
                    <td>{h.filename}</td>
                    <td className="muted">{h.format_label}</td>
                    <td className="r">{h.imported}</td>
                    <td className="r muted">{h.duplicates}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <span className="spacer" />
            <button className="btn quiet" onClick={reset}>Clear all transactions</button>
          </div>
        </Card>
      )}
    </div>
  );
}
