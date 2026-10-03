import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, ErrorNote, Notice } from '../components/ui.jsx';
import {
  getBundled, getHealth, getImports, getSources, importBundled,
  importFiles, money,
} from '../api.js';

export default function ImportPanel({ accounts, onImported, onTab }) {
  const [sources, setSources] = useState(null);
  const [storage, setStorage] = useState(null);
  const [history, setHistory] = useState([]);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);

  async function refresh() {
    const [s, h, health] = await Promise.all([
      getSources(), getImports(), getHealth().catch(() => null),
    ]);
    setSources(s);
    setHistory(h.imports ?? []);
    setStorage(health?.storage ?? null);
  }

  useEffect(() => { refresh().catch(setError); }, []);

  async function handleFiles(fileList) {
    const files = Array.from(fileList || []);
    if (files.length === 0) return;

    setBusy(true);
    setError(null);
    setResults(null);
    try {
      // Multipart, not text: reading a PDF with file.text() would mangle it.
      const form = new FormData();
      files.forEach((f) => form.append('files', f, f.name));
      const r = await importFiles(form);
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


  // Before the body renders: a failed refresh leaves `sources` null, and the
  // cards below would otherwise draw themselves with an undefined hint and an
  // empty list of steps — a failure that looks like furniture.
  if (error && !sources) return <ErrorNote error={error} onRetry={refresh} />;

  const csv = sources?.sources?.find((s) => s.key === 'csv');
  const others = sources?.sources?.filter((s) => s.key !== 'csv') ?? [];

  return (
    <div className="stack">
      {onTab && (
        <Notice>
          Tip: connected cards update themselves.{' '}
          <button className="link" onClick={() => onTab('banks')}>
            Connect a card
          </button>
        </Notice>
      )}

      <BundledStatements onImported={onImported} />

      {/* Said before the upload, not after it. On a serverless instance with
          no database the ledger lives in that instance's /tmp, so an upload
          can disappear when the instance is recycled and a request served by a
          different instance never sees it. Connecting a Postgres removes this
          notice by removing the problem. */}
      {storage === 'ephemeral' && (
        <Notice>
          <strong>Uploads here are temporary</strong> — no database is attached.
          Add Postgres in Vercel (Storage → Create Database) and redeploy.
        </Notice>
      )}

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
        <h3>{busy ? 'Reading…' : 'Drop statements here'}</h3>
        <p style={{ margin: '8px auto 18px', maxWidth: '46ch' }}>
          PDF or CSV, any card. Duplicates are skipped.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.pdf,text/csv,application/pdf"
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
        <Card title="Imported">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th><th>Format</th><th>Card</th>
                  <th className="r">Imported</th><th className="r">Duplicates</th>
                  <th className="r">Skipped</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={`${r.filename}-${r.account_name}`}>
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
            <div key={`${r.filename}-${w}`} style={{ marginTop: 12 }}>
              <Notice><strong>{r.filename}:</strong> {w}</Notice>
            </div>
          )))}
        </Card>
      )}

      <div className="grid cols-2">
        <Card title="Getting your statements">
          <ol className="steps">
            {(csv?.setup_steps ?? []).map((s) => <li key={s}>{s}</li>)}
          </ol>
          {/* The privacy claim has to match where the data actually goes:
              on a deployment it is not "this machine", and saying so anyway
              would be the one kind of inaccuracy that really matters here. */}
          <p className="small muted" style={{ marginTop: 16, marginBottom: 0 }}>
            {storage === 'sqlite'
              ? 'Stays on this computer.'
              : "Stored only in this app's database."}
          </p>
        </Card>

        <Card title="Automatic sync">
          {others.map((s) => (
            <div key={s.key} style={{ marginBottom: 14 }}>
              <div className="row">
                <strong>{s.label}</strong>
                <span className={`pill ${s.available ? 'good' : ''}`}>
                  {s.available ? 'Configured' : 'Not configured'}
                </span>
              </div>
              <p className="small muted" style={{ margin: '6px 0' }}>{s.detail}</p>
              {s.key === 'plaid' && (
                <p className="small" style={{ margin: '6px 0' }}>
                  Set up under <strong>Connections</strong>.
                </p>
              )}
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


      {history.length > 0 && (
        <Card title="Recent imports">
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
        </Card>
      )}
    </div>
  );
}

/**
 * Statements shipped with the app, for a card that cannot be connected.
 *
 * A closed account has no feed to sync: its history is complete, it will never
 * change, and the only copy that survives a database being emptied is the one
 * committed alongside the code. That makes this the one import worth offering
 * as a button rather than a file picker — there is no file to choose, and the
 * account it lands in is already decided.
 *
 * Loading twice is harmless and the button says so, because a button that
 * might double a year of spending is a button nobody dares press.
 */
function BundledStatements({ onImported }) {
  const [sets, setSets] = useState([]);
  const [busy, setBusy] = useState(null);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setSets((await getBundled()).bundled ?? []);
    } catch {
      setSets([]);          // an older build has no such route; say nothing
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function run(key) {
    setBusy(key);
    setError(null);
    try {
      const r = await importBundled(key);
      setDone(r);
      await load();
      await onImported();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  if (sets.length === 0) return null;

  return (
    <Card title="Included statements">
      <ErrorNote error={error} />

      {sets.map((b) => (
        <div key={b.key} className="row"
             style={{ justifyContent: 'space-between', alignItems: 'flex-start',
                      gap: 16, flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <div className="merchant">{b.label}</div>
            <div className="desc">
              {b.rows} transactions · {b.period}
            </div>
            <p className="small muted" style={{ margin: '6px 0 0', maxWidth: '54ch' }}>
              {b.note}
            </p>
          </div>
          <button className={`btn${b.loaded ? ' quiet' : ' primary'}`}
                  disabled={busy === b.key}
                  onClick={() => run(b.key)}>
            {busy === b.key ? 'Loading…'
              : b.loaded ? 'Loaded — check again' : 'Load these'}
          </button>
        </div>
      ))}

      {done && (
        <Notice kind="good">
          {done.imported > 0
            ? `Added ${done.imported} transaction${done.imported === 1 ? '' : 's'}.`
            : 'Already loaded.'}
          {done.duplicates > 0 && ` ${done.duplicates} were already there.`}
          {done.warnings?.length > 0 && (
            <div className="small" style={{ marginTop: 8 }}>
              {done.warnings.join(' ')}
            </div>
          )}
        </Notice>
      )}

      <p className="assumption" style={{ marginBottom: 0 }}>
        Safe to load twice — duplicates are skipped.
      </p>
    </Card>
  );
}
