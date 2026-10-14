import { useEffect, useMemo, useState } from 'react';
import { Avatar, Choice, ImpactNote, PButton, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, groupCategories } from './CategoryPicker.jsx';
import { getTxCases, markTx } from '../api.js';

/**
 * What was this? (2026-10-14; finance/marks.py). One question, one list of
 * answers, the same from the transactions list, the detail panel and Needs
 * a look. Each answer says in a sentence what it does to her numbers, asks
 * for what it needs (a category, which savings account, which purchase, a
 * kind of income, who put it in) and can end with "Do this for every
 * <merchant> from now on", which writes a rule she can see and undo in
 * Categories and rules.
 *
 * The cases come from the server, so the sheet never offers something the
 * row can't be. Saving goes through `markTx`, which answers like a change of
 * category: a title, what it did, and Undo.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const shortDate = (iso) => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

/** Which case to start on: the row's current one. */
export function startCase(data) {
  return data?.current && data.cases.some((c) => c.key === data.current) ? data.current : '';
}

/** Whether the choice is complete enough to save. */
export function ready(c, s) {
  if (!c) return false;
  switch (c.needs) {
    case 'category': return !!s.category;
    case 'account': return true;                       // the account is optional
    case 'amount': return Number(s.amount) > 0;
    case 'split': return true;
    case 'borrowed': return s.counted !== false || !!s.category;
    case 'reason': return true;
    case 'income_kind': return !!s.income_kind;
    case 'candidates': return !!s.charge;
    case 'refund': return !!s.charge || !!s.category;
    case 'person': return true;
    default: return true;
  }
}

/** The request body for a choice. */
export function bodyFor(c, s) {
  const out = { case: c.key };
  if (c.needs === 'category' || (c.needs === 'borrowed' && s.counted === false)
      || (c.needs === 'refund' && !s.charge) || (c.needs === 'amount' && s.category)) {
    out.category = s.category;
  }
  if (c.needs === 'borrowed') out.counted = s.counted !== false;
  if (c.needs === 'account') out.account = s.account || '';
  if (c.needs === 'amount') { out.amount = Number(s.amount); out.account = s.account || ''; }
  if (c.needs === 'reason') out.reason = s.reason || '';
  if (c.needs === 'income_kind') out.income_kind = s.income_kind;
  if (c.needs === 'candidates' || c.needs === 'refund') {
    if (s.charge) out.charge = s.charge;
    if (s.person) out.person = s.person;
  }
  if (c.needs === 'person') out.person = s.person || '';
  if (c.remember) out.remember = !!s.remember;
  return out;
}

function Candidate({ name, checked, onChange, c, what }) {
  const bits = [shortDate(c.date), txAmount(c.amount)];
  if (c.person) bits.push(`${c.person}’s share`);
  else if (c.share) bits.push(`about a 1/${c.share} share`);
  if (c.work) bits.push('left out as a work expense');
  if (c.exact) bits.push('exact match');
  return (
    <Choice name={name} checked={checked} onChange={onChange}
            label={`${what} ${c.merchant}`} description={bits.join(' · ')} />
  );
}

/** What one case asks for, under its row. */
function Needs({ c, data, s, set, spending, others }) {
  const name = `wwt-${data.id}-${c.key}`;
  switch (c.needs) {
    case 'category':
      return (
        <div className="wwt-sub">
          <p className="pk-label">What was it for?</p>
          <CategoryChips groups={spending} value={s.category} onChange={(v) => set({ category: v })}
                         label="What was it for?" />
        </div>
      );
    case 'account':
      if (!data.accounts.length) {
        return (
          <p className="pk-muted wwt-sub">
            Pearl doesn’t know a savings or investment account of yours yet. Add one on
            Profile › Accounts (with its last four digits) and transfers to it are sorted on
            their own.
          </p>
        );
      }
      return (
        <div className="wwt-sub">
          <p className="pk-label">{data.direction === 'out' ? 'Which account did it go to?' : 'Which account did it come out of?'}</p>
          <div className="pk-choices" role="radiogroup" aria-label="Which account?">
            <Choice name={`${name}-acct`} checked={!s.account} onChange={() => set({ account: '' })}
                    label="Not sure" />
            {data.accounts.map((a) => (
              <Choice key={a.id} name={`${name}-acct`} checked={s.account === a.id}
                      onChange={() => set({ account: a.id })} label={a.label}
                      description={a.source === 'hand' ? 'Added by you' : a.kind === 'investment' ? 'Investment' : 'Savings'} />
            ))}
          </div>
        </div>
      );
    case 'amount':
      return (
        <div className="wwt-sub">
          <label className="pk-label" htmlFor={`${name}-amt`}>How much was put away?</label>
          <input id={`${name}-amt`} className="wwt-input" type="number" inputMode="decimal" min="0.01"
                 step="0.01" value={s.amount || ''} onChange={(e) => set({ amount: e.target.value })} />
          {data.accounts.length > 0 && (
            <>
              <p className="pk-label">Into which account?</p>
              <div className="pk-choices" role="radiogroup" aria-label="Which account?">
                <Choice name={`${name}-acct`} checked={!s.account} onChange={() => set({ account: '' })}
                        label="Not sure" />
                {data.accounts.map((a) => (
                  <Choice key={a.id} name={`${name}-acct`} checked={s.account === a.id}
                          onChange={() => set({ account: a.id })} label={a.label} />
                ))}
              </div>
            </>
          )}
        </div>
      );
    case 'borrowed':
      return (
        <div className="wwt-sub">
          <div className="pk-choices" role="radiogroup" aria-label="What you bought with it">
            <Choice name={`${name}-c`} checked={s.counted !== false} onChange={() => set({ counted: true })}
                    label="What I bought with it is already in Pearl"
                    description="So this isn’t spending: it was counted when I bought it." />
            <Choice name={`${name}-c`} checked={s.counted === false} onChange={() => set({ counted: false })}
                    label="What I bought with it isn’t in Pearl"
                    description="Count this as the spending, in a category." />
          </div>
          {s.counted === false && (
            <CategoryChips groups={spending} value={s.category} onChange={(v) => set({ category: v })}
                           label="What was it for?" />
          )}
        </div>
      );
    case 'reason':
      return (
        <div className="wwt-sub">
          <label className="pk-label" htmlFor={`${name}-why`}>Why? (optional)</label>
          <input id={`${name}-why`} className="wwt-input" type="text" maxLength={80}
                 placeholder="My sister’s" value={s.reason || ''}
                 onChange={(e) => set({ reason: e.target.value })} />
        </div>
      );
    case 'income_kind':
      return (
        <div className="wwt-sub pk-choices" role="radiogroup" aria-label="What kind of income?">
          {Object.entries(data.income_kinds).map(([k, label]) => (
            <Choice key={k} name={`${name}-k`} checked={s.income_kind === k}
                    onChange={() => set({ income_kind: k })} label={label} />
          ))}
        </div>
      );
    case 'candidates':
      if (!c.candidates?.length) {
        return (
          <p className="pk-muted wwt-sub">
            {c.key === 'payback' ? 'Pearl can’t see a charge this pays back. Split the charge first, from its own page.'
              : 'Pearl can’t see an expense this reimburses. Mark the expense first, from its own page.'}
          </p>
        );
      }
      return (
        <div className="wwt-sub pk-choices" role="radiogroup" aria-label="Which charge?">
          {c.candidates.map((cand) => {
            const key = `${cand.id}|${cand.person || ''}`;
            return (
              <Candidate key={key} name={`${name}-cand`} c={cand}
                         checked={s.charge === cand.id && (s.person || '') === (cand.person || '')}
                         onChange={() => set({ charge: cand.id, person: cand.person || '' })}
                         what={c.key === 'payback' ? 'For' : 'Reimburses'} />
            );
          })}
        </div>
      );
    case 'refund':
      return (
        <div className="wwt-sub">
          {c.candidates?.length > 0 && (
            <div className="pk-choices" role="radiogroup" aria-label="Which purchase?">
              {c.candidates.map((cand) => (
                <Candidate key={cand.id} name={`${name}-cand`} c={cand} checked={s.charge === cand.id}
                           onChange={() => set({ charge: cand.id, category: '' })} what="Refund of" />
              ))}
              <Choice name={`${name}-cand`} checked={!s.charge && s.other}
                      onChange={() => set({ charge: '', other: true })} label="Something else"
                      description="Pick the category it comes off." />
            </div>
          )}
          {(!c.candidates?.length || (!s.charge && s.other)) && (
            <>
              <p className="pk-label">What does it come off?</p>
              <CategoryChips groups={spending} value={s.category} onChange={(v) => set({ category: v })}
                             label="What does it come off?" />
            </>
          )}
        </div>
      );
    case 'person':
      if (!data.joint_people?.length) return null;
      return (
        <div className="wwt-sub pk-choices" role="radiogroup" aria-label="Who?">
          {data.joint_people.map((p) => (
            <Choice key={p} name={`${name}-p`} checked={s.person === p}
                    onChange={() => set({ person: p })} label={p} />
          ))}
        </div>
      );
    case 'split':
      return (
        <p className="pk-muted wwt-sub">Say who it was with and what their parts were.</p>
      );
    default:
      return null;
  }
}

/**
 * The sheet. `tx` is the row as the list describes it (id, merchant, amount,
 * inflow, date). `onDone(res)` gets the server's answer; `onSplit` opens the
 * split step for "Paid for a group".
 */
export default function WhatWasThis({ tx, categories = [], busy = false, onDone, onSplit,
                                      onError, saveLabel = 'Save', showHead = false,
                                      initial = null }) {
  const [data, setData] = useState(initial);
  const [error, setError] = useState(null);
  const [key, setKey] = useState(startCase(initial));
  const [state, setState] = useState({});
  const [line, setLine] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (initial) return undefined;
    let live = true;
    getTxCases(tx.id).then((d) => {
      if (!live) return;
      setData(d);
      setKey(startCase(d));
      // The row's own category starts selected, so "A purchase · now" with
      // the remember line saves without picking it again.
      setState({ account: d.saved_to || '', income_kind: d.income_kind || '',
                 category: d.categories.includes(tx.category) ? tx.category : '' });
    }).catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, [tx.id, initial]);

  const spending = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const others = spending;
  const current = data?.cases.find((c) => c.key === key);
  const set = (patch) => setState((s) => ({ ...s, ...patch }));
  const ok = ready(current, state);

  // The line underneath: what it would do, from the server, before Save.
  useEffect(() => {
    if (!current || current.needs === 'split') { setLine(''); return undefined; }
    if (!ok) { setLine(current.effect); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      markTx(tx.id, bodyFor(current, state), true)
        .then((r) => { if (live) setLine(r.line || current.effect); })
        .catch(() => { if (live) setLine(current.effect); });
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [tx.id, key, JSON.stringify(state), ok]);

  const save = async () => {
    if (!current) return;
    if (current.needs === 'split') { onSplit?.(); return; }
    setSaving(true);
    setError(null);
    try {
      const res = await markTx(tx.id, bodyFor(current, state));
      onDone?.(res, current);
    } catch (e) {
      setError(e);
      onError?.(e);
    } finally {
      setSaving(false);
    }
  };

  if (error && !data) return <p className="txd-error" role="alert">{error.message}</p>;
  if (!data) return <p className="pk-muted">Loading…</p>;
  const inflow = data.direction === 'in';
  return (
    <div className="wwt">
      {showHead && (
        <div className="nl-tx">
          <Avatar name={tx.merchant} logo={tx.logo} />
          <div className="nl-tx-text">
            <span>{tx.merchant}</span>
            {tx.account && <span className="pk-label pk-muted">{tx.account}</span>}
          </div>
          <span className={`pk-h2 nl-tx-amt ${inflow ? 'in' : 'out'}`}>
            {txAmount(tx.amount, { inflow, signed: true })}
          </span>
        </div>
      )}
      {error && <p className="txd-error" role="alert">{error.message}</p>}
      <div className="pk-choices wwt-cases" role="radiogroup" aria-label="What was this?">
        {data.cases.map((c) => {
          const on = key === c.key;
          return (
            <div key={c.key} className={`wwt-case${on ? ' on' : ''}`}>
              <Choice name={`wwt-${data.id}`} checked={on} onChange={() => { setKey(c.key); }}
                      label={c.label + (data.current === c.key ? ' · now' : '')}
                      description={on ? undefined : c.effect} />
              {on && (
                <>
                  <Needs c={c} data={data} s={state} set={set} spending={spending} others={others} />
                  {c.remember && (
                    <Choice type="checkbox" checked={!!state.remember}
                            onChange={(v) => set({ remember: v })} label={c.remember_label}
                            description="A rule you can see and undo in Categories and rules." />
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
      <ImpactNote>{line}</ImpactNote>
      <PButton className="txd-save" disabled={busy || saving || !ok}
               onClick={save}>
        {current?.needs === 'split' ? 'Split this' : saveLabel}
      </PButton>
    </div>
  );
}

/** A small tag editor: type a tag, Enter adds it; × takes one off. */
export function TagEditor({ tags, known = [], onChange, label = 'Tags' }) {
  const [text, setText] = useState('');
  const add = (t) => {
    const tag = t.trim().replace(/\s+/g, ' ').slice(0, 30);
    if (!tag || tags.some((x) => x.toLowerCase() === tag.toLowerCase())) { setText(''); return; }
    onChange([...tags, tag]);
    setText('');
  };
  const suggestions = known.filter((k) => !tags.some((x) => x.toLowerCase() === k.toLowerCase())
    && (!text || k.toLowerCase().includes(text.toLowerCase()))).slice(0, 6);
  return (
    <div className="wwt-tags">
      <div className="wwt-tag-list" aria-label={label}>
        {tags.map((t) => (
          <span key={t} className="pk-tag editable">
            {t}
            <button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(tags.filter((x) => x !== t))}>
              <PIcon name="x" size={12} />
            </button>
          </span>
        ))}
      </div>
      <input className="wwt-input" type="text" value={text} maxLength={30} placeholder="Add a tag, like Ibiza"
             aria-label="Add a tag" onChange={(e) => setText(e.target.value)}
             onKeyDown={(e) => {
               if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(text); }
             }} />
      {suggestions.length > 0 && (
        <div className="pk-opts">
          {suggestions.map((k) => (
            <button key={k} type="button" className="pk-opt" onClick={() => add(k)}>{k}</button>
          ))}
        </div>
      )}
    </div>
  );
}
