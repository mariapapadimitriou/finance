import { useState } from 'react';
import { Alert, Choice, PButton } from '../pearl/kit.jsx';
import { monthName, shown } from './HomePanel.jsx';

/**
 * Last month's surplus or shortfall, carried into this one (THL-212; CO-01
 * to CO-03, THL-233).
 *
 * A shortfall is a card on Home (CO-01): take it from this month, or spread
 * it over two or three, each with what Allowance becomes. Money to
 * spare (CO-02) asks what to do with it — her Anchor (she moves it), a
 * treasure chest, or this month — and unanswered for seven days it's added
 * to this month's Allowance, and Home says so once. Copy follows the
 * calm-copy rules: no red, no blame, whole dollars.
 */

const nextMonth = (m) => {
  const [y, n] = m.split('-').map(Number);
  return n === 12 ? `${y + 1}-01` : `${y}-${String(n + 1).padStart(2, '0')}`;
};

/** What Home shows for last month, or nothing. */
export function CarryoverPrompt({ c, safe = null, onAnswer, onChest, onExplain }) {
  if (!c) return null;
  const was = monthName(c.month);
  const now = monthName(nextMonth(c.month));
  if (c.kind === 'short' && !c.choice) {
    return <ShortfallCard c={c} now={now} was={was} safe={safe} onAnswer={onAnswer} onExplain={onExplain} />;
  }
  if (c.kind === 'spare' && c.auto) {
    return (
      <Alert tone="positive" action="Got it" onAction={() => onAnswer('spend')}>
        {`${was}’s ${shown(c.amount)} to spare is in ${now}’s Allowance.`}
      </Alert>
    );
  }
  if (c.kind === 'spare' && !c.choice) {
    return <SpareCard c={c} was={was} now={now} safe={safe} onAnswer={onAnswer} onChest={onChest} />;
  }
  return null;
}

/** "$642 → $142": Allowance before and after a choice. */
const arrow = (safe, delta) => (safe && safe.amount != null
  ? `Allowance: ${shown(safe.amount)} → ${shown(safe.amount + delta)}` : '');

/** CO-01: last month ended short — take it from this month, or spread it. */
export function ShortfallCard({ c, now, was, safe = null, onAnswer, onExplain }) {
  const [choice, setChoice] = useState('spread2');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const per = (n) => c.amount / n;
  const options = [
    ['now', `Take it from ${now}`, arrow(safe, -c.amount) || `${shown(c.amount)} comes off ${now}’s Allowance`],
    ['spread2', 'Spread over 2 months', `${shown(per(2))} a month${safe && safe.amount != null ? ` · ${now} → ${shown(safe.amount - per(2))}` : ''}`],
    ['spread3', 'Spread over 3 months', `${shown(per(3))} a month${safe && safe.amount != null ? ` · ${now} → ${shown(safe.amount - per(3))}` : ''}`],
  ];
  const label = choice === 'now' ? `Take it from ${now}` : `Catch up over ${choice === 'spread2' ? 2 : 3} months`;
  return (
    <section className="hm-card hm-carry" aria-labelledby="hm-carry-title">
      <p className="pk-overline accent">{was}</p>
      <h2 className="pk-h2" id="hm-carry-title">{`${was} ended ${shown(c.amount)} short of plan`}</h2>
      <p className="pk-muted">
        {c.income != null
          ? `${shown(c.income)} came in and ${shown(c.spent)} went out. How would you like to catch up?`
          : 'That happens, and it’s easy to make up. How would you like to catch up?'}
      </p>
      <div className="pk-choices" role="radiogroup" aria-label="How to catch up">
        {options.map(([k, l, sub]) => (
          <Choice key={k} name="hm-carry" checked={choice === k} onChange={() => setChoice(k)}
                  label={l} description={sub} />
        ))}
      </div>
      {error && <Alert tone="caution">{error}</Alert>}
      <div className="hm-carry-actions">
        <PButton disabled={busy} onClick={() => {
          setBusy(true);
          setError(null);
          onAnswer(choice).catch((e) => { setError(e.message); setBusy(false); });
        }}>{busy ? 'Saving…' : label}</PButton>
        {onExplain && <PButton variant="text" onClick={onExplain}>How we worked this out</PButton>}
      </div>
      {c.unsorted > 0 && (
        <p className="pk-label pk-muted">
          {`Not counting ${shown(c.unsorted)} of transfers you haven’t sorted yet.`}
        </p>
      )}
    </section>
  );
}

/** CO-02: money to spare — her Anchor, a chest, or spend it this month. */
export function SpareCard({ c, was, now, safe = null, onAnswer, onChest }) {
  const [choice, setChoice] = useState('save');
  const [later, setLater] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  if (later) return null;
  const options = [
    ['save', 'Put it in your Anchor', `Move ${shown(c.amount)} to your savings. Pearl can’t move money for you.`],
    ['chest', 'Put it in a treasure chest', 'Choose a chest on Save'],
    ['spend', 'Spend it this month', arrow(safe, c.amount) || `${shown(c.amount)} is added to ${now}’s Allowance`],
  ];
  const go = () => {
    setBusy(true);
    setError(null);
    onAnswer(choice).then(() => { if (choice === 'chest') onChest?.(); })
      .catch((e) => { setError(e.message); setBusy(false); });
  };
  return (
    <section className="hm-card hm-carry" aria-labelledby="hm-carry-title">
      <p className="pk-overline accent">{was}</p>
      <h2 className="pk-h2" id="hm-carry-title">
        {`${was} left you ${shown(c.amount)} more than planned`}
      </h2>
      <p className="pk-muted">What would you like to do with it?</p>
      <div className="pk-choices" role="radiogroup" aria-label="What to do with it">
        {options.map(([k, l, sub]) => (
          <Choice key={k} name="hm-spare" checked={choice === k} onChange={() => setChoice(k)}
                  label={l} description={sub} />
        ))}
      </div>
      {error && <Alert tone="caution">{error}</Alert>}
      <div className="hm-carry-actions">
        <PButton disabled={busy} onClick={go}>
          {busy ? 'Saving…' : choice === 'spend' ? 'Spend it' : 'I’ve moved it'}
        </PButton>
        <PButton variant="text" onClick={() => setLater(true)}>Later</PButton>
      </div>
      <p className="pk-label pk-muted">
        If you don’t choose in 7 days, it’s added to this month’s Allowance. We’ll tell you when.
      </p>
    </section>
  );
}

/** The sheet's row for it (CO-03): "Catching up from September · 1 of 2 ·
 * $500 short, spread over 2 months", or "Left over from September". */
export function carryoverRow(r) {
  const parts = r.parts ?? [];
  const one = parts.length === 1 ? parts[0] : null;
  const from = one ? monthName(one.from) : 'earlier months';
  if (r.kind === 'short') {
    const total = one && one.of > 1 && one.amount != null ? shown(one.amount * one.of) : null;
    return {
      label: `Catching up from ${from}`,
      detail: one && one.of > 1
        ? `${one.index} of ${one.of}${total ? ` · ${total} short` : ''} · spread over ${one.of} months`
        : `${from} ended short of plan`,
    };
  }
  return { label: `Left over from ${from}`, detail: `Money to spare from ${from}` };
}
