import { useCallback, useEffect, useState } from 'react';
import {
  getAccountsOverview, getSetupAgain, hideSetupAgain, markSetupAgain, saveAccountSettings,
} from '../api.js';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { parsePeople } from './joint.js';
import { Field } from './GoalsParts.jsx';

/**
 * Set up again, after Start over (2026-10-29, finance/setup_again.py).
 *
 * Start over wipes what only she can say: which accounts she shares, her
 * income and bills, how each account counts, debt details. The history comes
 * back from the banks; these come back as a short list, on the "You're
 * starting fresh" page and on Home until each is done or she hides it.
 *
 * "Which accounts do you share?" is answered right here, and first-time
 * setup asks it too, after linking a bank.
 */

// Accounts someone else can share: a bank account or a card, linked.
const SHAREABLE = new Set(['chequing', 'savings', 'card', 'depository', 'credit']);
export function shareable(accounts = []) {
  return accounts.filter((a) => a.source === 'plaid' && SHAREABLE.has(a.kind));
}

/** "Cash ••6922", with the bank under it. */
export const accountLine = (a) => `${a.name}${a.mask ? ` ••${a.mask}` : ''}`;

/**
 * What saving the answers changes: `[[id, settings]]`, or `{ error }` when a
 * shared account has nobody named. `picks` is `{ id: { on, names } }`.
 */
export function sharedChanges(accounts, picks) {
  const out = [];
  for (const a of accounts) {
    const p = picks[a.id] ?? { on: !!a.joint, names: (a.joint_people ?? []).join(', ') };
    if (p.on) {
      const people = parsePeople(p.names);
      if (!people.length) return { error: `Say who you share ${accountLine(a)} with.`, id: a.id };
      const same = a.joint && people.length === (a.joint_people ?? []).length
        && people.every((n, i) => n === a.joint_people[i]);
      if (!same) out.push([a.id, { joint_people: people }]);
    } else if (a.joint) {
      out.push([a.id, { joint_share: null }]);
    }
  }
  return { changes: out };
}

/** The question and its answers, data in: for tests, Start over and setup. */
export function SharedAccountsForm({ accounts, busy = false, error = null, onSave, onNone,
                                     saveLabel = 'Save' }) {
  const [picks, setPicks] = useState(() => Object.fromEntries(accounts.map((a) => [a.id, {
    on: !!a.joint, names: (a.joint_people ?? []).join(', '),
  }])));
  const [problem, setProblem] = useState(null);
  const set = (id, patch) => { setProblem(null); setPicks((p) => ({ ...p, [id]: { ...p[id], ...patch } })); };
  const anyOn = Object.values(picks).some((p) => p.on);
  const save = () => {
    const plan = sharedChanges(accounts, picks);
    if (plan.error) { setProblem(plan); return; }
    onSave(plan.changes);
  };
  if (!accounts.length) {
    return (
      <>
        <p className="pk-muted">None of your linked accounts can be shared.</p>
        <PButton disabled={busy} onClick={() => onNone()}>Continue</PButton>
      </>
    );
  }
  return (
    <>
      <p className="pk-muted">
        On a shared account, only your part counts, and Pearl asks who put money in.
      </p>
      <div className="pk-choices su-shared">
        {accounts.map((a) => {
          const p = picks[a.id] ?? { on: false, names: '' };
          return (
            <div key={a.id} className="su-account">
              <Choice type="checkbox" checked={p.on} disabled={busy}
                      onChange={(on) => set(a.id, { on })}
                      label={accountLine(a)} description={a.institution || undefined} />
              {p.on && (
                <Field label="Who do you share it with?" id={`su-${a.id}`}
                       error={problem?.id === a.id ? problem.error : null}>
                  <input id={`su-${a.id}`} autoComplete="off" value={p.names} placeholder="Sam, Alex"
                         disabled={busy} onChange={(e) => set(a.id, { names: e.target.value })} />
                  {problem?.id !== a.id && <p className="gl-hint">Separate names with commas</p>}
                </Field>
              )}
            </div>
          );
        })}
      </div>
      {error && <Alert tone="caution">{error}</Alert>}
      <div className="su-actions">
        {anyOn ? (
          <PButton disabled={busy} onClick={save}>{busy ? 'Saving…' : saveLabel}</PButton>
        ) : (
          <PButton disabled={busy} onClick={() => onNone()}>None of these are shared</PButton>
        )}
      </div>
    </>
  );
}

/** The list itself, data in. */
export function SetupAgainList({ data, busy = false, onOpen, onHide, heading = 'Set Pearl up again' }) {
  const steps = data?.steps ?? [];
  const left = data?.left ?? 0;
  return (
    <section className="hm-card su-card" aria-labelledby="su-title">
      <h2 className="pk-h3" id="su-title">{heading}</h2>
      <p className="pk-muted">
        {left === 0 ? 'All done.'
          : `Start over cleared what only you can tell Pearl. ${left === 1 ? '1 thing' : `${left} things`} to set again.`}
      </p>
      <ul className="su-steps">
        {steps.map((s) => (
          <li key={s.key}>
            <button type="button" className={`su-step${s.done ? ' done' : ''}`} disabled={busy}
                    onClick={() => onOpen(s)}>
              <span className="su-tick" aria-hidden="true">
                {s.done ? <PIcon name="check" size={14} /> : null}
              </span>
              <span className="su-text">
                <span className="su-title">{s.title}</span>
                <span className="su-sub">{s.done ? 'Done' : s.sub}</span>
              </span>
              <PIcon name="chevronRight" size={16} />
            </button>
          </li>
        ))}
      </ul>
      {onHide && left > 0 && (
        <button type="button" className="hm-link" disabled={busy} onClick={onHide}>
          Hide this list
        </button>
      )}
    </section>
  );
}

/** Where each step goes. */
const PAGE = { income: 'income', accounts: 'accounts', debts: 'debts' };

/**
 * The list, loaded, with "Which accounts do you share?" in a sheet.
 * `always` shows it even when every step is done (right after Start over).
 */
export default function SetupAgain({ onTab, onChanged, version, always = false, heading }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState(null);       // accounts, once loaded
  const [error, setError] = useState(null);
  const load = useCallback(() => getSetupAgain().then(setData).catch(() => setData(null)), []);
  useEffect(() => { load(); }, [load, version]);
  if (!data || (!data.active && !(always && data.steps?.length))) return null;

  const open = async (s) => {
    if (s.key === 'shared') {
      setError(null);
      setBusy(true);
      try {
        const o = await getAccountsOverview();
        setSheet(shareable(o.linked ?? []));
      } catch (e) {
        setError(e.message);
      } finally {
        setBusy(false);
      }
      return;
    }
    // Opening Accounts or Debts is the step: she sees what to set there.
    if (s.key !== 'income') await markSetupAgain(s.key).catch(() => {});
    onTab?.(PAGE[s.key]);
  };
  const finishShared = async (changes) => {
    setBusy(true);
    setError(null);
    try {
      for (const [id, fields] of changes) await saveAccountSettings(id, fields);
      setData(await markSetupAgain('shared'));
      setSheet(null);
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <SetupAgainList data={data} busy={busy} heading={heading} onOpen={open}
                      onHide={always ? null : () => hideSetupAgain().then(setData).catch(() => {})} />
      {error && !sheet && <Alert tone="caution">{error}</Alert>}
      {sheet && (
        <div className="pk">
          <DetailPanel label="Which accounts do you share?" overline="" sheet className="pf-dialog"
                       onClose={() => setSheet(null)}>
            <h1 className="pk-h2">Which accounts do you share?</h1>
            <SharedAccountsForm accounts={sheet} busy={busy} error={error}
                                onSave={finishShared} onNone={() => finishShared([])} />
          </DetailPanel>
        </div>
      )}
    </>
  );
}

