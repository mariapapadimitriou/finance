import { useEffect, useMemo, useState } from 'react';
import { Choice, PButton, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, groupCategories } from './CategoryPicker.jsx';
import { getTxCases, markTx } from '../api.js';

/**
 * What was this? (WW-02 to WW-05, THL-231; finance/marks.py). One question,
 * one list of answers, the same from the transactions list, the detail
 * panel and Needs a look.
 *
 * Step 1 (WW-02, WW-04): the transaction, then the cases as cards — Pearl's
 * best guess on top, then grouped by what they do (Spending · Not spending ·
 * Not mine to count; Income · Or it isn't income), each with a one-line
 * effect. Step 2 (WW-03, WW-05) shows only what the case needs (which
 * savings account, which purchase, a category, a kind of income), the
 * effect on her real numbers in a "What this does" box, and "Do this for
 * every … from now on", which becomes a rule in Categories and rules.
 * Save closes with what it did and Undo, like a change of category.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const shortDate = (iso) => `${SHORT[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;
function longDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${WEEKDAYS[new Date(y, m - 1, d).getDay()]}, ${MONTHS[m - 1]} ${d}`;
}

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

/** The cases in their groups, Pearl's best guess first (WW-02). */
export function groupedCases(data) {
  if (!data) return [];
  const best = data.cases.find((c) => c.key === data.best);
  const out = [];
  if (best) out.push({ key: 'best', label: 'Pearl’s best guess', cases: [best] });
  for (const g of data.groups ?? []) {
    const cases = data.cases.filter((c) => c.group === g.key && c.key !== best?.key);
    if (cases.length) out.push({ key: g.key, label: g.label, cases });
  }
  return out;
}

/** "What this does", in words she can check (WW-03, WW-05). */
export function effectWords(c, s, data, line, tx) {
  const parts = [];
  if (line && line !== c.effect) parts.push(line);
  if (c.key === 'saved' || c.key === 'out_of_savings') {
    const a = (data.accounts ?? []).find((x) => x.id === s.account);
    const amt = txAmount(tx.amount);
    if (c.key === 'saved') {
      parts.push(a ? `It shows as “Put away to ${a.label}” and adds ${amt} to Savings this month${a.anchor ? ' and to your Anchor' : ''}.`
        : `It shows as “Put away” and adds ${amt} to Savings this month.`);
    } else {
      parts.push(a ? `It shows as “Taken out of ${a.label}” and comes off Savings this month.`
        : `It shows as “Taken out of savings” and comes off Savings this month.`);
    }
  } else if (c.key === 'refund') {
    const cand = (c.candidates ?? []).find((x) => x.id === s.charge);
    const cat = cand?.category || s.category;
    if (cat) {
      const when = cand ? ` in ${MONTHS[Number(cand.date.slice(5, 7)) - 1]}` : '';
      parts.push(`The refund comes off ${cat}${when}. It isn’t income.`);
    }
  } else if (!parts.length) {
    parts.push(c.effect);
  }
  return parts.join(' ');
}

function Candidate({ name, checked, onChange, c, what }) {
  const bits = [txAmount(c.amount, { signed: true }), c.category].filter(Boolean);
  if (c.person) bits.push(`${c.person}’s share`);
  else if (c.share) bits.push(`about a 1/${c.share} share`);
  if (c.work) bits.push('left out as a work expense');
  if (c.exact) bits.push('exact match');
  return (
    <Choice name={name} checked={checked} onChange={onChange}
            label={`${what ? `${what} ` : ''}${c.merchant} · ${shortDate(c.date)}`}
            description={bits.join(' · ')} />
  );
}

/** What one case asks for (step 2). */
export function CaseNeeds({ c, data, s, set, spending }) {
  const name = `wwt-${data.id}-${c.key}`;
  switch (c.needs) {
    case 'category':
      return (
        <div className="wwt-sub">
          <p className="pk-label">{c.key === 'bill' ? 'Which bill is it?' : 'What was it for?'}</p>
          <CategoryChips groups={spending} value={s.category} onChange={(v) => set({ category: v })}
                         label="What was it for?" />
        </div>
      );
    case 'account': {
      const out = data.direction === 'out';
      return (
        <div className="wwt-sub">
          <p className="pk-label">{out ? 'Which account did it go to?' : 'Which account did it come out of?'}</p>
          <div className="pk-choices" role="radiogroup" aria-label="Which account?">
            {data.accounts.map((a) => (
              <Choice key={a.id} name={`${name}-acct`} checked={s.account === a.id}
                      onChange={() => set({ account: a.id })} label={a.label} description={a.sub} />
            ))}
            <Choice name={`${name}-acct`} checked={!s.account} onChange={() => set({ account: '' })}
                    label="Somewhere Pearl can’t see"
                    description={out ? 'Still counts as put away' : 'Still comes off what you put away'} />
          </div>
          {!data.accounts.length && (
            <p className="pk-muted">Add a savings or investment account on Profile › Accounts, with
              its last four digits, and transfers to it are sorted on their own.</p>
          )}
        </div>
      );
    }
    case 'amount':
      return (
        <div className="wwt-sub">
          <label className="pk-label" htmlFor={`${name}-amt`}>How much was put away?</label>
          <input id={`${name}-amt`} className="wwt-input" type="number" inputMode="decimal" min="0.01"
                 step="0.01" value={s.amount || ''} onChange={(e) => set({ amount: e.target.value })} />
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
        <div className="wwt-sub">
          <p className="pk-label">What kind?</p>
          <div className="pk-choices" role="radiogroup" aria-label="What kind of income?">
            {Object.entries(data.income_kinds).map(([k, label]) => (
              <Choice key={k} name={`${name}-k`} checked={s.income_kind === k}
                      onChange={() => set({ income_kind: k })} label={label} />
            ))}
          </div>
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
        <div className="wwt-sub">
          <p className="pk-label">{c.key === 'payback' ? 'Which purchase is it for?' : 'Which expense does it reimburse?'}</p>
          <div className="pk-choices" role="radiogroup" aria-label="Which charge?">
            {c.candidates.map((cand) => (
              <Candidate key={`${cand.id}|${cand.person || ''}`} name={`${name}-cand`} c={cand}
                         checked={s.charge === cand.id && (s.person || '') === (cand.person || '')}
                         onChange={() => set({ charge: cand.id, person: cand.person || '' })} />
            ))}
          </div>
        </div>
      );
    case 'refund':
      return (
        <div className="wwt-sub">
          {c.candidates?.length > 0 && (
            <>
              <p className="pk-label">Which purchase is it for?</p>
              <div className="pk-choices" role="radiogroup" aria-label="Which purchase?">
                {c.candidates.map((cand) => (
                  <Candidate key={cand.id} name={`${name}-cand`} c={cand} checked={s.charge === cand.id}
                             onChange={() => set({ charge: cand.id, category: '' })} />
                ))}
                <Choice name={`${name}-cand`} checked={!s.charge && !!s.other}
                        onChange={() => set({ charge: '', other: true })} label="None of these"
                        description={tx_cat(data) ? `Keep it as a refund in ${tx_cat(data)}` : 'Pick the category it comes off'} />
              </div>
            </>
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
        <div className="wwt-sub">
          <p className="pk-label">Who?</p>
          <div className="pk-choices" role="radiogroup" aria-label="Who?">
            {data.joint_people.map((p) => (
              <Choice key={p} name={`${name}-p`} checked={s.person === p}
                      onChange={() => set({ person: p })} label={p}
                      description={`Pays for ${p}’s part of this month’s joint spending`} />
            ))}
          </div>
        </div>
      );
    case 'split':
      return <p className="pk-muted wwt-sub">Say who it was with and what their parts were.</p>;
    default:
      return null;
  }
}

const tx_cat = (data) => data?.category || '';

/** The transaction, as the sheet heads every step with it. */
export function TxCard({ tx }) {
  const inflow = !!tx.inflow;
  const when = tx.date ? longDate(tx.date) : '';
  return (
    <div className="wwt-tx">
      <div className="wwt-tx-text">
        <span>{tx.merchant}</span>
        {(when || tx.account) && (
          <span className="pk-label pk-muted">{[when, tx.account].filter(Boolean).join(' · ')}</span>
        )}
      </div>
      <span className={`pk-h2 nl-tx-amt ${inflow ? 'in' : 'out'}`}>
        {txAmount(tx.amount, { inflow, signed: true })}
      </span>
    </div>
  );
}

/**
 * The sheet. `tx` is the row as the list describes it (id, merchant, amount,
 * inflow, date, account). `onDone(res)` gets the server's answer; `onSplit`
 * opens the split step for "Paid for a group". `onTitle` lets the panel
 * around it name the step.
 */
export default function WhatWasThis({ tx, categories = [], busy = false, onDone, onSplit,
                                      onError, saveLabel = 'Save', showHead = true,
                                      initial = null, onStep }) {
  const [data, setData] = useState(initial);
  const [error, setError] = useState(null);
  const [key, setKey] = useState('');
  const [state, setState] = useState({});
  const [line, setLine] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (initial) return undefined;
    let live = true;
    getTxCases(tx.id).then((d) => {
      if (!live) return;
      setData(d);
      setState({ account: d.saved_to || '', income_kind: d.income_kind || '',
                 category: (d.categories ?? []).includes(tx.category) ? tx.category : '' });
    }).catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, [tx.id, initial]);

  const spending = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const current = data?.cases.find((c) => c.key === key);
  const set = (patch) => setState((s) => ({ ...s, ...patch }));
  const ok = ready(current, state);
  const pick = (c) => {
    if (c.needs === 'split') { onSplit?.(); return; }
    setKey(c.key);
    onStep?.(c.label);
  };
  const back = () => { setKey(''); setError(null); onStep?.(null); };

  // "What this does": the effect on her real numbers, from the server.
  useEffect(() => {
    if (!current) { setLine(''); return undefined; }
    if (!ok) { setLine(''); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      markTx(tx.id, bodyFor(current, state), true)
        .then((r) => { if (live) setLine(r.line || ''); })
        .catch(() => { if (live) setLine(''); });
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [tx.id, key, JSON.stringify(state), ok]);

  const save = async () => {
    if (!current) return;
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

  if (!current) {
    return (
      <div className="wwt">
        {showHead && <TxCard tx={tx} />}
        {error && <p className="txd-error" role="alert">{error.message}</p>}
        {groupedCases(data).map((g) => (
          <section key={g.key} className="wwt-group" aria-labelledby={`wwt-g-${data.id}-${g.key}`}>
            <p className="pk-overline" id={`wwt-g-${data.id}-${g.key}`}>{g.label}</p>
            <div className="wwt-cases">
              {g.cases.map((c) => (
                <button key={c.key} type="button"
                        className={`wwt-case${g.key === 'best' ? ' best' : ''}`}
                        onClick={() => pick(c)}>
                  <span className="wwt-case-title">{c.label}</span>
                  <span className="wwt-case-effect">{c.effect}</span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    );
  }

  const words = effectWords(current, state, data, line, tx);
  return (
    <div className="wwt">
      {showHead && <TxCard tx={tx} />}
      {error && <p className="txd-error" role="alert">{error.message}</p>}
      <CaseNeeds c={current} data={data} s={state} set={set} spending={spending} />
      {ok && words && (
        <div className="wwt-effect" role="status" aria-live="polite">
          <p className="pk-label">What this does</p>
          <p>{words}</p>
        </div>
      )}
      {current.remember && (
        <Choice type="checkbox" checked={!!state.remember} onChange={(v) => set({ remember: v })}
                label={current.remember_label}
                description="Becomes a rule in Categories and rules" />
      )}
      <div className="txd-actions wwt-actions">
        <PButton className="txd-save" disabled={busy || saving || !ok} onClick={save}>
          {saveLabel}
        </PButton>
        <PButton variant="secondary" disabled={busy || saving} onClick={back}>
          <PIcon name="arrowLeft" size={16} /> Back
        </PButton>
      </div>
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
