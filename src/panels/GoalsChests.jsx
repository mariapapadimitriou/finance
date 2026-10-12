import { useCallback, useEffect, useState } from 'react';
import { Alert, CategoryChip, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import {
  addBank, addToChest, deleteBank, getChest, openTreasure, seenCatchUp, updateBank,
} from '../api.js';
import { ErrorNote } from '../components/ui.jsx';
import { ProgressBar } from '../pearl/viz.jsx';
import {
  Field, Line, Mark, More, PageHead, Pill, Segments, amount, dayLong, dayShort,
  monthName, monthShortYear, monthYear, parseAmount, useFocusHeading,
} from './GoalsParts.jsx';

/**
 * Treasure chests (THL-169, THL-179): money set aside for something planned.
 * They are the piggy banks under another name, with the same arithmetic: a
 * monthly amount out of safe to spend, and purchases paid from the chest
 * instead of the month. A chest that paid out early catches up by raising its
 * own monthly amount. Chests never move the phase, so they carry no shell.
 */

const ym = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
const idx = (m) => Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - 1;

/** What a chest would ask a month, as the engine works it out at the start. */
function monthlyFor(target, cadence, month) {
  if (!(target > 0)) return null;
  if (cadence === 'annual') return target / 12;
  if (!month) return null;
  return target / Math.max(idx(month) - idx(ym()) + 1, 1);
}

/** The category a chest most likely pays for, from its name. */
function guessCategory(name, categories) {
  const words = (name || '').toLowerCase();
  if (/\b(trip|travel|flights?|vacation)\b/.test(words) && categories.includes('Travel')) return 'Travel';
  for (const c of categories) {
    for (const w of c.toLowerCase().match(/[a-z]+/g) ?? []) {
      const stem = w.replace(/s$/, '');
      if (stem.length >= 4 && words.includes(stem)) return c;
    }
  }
  return null;
}

/** The far end of a chest card's label row. */
function readyLabel(chest) {
  if (chest.ready) return '100%';
  if (chest.cadence === 'once' && chest.target_date) return monthShortYear(chest.target_date.slice(0, 7));
  return monthShortYear(chest.ready_by);
}

export function ChestCard({ chest, onOpen, onTreasure }) {
  return (
    <article className="gl-card gl-chest">
      <div className="gl-chest-top">
        <h3 className="pk-h3">
          <button type="button" className="gl-chest-link" onClick={onOpen}>{chest.name}</button>
        </h3>
        {chest.catching_up && <Pill>Catching up</Pill>}
      </div>
      <p className="gl-amount sm">
        <span className="pk-h2">{amount(chest.held)}</span>
        <span className="pk-label pk-muted">of {amount(chest.target)}</span>
      </p>
      {chest.ready ? (
        <ProgressBar label="Ready to open" value="100%" share={1} tone="positive" name={chest.name} />
      ) : (
        <ProgressBar label={`${amount(chest.monthly)} a month`} value={readyLabel(chest)}
                  share={chest.share} name={chest.name} />
      )}
      {chest.ready && <More className="gl-above" onClick={onTreasure}>Open your treasure</More>}
    </article>
  );
}

/** The chests on the overview, or how to start one. */
export function ChestsSection({ goals, onNew, onOpen, onTreasure }) {
  const suggestion = goals.chest_suggestion;
  return (
    <section className="gl-section" aria-labelledby="chests-title">
      <div className="gl-section-head">
        <div className="gl-stack tight">
          <h2 className="pk-h3" id="chests-title">Treasure chests</h2>
          <p className="pk-label pk-muted">Money set aside for things you’ve planned</p>
        </div>
        <PButton variant="secondary" className="gl-hug" onClick={() => onNew()}>Open a chest</PButton>
      </div>
      {goals.chests.length > 0 ? (
        <div className="gl-chests">
          {goals.chests.map((c) => (
            <ChestCard key={c.id} chest={c} onOpen={() => onOpen(c.id)}
                       onTreasure={() => onTreasure(c.id)} />
          ))}
        </div>
      ) : (
        <div className="gl-card">
          <h3 className="pk-h2">No treasure chests yet</h3>
          <p className="gl-body">Set money aside for something you’ve planned, like a trip, gifts
            or car insurance. A little comes out of your safe-to-spend each month.</p>
          {suggestion?.annual_spend >= 240 && (
            <Alert action="Start" onAction={() => onNew({
              name: 'Travel', target: suggestion.target, cadence: 'annual',
              categories: suggestion.categories,
            })}>
              You spent {amount(Math.round(suggestion.annual_spend))} on travel last year. Start a
              travel chest?
            </Alert>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * G-03 and G-04: open a chest (or change its plan), and then, when there is
 * no Anchor yet, a gentle note that never blocks. It shows every time a chest
 * is opened until there is one; "Not now" only closes it for that time.
 */
export function ChestForm({ goals, chest, preset, onClose, onSaved, onStartAnchor }) {
  const categories = goals.spend_categories ?? [];
  const editing = !!chest;
  const [name, setName] = useState(chest?.name ?? preset?.name ?? '');
  const [target, setTarget] = useState(
    chest ? String(chest.target) : preset?.target ? String(preset.target) : '');
  const [cadence, setCadence] = useState(chest?.cadence ?? preset?.cadence ?? 'once');
  const [month, setMonth] = useState(chest?.target_date?.slice(0, 7) ?? '');
  const owned = chest?.categories ?? preset?.categories ?? [];
  const guess = owned[0] ?? guessCategory(name, categories);
  const [payFrom, setPayFrom] = useState(editing ? owned.length > 0 : true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [opened, setOpened] = useState(null);
  const [nudge, setNudge] = useState(true);
  const [closing, setClosing] = useState(false);
  const heading = useFocusHeading(opened ? 'opened' : 'form');

  const value = parseAmount(target);
  const monthly = monthlyFor(value, cadence, month);
  const safe = goals.safe_to_spend;
  // Another chest may already pay for the guessed category.
  const takenBy = guess && (goals.bank_funded ?? []).includes(guess) && !owned.includes(guess);

  const submit = async () => {
    setError('');
    if (!name.trim()) { setError('Give the chest a name.'); return; }
    if (!(value > 0)) { setError('Enter how much it needs.'); return; }
    if (cadence === 'once' && !month) { setError('Pick the month you need it by.'); return; }
    const body = {
      name: name.trim(), target: value, cadence,
      target_date: cadence === 'once' ? `${month}-01` : null,
    };
    if (guess && !takenBy) {
      body.categories = payFrom ? [...new Set([...owned, guess])] : owned.filter((c) => c !== guess);
    }
    setBusy(true);
    try {
      if (editing) {
        await updateBank(chest.id, body);
        onSaved();
        onClose();
      } else {
        await addBank(body);
        onSaved();
        setOpened({ name: body.name, monthly, category: body.categories?.includes(guess) ? guess : null });
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (opened) {
    return (
      <DetailPanel label={`Your ${opened.name} chest is open`} overline="Treasure chest"
                   onClose={onClose} className="on-card">
        <h1 className="pk-h1" tabIndex={-1} ref={heading}>Your {opened.name} chest is open</h1>
        <p className="gl-body">
          {opened.monthly ? `${amount(Math.round(opened.monthly * 100) / 100)} a month, starting this month.` : ''}
          {opened.category ? ` ${opened.category} purchases will come out of it.` : ''}
        </p>
        {!goals.anchor.started && nudge && (
          <div className="gl-nudge">
            <div className="gl-nudge-head">
              <Mark phase="build" width={48} />
              <h2 className="pk-h3">Want to start your Anchor alongside it?</h2>
            </div>
            <p className="gl-text pk-muted">A small cushion for surprises keeps plans like this
              one safe.</p>
            <div className="gl-actions">
              <PButton variant="secondary" className="gl-hug" onClick={onStartAnchor}>
                Start my Anchor
              </PButton>
              <PButton variant="text" className="gl-text-btn" onClick={() => setNudge(false)}>
                Not now
              </PButton>
            </div>
          </div>
        )}
        <div className="gl-panel-foot">
          <PButton onClick={onClose}>Done</PButton>
        </div>
      </DetailPanel>
    );
  }

  return (
    <DetailPanel label={editing ? 'Change plan' : 'Open a chest'} overline="Treasure chest"
                 onClose={onClose} className="on-card gl-form">
      <h1 className="pk-h1" tabIndex={-1} ref={heading}>{editing ? 'Change plan' : 'Open a chest'}</h1>
      <Field label="Name" id="chest-name">
        <input id="chest-name" value={name} maxLength={40} placeholder="Japan trip"
               onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="How much?" id="chest-target">
        <input id="chest-target" inputMode="decimal" value={target} placeholder="$3,000"
               onChange={(e) => setTarget(e.target.value)} />
      </Field>
      <Segments label="When" value={cadence} onChange={setCadence}
                options={[{ value: 'once', label: 'By a date' }, { value: 'annual', label: 'Every year' }]} />
      {cadence === 'once' && (
        <Field label="Date" id="chest-date">
          <input id="chest-date" type="month" value={month} min={ym()}
                 onChange={(e) => setMonth(e.target.value)} />
        </Field>
      )}
      {monthly != null && (
        <div className="gl-note-card tight" role="status" aria-live="polite">
          <h2 className="pk-h3">{amount(Math.round(monthly * 100) / 100)} a month</h2>
          <p className="pk-label pk-muted">
            Set aside from your safe-to-spend
            {safe != null && !editing
              ? `. This month: ${amount(safe)} → ${amount(Math.round((safe - monthly) * 100) / 100)}.`
              : cadence === 'annual' ? ', every month of the year.' : ' until the date.'}
          </p>
        </div>
      )}
      {guess && !takenBy && (
        <Choice type="checkbox" checked={payFrom} onChange={setPayFrom}
                label={`Pay ${guess} purchases from this chest`}
                description={`Card purchases in ${guess} come out of the chest`} />
      )}
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        <PButton disabled={busy} onClick={submit}>
          {busy ? 'Saving…' : editing ? 'Save' : 'Open chest'}
        </PButton>
        {editing && !closing && (
          <PButton variant="text" className="gl-text-btn center" onClick={() => setClosing(true)}>
            Close this chest
          </PButton>
        )}
        {editing && closing && (
          <div className="gl-confirm">
            <p className="pk-label">Close {chest.name}? Anything it paid for goes back into the
              month it was spent.</p>
            <div className="gl-actions">
              <PButton variant="secondary" className="gl-hug" disabled={busy}
                       onClick={async () => {
                         setBusy(true);
                         try { await deleteBank(chest.id); onSaved({ closed: true }); onClose(); }
                         catch (e) { setError(e.message); setBusy(false); }
                       }}>Close chest</PButton>
              <PButton variant="text" className="gl-text-btn" onClick={() => setClosing(false)}>
                Keep it
              </PButton>
            </div>
          </div>
        )}
      </div>
    </DetailPanel>
  );
}

/** G-06: open your treasure — pay purchases from the chest, not the month. */
export function Treasure({ detail, onClose, onDone }) {
  const { chest, candidates, suggested_category: suggested } = detail;
  const offerCategory = suggested && !chest.categories.includes(suggested);
  const [category, setCategory] = useState(!!offerCategory);
  const [picked, setPicked] = useState(() => new Set(
    candidates.filter((c) => c.suggested).map((c) => c.id)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const paying = candidates.filter((c) => picked.has(c.id)).reduce((s, c) => s + c.amount, 0);
  const left = chest.held - paying;
  const nothing = picked.size === 0 && !category;
  return (
    <DetailPanel label="Open your treasure" overline={`${chest.name} · ${amount(chest.held)}`}
                 onClose={onClose} className="on-card gl-form">
      <h1 className="pk-h1">Open your treasure</h1>
      <p className="gl-body">Pick what to pay from this chest. It comes out of the chest, not
        your month.</p>
      <div className="pk-choices">
        {offerCategory && (
          <Choice type="checkbox" checked={category} onChange={setCategory}
                  label={`${suggested}, from now on`}
                  description={`Every purchase sorted as ${suggested}`} />
        )}
        {candidates.map((c) => (
          <Choice key={c.id} type="checkbox" checked={picked.has(c.id)}
                  label={`${c.merchant} · ${dayShort(c.date)}`}
                  description={amount(c.amount)}
                  onChange={(on) => setPicked((s) => {
                    const next = new Set(s);
                    if (on) next.add(c.id); else next.delete(c.id);
                    return next;
                  })} />
        ))}
      </div>
      {candidates.length === 0 && !offerCategory && (
        <p className="gl-body">No recent purchases to pay from it. New ones in its categories
          come out of it on their own.</p>
      )}
      {paying > 0 && (
        <div className="gl-note-card tight" role="status" aria-live="polite">
          <Line strong label="Paying from the chest" value={amount(Math.round(paying * 100) / 100)} />
          <Line label="Left in the chest" value={amount(Math.max(Math.round(left * 100) / 100, 0))} />
          <p className="pk-label pk-muted">
            Safe to spend goes up by {amount(Math.round(paying * 100) / 100)}.
            {left < 0 ? ' That’s more than it holds, so it catches up over the coming months.' : ''}
          </p>
        </div>
      )}
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        <PButton disabled={busy || nothing} onClick={async () => {
          setBusy(true); setError('');
          try {
            await openTreasure(chest.id, [...picked], category ? [suggested] : []);
            onDone(); onClose();
          } catch (e) { setError(e.message); setBusy(false); }
        }}>{busy ? 'Opening…' : 'Open your treasure'}</PButton>
      </div>
    </DetailPanel>
  );
}

/** Add money to a chest now, out of this month's safe to spend. */
export function AddMoney({ detail, onClose, onDone }) {
  const { chest, safe_to_spend: safe } = detail;
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const value = parseAmount(text);
  return (
    <DetailPanel label="Add money" overline={chest.name} onClose={onClose} className="on-card">
      <h1 className="pk-h1">Add money</h1>
      <p className="gl-body">Put more in now and it’s ready sooner.</p>
      <Field label="How much?" id="chest-add">
        <input id="chest-add" inputMode="decimal" value={text} placeholder="$100"
               onChange={(e) => setText(e.target.value)} />
      </Field>
      {value > 0 && (
        <Alert>
          It comes out of this month’s safe to spend
          {safe != null ? `: ${amount(safe)} → ${amount(Math.round((safe - value) * 100) / 100)}.` : '.'}
        </Alert>
      )}
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        <PButton disabled={busy || !(value > 0)} onClick={async () => {
          setBusy(true); setError('');
          try { await addToChest(chest.id, value); onDone(); onClose(); }
          catch (e) { setError(e.message); setBusy(false); }
        }}>{busy ? 'Adding…' : 'Add to chest'}</PButton>
      </div>
    </DetailPanel>
  );
}

const RECENT_WORDS = { set_aside: 'Set aside', paid: 'Paid from the chest', added: 'Added' };

/** "Ready by Sep 2027", or, catching up, "Until February, then $100". */
function detailRight(chest) {
  if (chest.catching_up && chest.caught_up_by) {
    return `Until ${monthName(chest.caught_up_by)}, then ${amount(chest.base_monthly)}`;
  }
  return `Ready by ${monthShortYear(chest.cadence === 'once' && chest.target_date
    ? chest.target_date.slice(0, 7) : chest.ready_by)}`;
}

/** G-05 and G-08: one chest. */
export function ChestDetail({ goals, id, onBack, onChanged, version }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [panel, setPanel] = useState(null);       // treasure | add | plan

  const load = useCallback(() => {
    setError(null);
    return getChest(id).then(setDetail).catch(setError);
  }, [id]);
  useEffect(() => { load(); }, [load, version]);

  if (error) return <ErrorNote error={error} onRetry={load} />;
  if (!detail) return <p className="pk-muted" role="status">Opening the chest…</p>;

  const { chest } = detail;
  const changed = async (opts) => {
    await onChanged();
    if (opts?.closed) { onBack(); return; }
    await load();
  };
  const behind = chest.catching_up && !detail.catch_up_seen;
  const extra = Math.round((chest.monthly - chest.base_monthly) * 100) / 100;
  return (
    <>
      <PageHead overline="Goals · Treasure chest" title={chest.name} onBack={onBack}
                backLabel="Back to Goals" />

      <section className="gl-card" aria-label="Progress">
        <p className="gl-amount">
          <span className="pk-amount">{amount(chest.held)}</span>
          <span className="pk-muted">
            of {amount(chest.target)}
            {chest.ready ? ' · ready' : chest.cadence === 'once' && chest.target_date
              ? ` · due ${dayLong(chest.target_date)}` : ` · ${amount(chest.to_go)} to go`}
          </span>
        </p>
        <ProgressBar label={chest.ready ? 'Ready to open' : `${amount(chest.monthly)} a month`}
                  value={chest.ready ? '100%' : detailRight(chest)}
                  share={chest.share} tone={chest.ready ? 'positive' : 'brand'} name={chest.name} />
        <div className="gl-actions">
          <PButton className="gl-hug" onClick={() => setPanel('treasure')}>Open your treasure</PButton>
          <PButton variant="secondary" className="gl-hug" onClick={() => setPanel('add')}>Add money</PButton>
          <PButton variant="secondary" className="gl-hug" onClick={() => setPanel('plan')}>Change plan</PButton>
        </div>
      </section>

      {behind && (
        <section className="gl-card gl-behind" aria-label="Catching up">
          <p className="pk-overline accent">Catching up</p>
          <h2 className="pk-h2">
            We’ve raised it to {amount(chest.monthly)} a month, so it’s
            {chest.cadence === 'once' && chest.target_date
              ? ` ready by ${dayLong(chest.target_date)}`
              : ` back on track by ${monthYear(chest.caught_up_by)}`}
          </h2>
          <p className="gl-body">
            {detail.last_paid ? `A purchase in ${monthName(detail.last_paid)} came out of this chest early. ` : ''}
            To catch up, {amount(extra)} more a month comes out of your safe-to-spend
            {chest.caught_up_by ? ` until ${monthName(chest.caught_up_by)}` : ''}.
          </p>
          <div className="gl-actions">
            <PButton className="gl-hug" onClick={async () => {
              await seenCatchUp(chest.id, chest.monthly);
              load();
            }}>Got it</PButton>
            {chest.cadence === 'once' && (
              <PButton variant="secondary" className="gl-hug" onClick={() => setPanel('plan')}>
                Move the date instead
              </PButton>
            )}
          </div>
        </section>
      )}

      <div className="gl-cols">
        <section className="gl-card" aria-label="Paid from this chest">
          <h2 className="pk-h3">Paid from this chest</h2>
          {chest.categories.length > 0 ? (
            <>
              <div className="gl-chips">
                {chest.categories.map((c) => <CategoryChip key={c} label={c} />)}
              </div>
              <p className="pk-label pk-muted">
                Card purchases in {chest.categories.join(', ')} come out of this chest, not your month.
              </p>
            </>
          ) : (
            <p className="pk-label pk-muted">Nothing is paid from it on its own yet. Use Open your
              treasure to pay purchases from it.</p>
          )}
          <More onClick={() => setPanel('plan')}>Change</More>
        </section>
        <section className="gl-card" aria-label="Recent">
          <h2 className="pk-h3">Recent</h2>
          {detail.recent.length > 0 ? detail.recent.map((r) => (
            <Line key={`${r.kind}${r.date}${r.amount}`}
                  label={`${dayShort(r.date)} · ${r.kind === 'paid' && r.merchant ? r.merchant
                    : RECENT_WORDS[r.kind]}`}
                  value={amount(r.amount)} />
          )) : <p className="pk-label pk-muted">Nothing yet.</p>}
        </section>
      </div>

      {panel === 'treasure' && (
        <Treasure detail={detail} onClose={() => setPanel(null)} onDone={changed} />
      )}
      {panel === 'add' && (
        <AddMoney detail={detail} onClose={() => setPanel(null)} onDone={changed} />
      )}
      {panel === 'plan' && (
        <ChestForm goals={{ ...goals, spend_categories: detail.spend_categories,
                            bank_funded: detail.bank_funded }}
                   chest={chest} onClose={() => setPanel(null)} onSaved={changed} />
      )}
    </>
  );
}
