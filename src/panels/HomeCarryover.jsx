import { useState } from 'react';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { longDate, monthName, shown } from './HomePanel.jsx';

/**
 * Last month's surplus or shortfall, carried into this one (THL-212).
 *
 * A shortfall is asked about each time: take it from this month, or spread
 * it over two or three. Money to spare is suggested for saving — her
 * Anchor, or a treasure chest — or spending this month; unanswered for seven
 * days it's added to this month's safe to spend, and Home says so once.
 * Copy follows the calm-copy rules: no red, no blame, whole dollars.
 */

const nextMonth = (m) => {
  const [y, n] = m.split('-').map(Number);
  return n === 12 ? `${y + 1}-01` : `${y}-${String(n + 1).padStart(2, '0')}`;
};

/** What Home shows for last month, or nothing. */
export function CarryoverPrompt({ c, onAnswer, onChest }) {
  const [asking, setAsking] = useState(false);
  if (!c) return null;
  const was = monthName(c.month);
  const now = monthName(nextMonth(c.month));
  if (c.kind === 'short' && !c.choice) {
    return (
      <>
        <Alert tone="info" action="Choose" onAction={() => setAsking(true)}>
          {`${was} ended ${shown(c.amount)} short of plan. Choose how ${now} makes it up.`}
        </Alert>
        {asking && (
          <ShortfallSheet c={c} now={now} was={was} onClose={() => setAsking(false)}
                          onAnswer={(choice) => onAnswer(choice).then(() => setAsking(false))} />
        )}
      </>
    );
  }
  if (c.kind === 'spare' && c.auto) {
    return (
      <Alert tone="positive" action="Got it" onAction={() => onAnswer('spend')}>
        {`${was}’s ${shown(c.amount)} to spare is in ${now}’s safe to spend.`}
      </Alert>
    );
  }
  if (c.kind === 'spare' && !c.choice) {
    return <SpareCard c={c} was={was} now={now} onAnswer={onAnswer} onChest={onChest} />;
  }
  return null;
}

/** A shortfall: this month, or spread over two or three. */
export function ShortfallSheet({ c, now, was, onClose, onAnswer }) {
  const [choice, setChoice] = useState('now');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const options = [
    ['now', `Take it from ${now}`, `${shown(c.amount)} comes off ${now}’s safe to spend.`],
    ['spread2', 'Spread over 2 months', `About ${shown(c.amount / 2)} off ${now} and the month after.`],
    ['spread3', 'Spread over 3 months', `About ${shown(c.amount / 3)} off each of the next 3 months.`],
  ];
  return (
    <DetailPanel label={`How ${now} makes up ${was}`} overline="Last month" onClose={onClose}>
      <h1 className="pk-h2">{`${was} ended ${shown(c.amount)} short`}</h1>
      <p className="pk-muted">
        {c.income != null
          ? `${shown(c.income)} came in and ${shown(c.spent)} went out. That happens, and it’s easy to make up.`
          : 'That happens, and it’s easy to make up.'}
      </p>
      {c.saved > 0 && (
        <p className="pk-muted">
          {`You also put ${shown(c.saved)} away, which isn’t counted here — that’s yours.`}
        </p>
      )}
      {c.unsorted > 0 && (
        <p className="pk-muted">
          {`Not counting ${shown(c.unsorted)} of transfers you haven’t sorted yet. Sorting them in Needs a look can change this.`}
        </p>
      )}
      <div className="pk-choices" role="radiogroup" aria-label="How to make it up">
        {options.map(([k, label, sub]) => (
          <Choice key={k} name="hm-carry" checked={choice === k} onChange={() => setChoice(k)}
                  label={label} description={sub} />
        ))}
      </div>
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton disabled={busy} onClick={() => {
        setBusy(true);
        setError(null);
        onAnswer(choice).catch((e) => { setError(e.message); setBusy(false); });
      }}>{busy ? 'Saving…' : 'Save'}</PButton>
    </DetailPanel>
  );
}

/** Money to spare: save it, put it in a chest, or spend it this month. */
export function SpareCard({ c, was, now, onAnswer, onChest }) {
  return (
    <section className="hm-card hm-carry" aria-labelledby="hm-carry-title">
      <p className="pk-overline accent">{`${was} is done`}</p>
      <h2 className="pk-h3" id="hm-carry-title">
        {`${was} left you ${shown(c.amount)} more than planned`}
      </h2>
      <p className="pk-muted">
        {`Putting it toward your Anchor or a treasure chest keeps it working. If you don’t choose by ${longDate(c.deadline)}, it’s added to ${now}’s safe to spend.`}
      </p>
      <div className="hm-carry-actions">
        <PButton variant="secondary" onClick={() => onAnswer('save')}>Add to your Anchor</PButton>
        <PButton variant="secondary" onClick={() => onAnswer('chest').then(() => onChest?.())}>
          Put it in a treasure chest
        </PButton>
        <PButton variant="text" onClick={() => onAnswer('spend')}>{`Spend it in ${now}`}</PButton>
      </div>
    </section>
  );
}

/** The sheet's row for it (X-01): "Catching up from September" or "Left over from September". */
export function carryoverRow(r) {
  const parts = r.parts ?? [];
  const one = parts.length === 1 ? parts[0] : null;
  const from = one ? monthName(one.from) : 'earlier months';
  if (r.kind === 'short') {
    return {
      label: `Catching up from ${from}`,
      detail: one && one.of > 1 ? `${one.index} of ${one.of} · you chose to spread it`
        : `${from} ended short of plan`,
    };
  }
  return { label: `Left over from ${from}`, detail: `Money to spare from ${from}` };
}
