import { useState } from 'react';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { setAnchor } from '../api.js';
import {
  Field, Line, Mark, More, PageHead, Progress, Segments, amount, dayShort, monthName,
  parseAmount, rangeShort, rangeWords, useFocusHeading,
} from './GoalsParts.jsx';

/**
 * The Anchor (THL-131): the emergency fund, and the whole of the Build phase.
 * Starting it is Build step 1 of 2; filling it is step 2. Full hands off to
 * Unveil, which is earned once and kept after a dip.
 */

const SIZES = [
  { value: 1, label: '1 month' }, { value: 2, label: '2 months' },
  { value: 3, label: '3 months' }, { value: 0, label: 'Any amount' },
];

/** What the far end of the Anchor card's label row says about when. */
function whenShort(projection) {
  if (!projection) return '';
  if (projection.state === 'full') return 'Full';
  if (projection.state === 'range') return `Likely full ${rangeShort(projection.from, projection.to)}`;
  return 'No date yet';
}

/** The first stop's label: done, or how far there is to go. */
function firstStopLabel(a) {
  return a.first_stop_done ? `${amount(a.first_stop)} · done`
    : `${amount(a.first_stop - a.counted)} to go`;
}

/** The Anchor, pinned at the top of Goals with the phase's shell. */
export function AnchorCard({ goals, onStart, onOpen, onTab }) {
  const a = goals.anchor;
  const head = (phase, overline, title, extra) => (
    <div className="gl-anchor-head">
      <Mark phase={phase} />
      <div className="gl-stack">
        <p className="pk-overline accent">{overline}</p>
        <h2 className="pk-h2">{title}</h2>
      </div>
      {extra}
    </div>
  );

  if (!a.started && goals.phase === 'protect') {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('protect', 'Comes next · Build', 'Your Anchor')}
        <p className="gl-body">A cushion for surprises. It becomes your focus once the basics
          are covered, and you can start it any time.</p>
        <div className="gl-actions"><PButton variant="secondary" onClick={onStart}>Start early</PButton></div>
      </section>
    );
  }

  if (!a.started) {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('build', 'Build · Step 1 of 2', 'Your Anchor')}
        <p className="gl-body">A cushion for surprises, so one rough month doesn’t undo your
          plans. Pearl suggests an amount from your Essentials.</p>
        <div className="gl-actions"><PButton onClick={onStart}>Start your Anchor</PButton></div>
      </section>
    );
  }

  if (a.earned && a.full) {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('unveil', 'Unveil', 'Your Anchor is full')}
        <Progress label="Full Anchor" value={`${amount(a.counted)} of ${amount(a.target)}`}
                  share={1} done />
        <p className="gl-body">You’re in Unveil. Keep it topped up and it’ll keep you steady.</p>
        <div className="gl-actions">
          <PButton variant="secondary" onClick={() => onTab('projections')}>
            See what’s next in Growth
          </PButton>
        </div>
      </section>
    );
  }

  if (a.earned) {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('unveil', 'Unveil · Keep it going', 'Your Anchor')}
        <Progress label="Your Anchor" value={`${amount(a.counted)} of ${amount(a.target)}`}
                  share={a.share} />
        <p className="gl-body">A big month dipped into it, which is what it’s for. You’re still
          in Unveil.</p>
        <More onClick={onOpen}>Top it up when you can</More>
      </section>
    );
  }

  return (
    <section className="gl-card gl-anchor" aria-label="Your Anchor">
      {head('build', 'Build · Step 2 of 2', 'Your Anchor',
        <More className="gl-push" onClick={onOpen}>See details</More>)}
      <p className="gl-amount">
        <span className="pk-amount">{amount(a.counted)}</span>
        <span className="pk-muted">of {amount(a.target)}</span>
      </p>
      <Progress label={`First stop ${amount(a.first_stop)} · ${a.first_stop_done ? 'done'
        : `${amount(a.first_stop - a.counted)} to go`}`}
                value={whenShort(a.projection)}
                name="Your Anchor"
                share={a.first_stop_done ? a.share : a.first_stop_share} />
    </section>
  );
}

/** A-04: the Anchor's own page. */
export function AnchorDetail({ goals, onBack, onProjection, onAccounts, onExplain }) {
  const a = goals.anchor;
  const p = a.projection;
  const phase = a.earned ? 'unveil' : 'build';
  return (
    <>
      <PageHead overline="Goals" title="Your Anchor" onBack={onBack} backLabel="Back to Goals" />

      <section className="gl-card" aria-label="Progress">
        <div className="gl-anchor-head">
          <Mark phase={phase} />
          <div className="gl-stack">
            <p className="pk-overline accent">{a.earned ? 'Unveil' : 'Build · Step 2 of 2'}</p>
            <h2 className="pk-h2">{amount(a.counted)} of {amount(a.target)}</h2>
          </div>
          <More className="gl-push" onClick={onExplain}>How we worked this out</More>
        </div>
        <div className="gl-pair">
          <Progress label="First stop" value={firstStopLabel(a)}
                    share={a.first_stop_share} done={a.first_stop_done} />
          <Progress label="Full Anchor" value={a.full ? 'Full' : `${amount(a.to_go)} to go`}
                    share={a.share} done={a.full} />
        </div>
      </section>

      <section className="gl-card gl-row-card" aria-label="When you’ll get there">
        <div className="gl-stack gl-grow">
          <h2 className="pk-h3">When you’ll get there</h2>
          <p className="gl-text">
            {p?.state === 'range' ? `Likely between ${rangeWords(p.from, p.to)}`
              : p?.state === 'full' ? 'It’s full'
                : 'No date yet'}
          </p>
        </div>
        <More onClick={onProjection}>{p?.state === 'range' ? 'See the range' : 'See why'}</More>
      </section>

      <div className="gl-cols">
        <section className="gl-card" aria-label="Counting">
          <h2 className="pk-h3">Counting</h2>
          {a.counting.length > 0
            ? a.counting.map((acct) => (
                <Line key={acct.account_id} label={acct.name} value={amount(acct.balance)} />
              ))
            : <p className="gl-text pk-muted">No accounts are counting toward it yet.</p>}
          <More onClick={onAccounts}>Change accounts</More>
        </section>
        <section className="gl-card" aria-label="Recent">
          <h2 className="pk-h3">Recent</h2>
          {a.recent.length > 0
            ? a.recent.map((r) => (
                <Line key={`${r.date}${r.amount}`}
                      label={`${dayShort(r.date)} · ${r.saved ? 'Saved' : 'Took out'}`}
                      value={amount(r.amount)} />
              ))
            : <p className="gl-text pk-muted">Transfers you mark as Saved show here.</p>}
        </section>
      </div>
    </>
  );
}

/** The accounts the Anchor could count, as checkbox rows. */
function AccountChoices({ accounts, chosen, onToggle }) {
  if (!accounts.length) {
    return (
      <Alert>No savings accounts are connected yet. Connect your bank in Settings and
        they’ll show here; you can set your Anchor now.</Alert>
    );
  }
  return (
    <div className="pk-choices">
      {accounts.map((acct) => (
        <Choice key={acct.account_id} type="checkbox" checked={chosen.has(acct.account_id)}
                onChange={(on) => onToggle(acct.account_id, on)}
                label={acct.name}
                description={acct.kind === 'chequing'
                  ? `${amount(acct.balance)} · everyday spending, usually best left out`
                  : amount(acct.balance)} />
      ))}
    </div>
  );
}

function countingNote(total, firstStop) {
  if (total <= 0) return null;
  return total >= firstStop
    ? `Counting ${amount(total)} so far, already past your first stop.`
    : `Counting ${amount(total)} so far. ${amount(firstStop - total)} to your first stop.`;
}

/**
 * A-01 to A-03: start the Anchor — how much cushion, which savings count,
 * and then that it is set. `editing` changes the amount of one already set.
 */
export function StartAnchor({ goals, editing = false, onClose, onDone, onSeeAnchor }) {
  const a = goals.anchor;
  const suggestion = a.suggestion;
  const [step, setStep] = useState('amount');      // amount | explain | accounts | set
  const [size, setSize] = useState(editing ? (a.size ?? 0) : suggestion ? 1 : 0);
  const [custom, setCustom] = useState(editing ? String(a.target) : '');
  const [chosen, setChosen] = useState(() => new Set(
    a.started ? a.accounts : a.available_accounts.filter((x) => x.suggested).map((x) => x.account_id)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const heading = useFocusHeading(step);

  const target = size > 0 && suggestion ? suggestion.amount * size : parseAmount(custom);
  const valid = Number.isFinite(target) && target > 0;
  const firstStop = Math.min(500, valid ? target : 500);
  const counting = a.available_accounts.filter((x) => chosen.has(x.account_id))
    .reduce((sum, x) => sum + x.balance, 0);

  const save = async (fields) => {
    setBusy(true); setError('');
    try {
      const result = await setAnchor(fields);
      onDone(result);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  if (step === 'explain') {
    return (
      <DetailPanel label="How we worked this out" onClose={onClose} className="on-card"
                   back={{ label: 'Start your Anchor', onClick: () => setStep('amount') }}>
        <TargetSteps suggestion={suggestion} heading={heading} />
      </DetailPanel>
    );
  }

  if (step === 'set') {
    return (
      <DetailPanel label="Your Anchor is set" overline="Your Anchor" onClose={onClose} className="on-card">
        <Mark phase="build" width={96} />
        <h1 className="pk-h1" tabIndex={-1} ref={heading}>Your Anchor is set</h1>
        <p className="gl-body">
          {counting >= firstStop
            ? `${amount(counting)} is already counting, so you’re past your first stop. Next: ${amount(target)}.`
            : counting > 0
              ? `${amount(counting)} is already counting. First stop: ${amount(firstStop)}, then ${amount(target)}.`
              : `First stop: ${amount(firstStop)}. Then we’ll keep going to ${amount(target)}.`}
        </p>
        <Progress label="First stop"
                  value={counting >= firstStop ? `${amount(firstStop)} · done` : `${amount(firstStop - counting)} to go`}
                  share={Math.min(counting / firstStop, 1)} done={counting >= firstStop} />
        <Progress label="Full Anchor" value={`${amount(counting)} of ${amount(target)}`}
                  share={Math.min(counting / target, 1)} done={counting >= target} />
        <div className="gl-panel-foot">
          <PButton onClick={onSeeAnchor}>See my Anchor</PButton>
        </div>
      </DetailPanel>
    );
  }

  if (step === 'accounts') {
    const note = countingNote(counting, firstStop);
    return (
      <DetailPanel label="Which savings count?" overline="Build · Step 1 of 2" onClose={onClose}
                   className="on-card">
        <h1 className="pk-h1" tabIndex={-1} ref={heading}>Which savings count?</h1>
        <p className="gl-body">Only money in these accounts counts toward your Anchor. You can
          change this later.</p>
        <AccountChoices accounts={a.available_accounts} chosen={chosen}
                        onToggle={(id, on) => setChosen((s) => {
                          const next = new Set(s);
                          if (on) next.add(id); else next.delete(id);
                          return next;
                        })} />
        {note && <Alert>{note}</Alert>}
        {error && <p className="txd-hint" role="alert">{error}</p>}
        <div className="gl-panel-foot">
          <PButton disabled={busy}
                   onClick={async () => {
                     const r = await save({ target, size, accounts: [...chosen] });
                     if (r) setStep('set');
                   }}>
            {busy ? 'Setting…' : 'Set my Anchor'}
          </PButton>
        </div>
      </DetailPanel>
    );
  }

  return (
    <DetailPanel label={editing ? 'Change your Anchor' : 'Start your Anchor'}
                 overline={editing ? 'Your Anchor' : 'Build · Step 1 of 2'}
                 onClose={onClose} className="on-card">
      <h1 className="pk-h1" tabIndex={-1} ref={heading}>
        {editing ? 'Change your Anchor' : 'Start your Anchor'}
      </h1>
      <p className="gl-body">A cushion for surprises, so one rough month doesn’t undo your plans.</p>
      {suggestion && (
        <div className="gl-suggest">
          <p className="pk-overline">We suggest</p>
          <p className="pk-amount">{amount(suggestion.amount)}</p>
          <p className="pk-label pk-muted">
            One month of your Essentials, from your last {suggestion.months.length === 1
              ? 'month' : `${suggestion.months.length} months`}
          </p>
          <More onClick={() => setStep('explain')}>How we worked this out</More>
        </div>
      )}
      {suggestion ? (
        <>
          <p className="gl-text" id="cushion-label">How much cushion?</p>
          <Segments label="How much cushion?" value={size} options={SIZES} onChange={setSize} />
        </>
      ) : (
        <p className="gl-text">Pick an amount to aim for. A month of what you spend on
          essentials is a good start.</p>
      )}
      {size === 0 && (
        <Field label="How much?" id="anchor-amount"
               error={custom && !valid ? 'Enter an amount above zero.' : ''}>
          <input id="anchor-amount" inputMode="decimal" value={custom} placeholder="$2,000"
                 onChange={(e) => setCustom(e.target.value)} />
        </Field>
      )}
      {valid && (
        <Alert>First stop: {amount(firstStop)}. Then we’ll keep going to {amount(target)}.</Alert>
      )}
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        {editing ? (
          <PButton disabled={!valid || busy}
                   onClick={async () => { if (await save({ target, size })) onClose(); }}>
            {busy ? 'Saving…' : 'Save'}
          </PButton>
        ) : (
          <PButton disabled={!valid} onClick={() => setStep('accounts')}>Continue</PButton>
        )}
      </div>
    </DetailPanel>
  );
}

/** How the suggested amount was worked out: Essentials, month by month. */
function TargetSteps({ suggestion, heading, target, size }) {
  return (
    <>
      <h1 className="pk-h1" tabIndex={-1} ref={heading}>Your Anchor amount</h1>
      {suggestion ? (
        <>
          {suggestion.months.map((m) => (
            <Line key={m.month} label={`Essentials in ${monthName(m.month)}`}
                  value={amount(Math.round(m.essentials))} />
          ))}
          <div className="gl-divider" />
          <Line label="One month, on average" value={amount(Math.round(suggestion.average))} strong />
          {target != null && (
            <Line label={size > 0 && Math.abs(suggestion.amount * size - target) < 0.5
              ? `Your Anchor · ${size} month${size === 1 ? '' : 's'}`
              : 'Your Anchor · your own amount'} value={amount(target)} strong />
          )}
          <p className="pk-label pk-muted">Essentials are what you need rather than choose:
            rent, groceries, bills, getting around. We round to the nearest $50 so it’s a
            number you can remember.</p>
        </>
      ) : (
        <p className="gl-body">There isn’t a full month of spending yet to suggest an amount
          from, so this one is yours.</p>
      )}
    </>
  );
}

/** "How we worked this out" from the Anchor's page, with a way to change it. */
export function TargetExplained({ goals, onClose, onChange }) {
  const a = goals.anchor;
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} className="on-card">
      <TargetSteps suggestion={a.suggestion} target={a.target} size={a.size} />
      <More onClick={onChange}>Change the amount</More>
      <div className="gl-panel-foot">
        <PButton variant="secondary" onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

/** Change accounts: which savings count toward the Anchor. */
export function AnchorAccounts({ goals, onClose, onDone }) {
  const a = goals.anchor;
  const [chosen, setChosen] = useState(() => new Set(a.accounts));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const counting = a.available_accounts.filter((x) => chosen.has(x.account_id))
    .reduce((sum, x) => sum + x.balance, 0);
  const note = countingNote(counting, a.first_stop);
  return (
    <DetailPanel label="Which savings count?" overline="Your Anchor" onClose={onClose}
                 className="on-card">
      <h1 className="pk-h1">Which savings count?</h1>
      <p className="gl-body">Only money in these accounts counts toward your Anchor.</p>
      <AccountChoices accounts={a.available_accounts} chosen={chosen}
                      onToggle={(id, on) => setChosen((s) => {
                        const next = new Set(s);
                        if (on) next.add(id); else next.delete(id);
                        return next;
                      })} />
      {note && <Alert>{note}</Alert>}
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        <PButton disabled={busy} onClick={async () => {
          setBusy(true); setError('');
          try { onDone(await setAnchor({ accounts: [...chosen] })); onClose(); }
          catch (e) { setError(e.message); }
          finally { setBusy(false); }
        }}>{busy ? 'Saving…' : 'Save'}</PButton>
      </div>
    </DetailPanel>
  );
}
