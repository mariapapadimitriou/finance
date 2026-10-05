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


  return (
    <div className="stack">
      {onTab && (
        <div>
          <button className="link" onClick={() => onTab('banks')}>
            Connect a card instead
          </button>
        </div>
      )}

      <BundledStatements onImported={onImported} />

      {/* Said before the upload, not after it. On a serverless instance with
          no database the ledger lives in that instance's /tmp, so an upload
          can disappear when the instance is recycled and a request served by a
          different instance never sees it. Connecting a Postgres removes this
          notice by removing the problem. */}
      {storage === 'ephemeral' && (
        <Notice>
          <strong>Uploads are temporary</strong> · no database attached
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
        <h3>{busy ? 'Reading your statements…' : 'Drop your statements here'}</h3>
        <p className="muted" style={{ margin: '8px auto 18px' }}>PDF or CSV</p>
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
            <div key={`${r.filename}-${w}`} style={{ marginTop: 12 }}>
              <Notice><strong>{r.filename}:</strong> {w}</Notice>
            </div>
          )))}
        </Card>
      )}

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
    <Card title="Statements included with the app">
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
            : 'Already imported'}
          {done.duplicates > 0 && ` ${done.duplicates} were already there.`}
          {done.warnings?.length > 0 && (
            <div className="small" style={{ marginTop: 8 }}>
              {done.warnings.join(' ')}
            </div>
          )}
        </Notice>
      )}

    </Card>
  );
}
