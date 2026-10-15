import { useState } from 'react';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { setAnchor } from '../api.js';
import { PearlProgress, ProgressBar } from '../pearl/viz.jsx';
import {
  Line, Mark, More, PageHead, amount, dayShort, monthName, rangeShort, rangeWords,
  useFocusHeading,
} from './GoalsParts.jsx';
import { Ledger } from './HomePanel.jsx';

/**
 * The Anchor (THL-229, THL-230; A-01 to A-06, G-01, G-02, X-03): the cash
 * savings she already has, less what her treasure chests hold. There is no
 * amount to set. The milestone is three months of her usual Essentials, a
 * benchmark she can't change; reached once, it stays reached after a dip.
 * No phase names anywhere (THL-238).
 */

/** "1.9 months", "3 months". */
export function monthsWords(months) {
  if (months == null) return '';
  const n = Math.round(months * 10) / 10;
  return `${Number.isInteger(n) ? n : n.toFixed(1)} month${n === 1 ? '' : 's'}`;
}

/** The hero's figure: "$5,470 · 1.9 months of Essentials". */
export function anchorFigure(a) {
  return a.months != null ? `${amount(a.counted)} · ${monthsWords(a.months)} of Essentials`
    : amount(a.counted);
}

/** "63% of the way to 3 months · likely Jul 2027 – Jun 2028". */
export function progressWords(a) {
  const pct = Math.round((a.share ?? 0) * 100);
  const p = a.projection;
  const when = p?.state === 'range' ? ` · likely ${rangeShort(p.from, p.to).replace('–', ' – ')}`
    : p?.state === 'none' ? ' · no date yet' : '';
  return a.target > 0 ? `${pct}% of the way to 3 months${when}` : 'Pearl needs a full month to work out your milestone';
}

/** "$7,420 in savings − $1,950 in treasure chests = $5,470 Anchor". */
export function countingWords(savings, chests) {
  const counted = Math.max(savings - chests, 0);
  if (savings <= 0) return null;
  return chests > 0
    ? `${amount(savings)} in savings − ${amount(chests)} in treasure chests = ${amount(counted)} Anchor`
    : `${amount(savings)} in savings = ${amount(counted)} Anchor`;
}

const INTRO = 'Money for big surprises, like a car repair or a vet bill. It’s the cash savings you already have, less what your treasure chests hold.';

/** The Anchor, pinned at the top of Save. */
export function AnchorCard({ goals, onStart, onOpen, onTab }) {
  const a = goals.anchor;
  const head = (overline, title, extra) => (
    <div className="gl-anchor-head">
      <Mark phase={a.earned ? 'unveil' : a.started ? 'build' : goals.phase === 'protect' ? 'protect' : 'build'} />
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
        {head('Comes next', 'Your Anchor')}
        <p className="gl-body">Money for big surprises, like a car repair or a vet bill. It’s the
          cash savings you already have. It becomes your focus once the basics are covered, and
          you can set it up any time.</p>
        <div className="gl-actions"><PButton variant="secondary" onClick={onStart}>Set it up early</PButton></div>
      </section>
    );
  }

  if (!a.started) {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('Step 1 of 2', 'Your Anchor')}
        <p className="gl-body">{INTRO}</p>
        <div className="gl-actions"><PButton onClick={onStart}>Set up your Anchor</PButton></div>
      </section>
    );
  }

  if (a.earned && a.full) {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('Milestone reached', 'Your Anchor covers 3 months')}
        <PearlProgress title={anchorFigure(a)} saved={a.counted} target={a.target} share={1}
                       sub="Milestone reached" />
        <p className="gl-body">Three months of Essentials, ready for a big surprise. If your Anchor
          dips below 3 months, Pearl lets you know.</p>
        <div className="gl-actions">
          <PButton variant="secondary" onClick={() => onTab('path')}>See what’s next on Wins</PButton>
        </div>
      </section>
    );
  }

  if (a.earned) {
    return (
      <section className="gl-card gl-anchor" aria-label="Your Anchor">
        {head('Keep it going', 'Your Anchor')}
        <PearlProgress title={anchorFigure(a)} saved={a.counted} target={a.target} share={a.share}
                       sub="Just under 3 months · put a little away when you can" />
        <p className="gl-body">A big surprise dipped into it, which is what it’s for. The milestone
          stays reached.</p>
        <More onClick={onOpen}>Top it up when you can</More>
      </section>
    );
  }

  // The hero while it grows (G-01): the pearl grows with the nacre bar, the
  // one nacre element on the page.
  return (
    <section className="gl-card gl-anchor" aria-label="Your Anchor">
      {head('Step 2 of 2', 'Your Anchor', <More className="gl-push" onClick={onOpen}>See details</More>)}
      <PearlProgress title={anchorFigure(a)} saved={a.counted} target={a.target} share={a.share}
                     delta={a.saved_this_month} sub={progressWords(a)} />
    </section>
  );
}

/** A-04: the Anchor's own page. */
export function AnchorDetail({ goals, onBack, onProjection, onAccounts, onExplain }) {
  const a = goals.anchor;
  const p = a.projection;
  const overline = a.full ? 'Milestone reached' : a.earned ? 'Keep it going' : 'Step 2 of 2';
  return (
    <>
      <PageHead overline="Save" title="Your Anchor" onBack={onBack} backLabel="Back to Save" />

      <section className="gl-card" aria-label="Progress">
        <div className="gl-anchor-head">
          <Mark phase={a.earned ? 'unveil' : 'build'} />
          <div className="gl-stack">
            <p className="pk-overline accent">{overline}</p>
            <h2 className="pk-h2">{anchorFigure(a)}</h2>
          </div>
          <More className="gl-push" onClick={onExplain}>How we worked this out</More>
        </div>
        <ProgressBar label="3 months of Essentials"
                     value={a.target <= 0 ? 'Not known yet' : a.full ? 'Reached' : `${amount(a.to_go)} to go`}
                     share={a.share} tone={a.full ? 'positive' : 'brand'} />
      </section>

      <section className="gl-card gl-row-card" aria-label="When you’ll reach 3 months">
        <div className="gl-stack gl-grow">
          <h2 className="pk-h3">When you’ll reach 3 months</h2>
          <p className="gl-text">
            {p?.state === 'range' ? `Likely between ${rangeWords(p.from, p.to)}`
              : p?.state === 'full' ? 'You’re there'
                : 'No date yet'}
          </p>
        </div>
        <More onClick={onProjection}>{p?.state === 'range' ? 'See the range' : 'See why'}</More>
      </section>

      <div className="gl-cols">
        <section className="gl-card" aria-label="Your savings">
          <h2 className="pk-h3">Your savings</h2>
          {a.counting.length > 0
            ? a.counting.map((acct) => (
                <Line key={acct.account_id} label={acct.mask ? `${acct.name} ••${acct.mask}` : acct.name}
                      value={amount(acct.balance)} />
              ))
            : <p className="gl-text pk-muted">No accounts are counting toward it yet.</p>}
          {a.chests > 0 && <Line label="In treasure chests" value={`− ${amount(a.chests)}`} />}
          <More onClick={onAccounts}>Change accounts</More>
        </section>
        <section className="gl-card" aria-label="Recent">
          <h2 className="pk-h3">Recent</h2>
          {a.recent.length > 0
            ? a.recent.map((r) => (
                <Line key={`${r.date}${r.amount}`}
                      label={`${dayShort(r.date)} · ${r.saved ? 'Put away' : 'Taken out'}`}
                      value={amount(r.amount)} />
              ))
            : <p className="gl-text pk-muted">Transfers you mark as Saved show here.</p>}
        </section>
      </div>
    </>
  );
}

/** The accounts the Anchor could count, as checkbox rows (A-02). */
function AccountChoices({ accounts, chosen, onToggle }) {
  if (!accounts.length) {
    return (
      <Alert>No savings accounts yet. Link your bank, or add one by hand on Profile › Accounts,
        and it shows here.</Alert>
    );
  }
  return (
    <div className="pk-choices">
      {accounts.map((acct) => (
        <Choice key={acct.account_id} type="checkbox" checked={chosen.has(acct.account_id)}
                onChange={(on) => onToggle(acct.account_id, on)}
                label={acct.mask ? `${acct.name} ••${acct.mask}` : acct.name}
                description={acct.kind === 'chequing'
                  ? `${amount(acct.balance)} · everyday spending, usually best left out`
                  : amount(acct.balance)} />
      ))}
    </div>
  );
}

function useChosen(a) {
  const [chosen, setChosen] = useState(() => new Set(
    a.started ? a.accounts : a.available_accounts.filter((x) => x.suggested).map((x) => x.account_id)));
  const toggle = (id, on) => setChosen((s) => {
    const next = new Set(s);
    if (on) next.add(id); else next.delete(id);
    return next;
  });
  const savings = a.available_accounts.filter((x) => chosen.has(x.account_id))
    .reduce((sum, x) => sum + x.balance, 0);
  return { chosen, toggle, savings };
}

/**
 * A-01 to A-03: set up the Anchor — what the milestone is, which savings
 * make it up, and then that it is set.
 */
export function StartAnchor({ goals, onClose, onDone, onSeeAnchor }) {
  const a = goals.anchor;
  const suggestion = a.suggestion;
  const [step, setStep] = useState('intro');      // intro | explain | accounts | set
  const { chosen, toggle, savings } = useChosen(a);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const heading = useFocusHeading(step);
  const chests = a.chests ?? 0;

  const save = async () => {
    setBusy(true); setError('');
    try {
      const r = await setAnchor({ accounts: [...chosen] });
      onDone(r);
      setResult(r);
      setStep('set');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (step === 'explain') {
    return (
      <DetailPanel label="How we worked this out" onClose={onClose} className="on-card"
                   back={{ label: 'Set up your Anchor', onClick: () => setStep('intro') }}>
        <MilestoneSteps suggestion={suggestion} heading={heading} />
      </DetailPanel>
    );
  }

  if (step === 'set') {
    const set = result?.anchor ?? a;
    return (
      <DetailPanel label="Your Anchor is set" overline="Your Anchor" onClose={onClose} className="on-card">
        <Mark phase="build" width={96} />
        <h1 className="pk-h1" tabIndex={-1} ref={heading}>Your Anchor is set</h1>
        <p className="gl-body">
          {set.target > 0
            ? `Your Anchor is ${amount(set.counted)}, about ${monthsWords(set.months)} of your usual Essentials. The milestone is 3 months (${amount(set.target)}).`
            : `Your Anchor is ${amount(set.counted)}. Once Pearl has seen a full month, it’ll say how many months of Essentials that covers.`}
        </p>
        <ProgressBar label="3 months of Essentials" value={anchorFigure(set)}
                     share={set.share} tone={set.full ? 'positive' : 'brand'} />
        <div className="gl-panel-foot">
          <PButton onClick={onSeeAnchor}>See my Anchor</PButton>
        </div>
      </DetailPanel>
    );
  }

  if (step === 'accounts') {
    const note = countingWords(savings, chests);
    return (
      <DetailPanel label="Which savings make up your Anchor?" overline="Step 1 of 2" onClose={onClose}
                   className="on-card">
        <h1 className="pk-h1" tabIndex={-1} ref={heading}>Which savings make up your Anchor?</h1>
        <p className="gl-body">Pick your cash savings. Your Anchor adds them up and takes out what
          your treasure chests hold. Change it any time.</p>
        <AccountChoices accounts={a.available_accounts} chosen={chosen} onToggle={toggle} />
        {note && <Alert>{note}</Alert>}
        {error && <p className="txd-hint" role="alert">{error}</p>}
        <div className="gl-panel-foot">
          <PButton disabled={busy} onClick={save}>{busy ? 'Setting…' : 'Set my Anchor'}</PButton>
        </div>
      </DetailPanel>
    );
  }

  return (
    <DetailPanel label="Set up your Anchor" overline="Step 1 of 2" onClose={onClose} className="on-card">
      <h1 className="pk-h1" tabIndex={-1} ref={heading}>Set up your Anchor</h1>
      <p className="gl-body">{INTRO}</p>
      <div className="gl-suggest">
        <p className="pk-overline">Your milestone</p>
        {suggestion ? (
          <>
            <p className="pk-amount">{amount(suggestion.target)}</p>
            <p className="pk-label pk-muted">
              Three months of your usual Essentials ({amount(suggestion.amount)} a month). A
              benchmark, not a goal you set.
            </p>
            <More onClick={() => setStep('explain')}>How we worked this out</More>
          </>
        ) : (
          <p className="pk-label pk-muted">Three months of your usual Essentials. Once Pearl has seen
            a full month, it’ll say what that is.</p>
        )}
      </div>
      <Alert>Next, pick the savings accounts that make up your Anchor.</Alert>
      <div className="gl-panel-foot">
        <PButton onClick={() => setStep('accounts')}>Continue</PButton>
      </div>
    </DetailPanel>
  );
}

/** How the milestone was worked out: Essentials, month by month, times three. */
function MilestoneSteps({ suggestion, heading }) {
  return (
    <>
      <h1 className="pk-h1" tabIndex={-1} ref={heading}>Your milestone</h1>
      {suggestion ? (
        <>
          {suggestion.months.map((m) => (
            <Line key={m.month} label={`Essentials in ${monthName(m.month)}`}
                  value={amount(Math.round(m.essentials))} />
          ))}
          <div className="gl-divider" />
          <Line label="A usual month, rounded" value={amount(suggestion.amount)} strong />
          <Line label="Three months" value={amount(suggestion.target)} strong />
          <p className="pk-label pk-muted">Essentials are what you need rather than choose:
            rent, groceries, bills, getting around. We round a month to the nearest $50 so it’s a
            number you can remember. Months you marked unusual are left out.</p>
        </>
      ) : (
        <p className="gl-body">There isn’t a full month of spending yet to work it out from. Once
          there is, your milestone is three months of your usual Essentials.</p>
      )}
    </>
  );
}

const cents = (n) => amount(Math.round(n * 100) / 100);

/**
 * X-03: "How we worked this out" from the Anchor's page — the savings, the
 * chests, the Anchor, a usual month of Essentials, and the months it covers.
 */
export function anchorSheet(goals) {
  const a = goals.anchor;
  const months = a.suggestion?.months ?? [];
  const rows = [
    { key: 'savings', label: 'In your savings', display: cents(a.savings),
      detail: a.counting.length ? `${a.counting.length} account${a.counting.length === 1 ? '' : 's'}` : null,
      lines: a.counting.map((acct) => ({ label: acct.mask ? `${acct.name} ••${acct.mask}` : acct.name,
                                         amount: acct.balance })) },
    { key: 'chests', label: 'In treasure chests', display: a.chests > 0 ? `− ${cents(a.chests)}` : 'None',
      lines: (goals.chests ?? []).filter((c) => c.held > 0).map((c) => ({ label: c.name, amount: c.held })) },
    { key: 'anchor', label: 'Your Anchor', display: cents(a.counted), lines: [] },
    { key: 'usual', label: 'Your usual Essentials',
      display: a.usual ? `÷ ${cents(a.usual)}` : 'Not known yet',
      detail: months.length ? `A month, over the last ${months.length === 1 ? 'month' : `${months.length} months`}` : null,
      lines: months.map((m) => ({ label: `Essentials in ${monthName(m.month)}`, amount: m.essentials })) },
  ];
  const total = {
    label: 'Months it covers',
    detail: 'The milestone is 3 months',
    display: a.months != null ? monthsWords(a.months) : 'Not known yet',
  };
  return { title: `Your Anchor: ${amount(a.counted)}`,
           sub: 'The cash savings you have, less what your chests hold.', rows, total };
}

/** X-03 as a sheet, with a way to the what-if. */
export function TargetExplained({ goals, onClose, onWhatIf }) {
  const { title, sub, rows, total } = anchorSheet(goals);
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} sheet className="hm-sheet">
      <h1 className="pk-h2">{title}</h1>
      <p className="pk-muted">{sub}</p>
      <Ledger rows={rows} total={total} />
      {goals.anchor.to_go > 0 && onWhatIf && (
        <button type="button" className="hm-link" onClick={onWhatIf}>
          Want to reach 3 months sooner? Try putting away a bit more
        </button>
      )}
      <div className="hm-sheet-foot">
        <PButton onClick={onClose}>Got it</PButton>
      </div>
    </DetailPanel>
  );
}

/** Change accounts: which savings make up the Anchor. */
export function AnchorAccounts({ goals, onClose, onDone }) {
  const a = goals.anchor;
  const { chosen, toggle, savings } = useChosen(a);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const note = countingWords(savings, a.chests ?? 0);
  return (
    <DetailPanel label="Which savings make up your Anchor?" overline="Your Anchor" onClose={onClose}
                 className="on-card">
      <h1 className="pk-h1">Which savings make up your Anchor?</h1>
      <p className="gl-body">Pick your cash savings. Your Anchor adds them up and takes out what
        your treasure chests hold.</p>
      <AccountChoices accounts={a.available_accounts} chosen={chosen} onToggle={toggle} />
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
