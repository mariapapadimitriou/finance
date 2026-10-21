import { Choice, PButton, amountTone, txAmount } from '../pearl/kit.jsx';
import './txextras.css';

/**
 * Possible duplicates (Pearl THL-165).
 *
 *   D-01  `duplicateAlert`: the line above the list. The second copy itself
 *         is listed as not counted, "Possible duplicate · counted once until
 *         you check", with a suggested chip.
 *   D-02  `DuplicateQuestion`: in Needs a look, both copies side by side with
 *         where each came from and the bank's own description. Tapping Same
 *         purchase hides the copy (kept, so Undo works); Two different
 *         purchases counts both. Skip for now leaves it counted once.
 *   D-03  the toast after: what it did to her numbers, with Undo.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const SHORT = MONTHS.map((m) => m.slice(0, 3));
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function longDate(iso) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[m - 1]} ${d}`
    + (y !== new Date().getFullYear() ? `, ${y}` : '');
}

const shortDate = (iso) => `${SHORT[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

/** D-01's alert: how many, and that each is counted once meanwhile. */
export function duplicateAlert(n) {
  if (!n) return '';
  return n === 1 ? '1 possible duplicate needs a look. We’re counting it once for now.'
    : `${n} possible duplicates need a look. We’re counting each once for now.`;
}

/** "the copy from the statement file" — the one that would be hidden. */
export function copyPhrase(label) {
  switch (label) {
    case 'from a statement file': return 'from the statement file';
    case 'added by hand': return 'you added by hand';
    case 'pending at your bank': return 'that was still pending';
    case 'from your bank connection': return 'from your bank connection';
    default: return '';
  }
}

/** One side of the comparison. */
export function CopyCard({ side, found }) {
  const how = side.source_verb + (found ? ` ${shortDate(found)}` : '');
  return (
    <div className="dp-copy" aria-label={side.source_label}>
      <p className="pk-overline accent">{side.source_label}</p>
      <p className="pk-muted dp-merchant">{side.merchant}</p>
      <p className="pk-label pk-muted">{longDate(side.date)} · {side.account}</p>
      <p className={`pk-h3 dp-amt ${amountTone(side.amount < 0)}`}>
        {txAmount(side.amount, { inflow: side.amount < 0, signed: true })}
      </p>
      <p className="pk-label pk-muted dp-raw">{side.description} · {how}</p>
    </div>
  );
}

/** D-02: "Is this the same purchase?" Tapping an answer is the commit
 * (Current design, 2026-10-20): no Save. */
export function DuplicateQuestion({ it, busy = false, onAnswer, onSkip }) {
  const name = `dup-${it.txn.id}`;
  const hide = copyPhrase(it.txn.source_label);
  return (
    <>
      <h2 className="pk-h2">Is this the same purchase?</h2>
      <div className="dp-compare">
        <CopyCard side={it.twin} />
        <CopyCard side={it.txn} found={it.txn.found_on} />
      </div>
      <div className="pk-choices" role="radiogroup" aria-label="Is this the same purchase?">
        <Choice name={name} checked={false} disabled={busy} onChange={() => onAnswer('same')}
                label="Same purchase"
                description={hide ? `Keep one. We’ll hide the copy ${hide}.` : 'Keep one. We’ll hide the copy.'} />
        <Choice name={name} checked={false} disabled={busy} onChange={() => onAnswer('different')}
                label="Two different purchases" description="Keep both. Both count as spending." />
      </div>
      <div className="nl-actions">
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onSkip}>
          Skip for now
        </PButton>
      </div>
    </>
  );
}
