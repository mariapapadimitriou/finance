import { useEffect, useMemo, useState } from 'react';
import { Card, ErrorNote, Loading, Notice } from '../components/ui.jsx';
import { getCategoryGroups, setCategoryGroups } from '../api.js';

const OWN = '';
const NEW = '__new__';

/**
 * Budget lines: which categories share one line in your budget.
 *
 * A transaction deserves an accurate label, which is why there are thirty-odd
 * categories, and that is too many lines for a budget anyone keeps. This is
 * where you fold them: Lodging into Travel, Health and Personal Care into one
 * line, Coffee left on its own. Only budgeting sees the result — the plan's
 * split and the Budgets table. Transactions keep their categories everywhere
 * else, and the weekly number is worked out per category, so nothing here can
 * change what you may spend today.
 *
 * Two rules are enforced by the server and pre-empted here, so the choices
 * offered are only ones that will save: a line cannot itself be folded into
 * another, and a category a piggy bank pays for only shares a line with
 * others a piggy bank pays for. Joining a bank's line is how a category
 * becomes one: the server hands it to that bank.
 */
export default function CategoriesPanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [draft, setDraft] = useState({});       // category -> line, '' = own
  const [naming, setNaming] = useState({});     // category -> new line name
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [adopted, setAdopted] = useState({});

  async function load() {
    setLoadError(null);
    try {
      const d = await getCategoryGroups();
      setData(d);
      setDraft(d.groups ?? {});
      setNaming({});
    } catch (e) {
      setLoadError(e);
    }
  }

  useEffect(() => { load(); }, []);

  // Which categories a piggy bank pays for, from the server's own lines —
  // the client does not get its own copy of that rule.
  const funded = useMemo(() => {
    const out = new Set();
    for (const line of data?.lines ?? []) {
      if (line.bank_funded) line.members.forEach((m) => out.add(m));
    }
    return out;
  }, [data]);

  if (loadError) return <ErrorNote error={loadError} onRetry={load} />;
  if (!data) return <Loading what="categories" />;

  const categories = data.categories;
  const lineOf = (c) => {
    const v = draft[c];
    if (v === NEW) return (naming[c] ?? '').trim() || c;
    return v || c;
  };
  const holds = (c) => categories.filter((o) => o !== c && lineOf(o) === c);
  // Every named line on offer: saved ones, ones chosen in this draft, and —
  // the case that was missing — one being typed right now, so the second
  // category can join a line the first one has only just named.
  const named = [...new Set([
    ...(data.named ?? []),
    ...Object.entries(draft)
      .filter(([, v]) => v && v !== NEW && !categories.includes(v))
      .map(([, v]) => v),
    ...Object.entries(draft)
      .filter(([, v]) => v === NEW)
      .map(([c]) => (naming[c] ?? '').trim())
      .filter((n) => n && !categories.includes(n)),
  ])].sort();

  // A named line is bank-funded if what is in it is.
  const namedFunded = (name) => {
    const members = categories.filter((c) => lineOf(c) === name);
    return members.length > 0 && members.every((m) => funded.has(m));
  };

  // A category a piggy bank pays for only joins others it pays for. One no
  // bank pays for can join anything: joining a bank's line hands it to that
  // bank, which is what putting Lodging under Travel means.
  function options(c) {
    const bf = funded.has(c);
    const others = categories.filter((o) =>
      o !== c && !draft[o] && (!bf || funded.has(o)));
    const names = named.filter((n) => {
      const members = categories.filter((m) => m !== c && lineOf(m) === n);
      return members.length === 0 || !bf || namedFunded(n);
    });
    return { others, names };
  }

  // What changes against what is saved, as the server will see it.
  const outgoing = Object.fromEntries(categories.map((c) => {
    const v = draft[c];
    if (v === NEW) return [c, (naming[c] ?? '').trim() || null];
    return [c, v || null];
  }));
  const before = data.groups ?? {};
  const dirty = categories.some((c) => (outgoing[c] ?? null) !== (before[c] ?? null));

  async function save() {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const r = await setCategoryGroups(outgoing);
      await load();
      setAdopted(r?.adopted ?? {});
      await onChanged?.();
      setSaved(true);
    } catch (e) {
      setSaveError(e);                 // the draft survives on purpose
    } finally {
      setSaving(false);
    }
  }

  const lines = data.lines.filter((l) => l.members.length > 1);

  return (
    <div className="stack">
      <Card title="Budget lines"
            actions={dirty && (
              <div className="row" style={{ gap: 8 }}>
                <button className="btn quiet" onClick={load} disabled={saving}>
                  Discard
                </button>
                <button className="btn primary" onClick={save} disabled={saving}>
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            )}>

        <ErrorNote error={saveError} />
        {saved && !dirty && (
          <Notice kind="good">
            Saved
            {Object.entries(adopted).map(([cat, bank]) => (
              <div key={cat}>{bank} piggy bank now pays for {cat}</div>
            ))}
          </Notice>
        )}

        {lines.length > 0 && (
          <div className="stack" style={{ gap: 6, margin: '4px 0 16px' }}>
            {lines.map((l) => (
              <div key={l.name} className="small">
                <strong>{l.name}</strong>{' '}
                <span className="muted">
                  — {l.members.join(', ')}
                  {l.bank_funded && ' · paid for by a piggy bank'}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Budgeted as</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => {
                const children = holds(c);
                const { others, names } = options(c);
                const value = draft[c] ?? OWN;
                return (
                  <tr key={c}>
                    <td>
                      {c}
                      {funded.has(c) && (
                        <span className="muted small"> · piggy bank</span>
                      )}
                    </td>
                    <td>
                      {children.length > 0 ? (
                        // A line holding others cannot be folded itself — one
                        // level is what a budget needs, and two let a cycle in.
                        <span className="muted small">
                          Its own line, holding {children.join(', ')}
                        </span>
                      ) : (
                        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                          <select
                            value={value}
                            aria-label={`Budget ${c} as`}
                            onChange={(e) => setDraft((d) => ({
                              ...d, [c]: e.target.value,
                            }))}
                          >
                            <option value={OWN}>Its own line</option>
                            {others.length > 0 && (
                              <optgroup label="Put it with">
                                {others.map((o) => (
                                  <option key={o} value={o}>
                                    {o}{!funded.has(c) && funded.has(o) ? ' · piggy bank' : ''}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            {names.length > 0 && (
                              <optgroup label="Your lines">
                                {names.map((n) => (
                                  <option key={n} value={n}>
                                    {n}{!funded.has(c) && namedFunded(n) ? ' · piggy bank' : ''}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            <option value={NEW}>A new line…</option>
                          </select>
                          {value === NEW && (
                            <input
                              type="text"
                              value={naming[c] ?? ''}
                              placeholder="Name it, e.g. Health & care"
                              maxLength={40}
                              aria-label={`Name of the new line for ${c}`}
                              onChange={(e) => setNaming((n) => ({
                                ...n, [c]: e.target.value,
                              }))}
                              style={{ flex: '1 1 180px' }}
                            />
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
