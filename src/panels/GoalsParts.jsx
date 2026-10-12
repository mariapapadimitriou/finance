import { useEffect, useRef } from 'react';
import PIcon from '../pearl/icons.jsx';
import { MARKS } from '../pearl/ui.jsx';
import shellBuild from '../pearl/assets/shell-build.svg';
import shellProtect from '../pearl/assets/shell-protect.svg';
import { money } from '../api.js';

// The pieces the Goals page is built from (Pearl Handoff, THL-131, THL-132,
// THL-179). Each phase has its shell: Protect is the closed clam, Build lifts
// and the pearl peeks out, Unveil is the open scallop (the logo mark). Only the
// Anchor carries one — chests and the saving goal are neutral.

export const PHASE_MARKS = { protect: shellProtect, build: shellBuild, unveil: MARKS.pearl };

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

/** "2027-03" → "March". */
export const monthName = (ym) => MONTHS[Number(ym?.slice(5, 7)) - 1] ?? ym ?? '';
/** "2027-03" → "Mar". */
export const monthShort = (ym) => monthName(ym).slice(0, 3);
/** "2027-03" → "March 2027". */
export const monthYear = (ym) => (ym ? `${monthName(ym)} ${ym.slice(0, 4)}` : '');
/** "2027-03" → "Mar 2027". */
export const monthShortYear = (ym) => (ym ? `${monthShort(ym)} ${ym.slice(0, 4)}` : '');
/** "2026-10-02" → "Oct 2". */
export const dayShort = (iso) => (iso ? `${monthShort(iso)} ${Number(iso.slice(8, 10))}` : '');
/** "2027-02-01" → "February 1". */
export const dayLong = (iso) => (iso ? `${monthName(iso)} ${Number(iso.slice(8, 10))}` : '');

/** Whole dollars when the amount is whole, cents when it isn't. */
export const amount = (n) => money(n, { cents: Math.abs((n ?? 0) % 1) > 0.004 });

/** "March and June 2027", or "December 2026 and March 2027" across a year. */
export function rangeWords(from, to, joiner = 'and') {
  if (from === to) return monthYear(from);
  if (from.slice(0, 4) === to.slice(0, 4)) return `${monthName(from)} ${joiner} ${monthYear(to)}`;
  return `${monthYear(from)} ${joiner} ${monthYear(to)}`;
}

/** "Mar–Jun 2027", or "Dec 2026–Mar 2027". */
export function rangeShort(from, to) {
  if (from === to) return monthShortYear(from);
  if (from.slice(0, 4) === to.slice(0, 4)) return `${monthShort(from)}–${monthShortYear(to)}`;
  return `${monthShortYear(from)}–${monthShortYear(to)}`;
}

/** "June, July and September". */
export function listWords(items) {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
}

/** A phase's shell. Decorative: the overline beside it names the phase. */
export function Mark({ phase, width = 56 }) {
  return <img className="gl-mark" src={PHASE_MARKS[phase] ?? shellBuild} alt=""
              width={width} height={Math.round((width * 5) / 6)} />;
}

/** The page's own heading. An overline that leads back is a link. */
export function PageHead({ overline, title, onBack, backLabel }) {
  return (
    <header className="gl-head">
      {onBack ? (
        <button type="button" className="pk-overline accent gl-up" onClick={onBack}
                aria-label={backLabel}>
          {overline}
        </button>
      ) : <p className="pk-overline accent">{overline}</p>}
      <h1 className="pk-h1">{title}</h1>
    </header>
  );
}

/** "See details  ›": a text link that moves somewhere. */
export function More({ children, onClick, className = '' }) {
  return (
    <button type="button" className={`gl-more ${className}`} onClick={onClick}>
      {children}<span aria-hidden="true">  ›</span>
    </button>
  );
}

/** A label on the left and its figure on the right. */
export function Line({ label, value, strong = false }) {
  return (
    <div className={`gl-line${strong ? ' strong' : ''}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}

/** A neutral status: words in a pill, never colour alone. */
export function Pill({ children }) {
  return <span className="gl-pill">{children}</span>;
}

/** A labelled text field, 52px, as the Handoff Input draws it. */
export function Field({ label, error, hint, children, id }) {
  return (
    <div className="gl-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && (
        <p className="txd-hint" role="alert"><PIcon name="alert" size={14} /> {error}</p>
      )}
      {!error && hint && <p className="gl-hint">{hint}</p>}
    </div>
  );
}

/** Two to four ways of doing one thing, side by side (Segmented control). */
export function Segments({ label, value, options, onChange }) {
  return (
    <div className="pk-seg gl-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value}
                className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Where focus goes when a step inside a panel changes: its heading. */
export function useFocusHeading(dep) {
  const ref = useRef(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    ref.current?.focus();
  }, [dep]);
  return ref;
}

/** Parse what someone typed as money: "$2,150" → 2150. */
export function parseAmount(text) {
  const n = Number(String(text ?? '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(n) ? n : NaN;
}
