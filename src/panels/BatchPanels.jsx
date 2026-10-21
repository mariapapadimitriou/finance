import { useEffect, useMemo, useState } from 'react';
import { Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { DEFAULT_CASES, DONE, Done, Pill, Progress, nextOf } from './SortCard.jsx';
import { batchMark, batchTags, getTags, money } from '../api.js';

/**
 * A selection, answered at once (2026-10-21): the same list and the same
 * card as sorting one transaction (SortCard.jsx), minus the cases that need
 * something per row (who it was with, which purchase, how much). Tapping
 * the last answer saves it for all of them: one toast, one Undo, never a
 * merchant rule. "Tag" tags them with her tags.
 */

/** The cases a selection can take: the server's list, less the per-row ones. */
export const BATCH_CASES = DEFAULT_CASES.out.filter((c) => [null, 'category', 'reason', 'borrowed', 'account'].includes(c.needs));

export function BatchMarkPanel({ ids, categories = [], onDone, onClose }) {
  // The answers so far: [{ step, v, label }], the open question after them.
  const [path, setPath] = useState([]);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const groups = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const n = ids.length;
  const flow = useMemo(() => {
    const S = {
      all: {
        title: 'What were these?', left: 2,
        options: BATCH_CASES.map((c) => ({ v: c.key, label: c.label, done: DONE[c.key] ?? c.label, effect: c.effect,
                                           to: c.needs === 'category' ? 'cat' : c.needs === 'borrowed' ? 'borrowed' : undefined })),
      },
      cat: { title: 'What were they for?', left: 1, ask: 'category' },
      borrowed: { title: 'What you bought with it', left: 1, options: [
        { v: 'counted', label: 'What I bought with it is already in Pearl', done: 'Already in Pearl' },
        { v: 'not_counted', label: 'What I bought with it isn’t in Pearl', done: 'Not in Pearl yet', to: 'cat' },
      ] },
    };
    return { start: 'all', S };
  }, []);
  const stepId = path.length ? nextOf(flow, path[path.length - 1]) : flow.start;
  const step = flow.S[stepId];
  const total = path.length + (step?.left ?? 1);

  const save = async (answers) => {
    setBusy(true);
    setError(null);
    try {
      const body = { case: answers[0].v };
      const cat = answers.find((p) => p.step === 'cat');
      if (cat) body.category = cat.v;
      const counted = answers.find((p) => p.step === 'borrowed');
      if (counted) body.counted = counted.v === 'counted';
      if (body.case === 'not_mine') body.reason = '';
      if (body.case === 'saved') body.account = '';          // no one account for a selection
      onDone(await batchMark(ids, body));
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };
  const choose = (sId, v, before) => {
    const opt = flow.S[sId].options.find((o) => o.v === v);
    const answers = [...before, { step: sId, v }];
    if (opt?.to) setPath(answers); else save(answers);
  };
  const rechoose = (i, v) => {
    const sId = path[i].step;
    const s = flow.S[sId];
    const was = s.options.find((o) => o.v === path[i].v);
    const now = s.options.find((o) => o.v === v);
    setEditing(null);
    if (!now.to) { choose(sId, v, path.slice(0, i)); return; }
    if (now.to === was?.to) setPath(path.map((p, k) => (k === i ? { step: p.step, v } : p)));
    else setPath([...path.slice(0, i), { step: sId, v }]);
  };
  const undoLast = () => {
    if (editing !== null) { setEditing(null); return; }
    if (path.length) { setPath(path.slice(0, -1)); return; }
    onClose?.();
  };

  return (
    <DetailPanel label={`Mark ${n} transaction${n === 1 ? '' : 's'} as`} overline="Selection"
                 onClose={onClose}>
      <p className="pk-muted">The same answer for all {n}. Nothing becomes a rule.</p>
      {error && <p className="txd-error" role="alert">{error.message}</p>}
      <section className="nl-card nl-stack txd-sort" aria-label="What were these?">
        <Progress done={path.length} total={total}
                  trailing={(
                    <Pill className="nl-undo" onClick={undoLast} disabled={busy}
                          aria-label={path.length || editing !== null ? 'Undo the last answer' : 'Back to the list'}>
                      Undo
                    </Pill>
                  )} />
        <Done path={path} flow={flow} editing={editing} busy={busy}
              onOpen={(i) => setEditing(editing === i ? null : i)} onPick={rechoose} />
        {step && (
          <>
            <h2 className="pk-h2 nl-q">{step.title}</h2>
            {step.options && (
              <div className="pk-choices" role="radiogroup" aria-label={step.title}>
                {step.options.map((o) => (
                  <Choice key={o.v} name={`batch-${stepId}`} checked={false} disabled={busy}
                          onChange={() => choose(stepId, o.v, path)} label={o.label} description={o.effect} />
                ))}
              </div>
            )}
            {step.ask === 'category' && (
              <CategoryChips groups={groups} value="" label={step.title}
                             onChange={(v) => save([...path, { step: stepId, v, label: categoryLabel(v) }])} />
            )}
          </>
        )}
      </section>
    </DetailPanel>
  );
}

export function BatchTagPanel({ ids, onDone, onClose }) {
  const [picked, setPicked] = useState([]);
  const [text, setText] = useState('');
  const [known, setKnown] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    let live = true;
    getTags().then((d) => { if (live) setKnown(d.tags ?? []); }).catch(() => {});
    return () => { live = false; };
  }, []);
  const n = ids.length;
  const fresh = text.trim().replace(/\s+/g, ' ').slice(0, 30);
  const tags = [...picked, ...(fresh && !picked.some((p) => p.toLowerCase() === fresh.toLowerCase()) ? [fresh] : [])];
  const toggle = (tag, on) => setPicked((p) => (on ? [...p, tag] : p.filter((x) => x !== tag)));
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await batchTags(ids, tags, []));
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };
  return (
    <DetailPanel label={`Tag ${n} transaction${n === 1 ? '' : 's'}`} overline="Tag" onClose={onClose}>
      <h2 className="pk-h2">{`Tag ${n} transaction${n === 1 ? '' : 's'}`}</h2>
      <p className="pk-muted">Tags group anything you like, across categories and months. Filter by
        a tag to see its total.</p>
      {error && <p className="txd-error" role="alert">{error.message}</p>}
      {known.length > 0 && (
        <div className="txd-field">
          <p className="pk-label">Your tags</p>
          <div className="pk-choices">
            {known.map((t) => (
              <Choice key={t.tag} type="checkbox" checked={picked.includes(t.tag)}
                      onChange={(on) => toggle(t.tag, on)} label={t.tag}
                      description={`${t.count} transaction${t.count === 1 ? '' : 's'} · ${money(t.spent, { cents: true })}`} />
            ))}
          </div>
        </div>
      )}
      <div className="txd-field">
        <label className="pk-label" htmlFor="bt-new">New tag</label>
        <input id="bt-new" className="wwt-input" type="text" maxLength={30} value={text}
               autoComplete="off" onChange={(e) => setText(e.target.value)} />
      </div>
      <div className="txd-actions">
        <PButton disabled={busy || !tags.length} onClick={save}>{busy ? 'Saving…' : 'Tag them'}</PButton>
        <PButton variant="secondary" onClick={onClose}>Cancel</PButton>
      </div>
    </DetailPanel>
  );
}
